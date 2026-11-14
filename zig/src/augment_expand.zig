//! Resolve RFC 7950 `augment` targets, merge augmented schema into the target module
//! (this module's tree or an imported one), and apply `deviation` (mirrors
//! `src/xyang/augment_expand.py`).

const std = @import("std");
const ast = @import("ast.zig");
const errors = @import("errors.zig");
const pyfmt = @import("pyfmt.zig");
const Module = @import("module.zig").Module;
const refine_expand = @import("refine_expand.zig");
const uses_expand = @import("uses_expand.zig");

const Statement = ast.Statement;
const IdentifierRef = ast.IdentifierRef;
const Error = errors.Error;
const Reporter = errors.Reporter;
const repr = pyfmt.repr;
const StatementList = std.ArrayList(*Statement);

/// A schema node's parent: the module (top level) or a statement.
const Owner = union(enum) {
    module: *Module,
    stmt: *Statement,

    fn statements(o: Owner) *StatementList {
        return switch (o) {
            .module => |m| &m.statements,
            .stmt => |s| &s.statements,
        };
    }
};

/// `parse_absolute_schema_path` for a path whose segments were not stored at parse time.
fn absoluteSegments(r: *Reporter, path: []const u8, stored: []const IdentifierRef) Error![]const IdentifierRef {
    if (stored.len > 0) return stored;
    const raw = std.mem.trim(u8, std.mem.trim(u8, std.mem.trim(u8, path, &refine_expand.pyWhitespace), "\""), "'");
    if (!std.mem.startsWith(u8, raw, "/")) return r.fail(.syntax, "Schema path must be absolute, got {f}", .{repr(path)});
    var out: std.ArrayList(IdentifierRef) = .empty;
    var it = std.mem.splitScalar(u8, raw[1..], '/');
    while (it.next()) |part| {
        const seg = std.mem.trim(u8, part, &refine_expand.pyWhitespace);
        if (seg.len == 0) continue;
        const idx = std.mem.indexOfScalar(u8, seg, ':');
        if (idx == null or idx.? == 0 or idx.? >= seg.len - 1) {
            return r.fail(.syntax, "Invalid schema path segment {f}: expected 'prefix:identifier'", .{repr(seg)});
        }
        try out.append(r.arena, .{ .prefix = seg[0..idx.?], .name = seg[idx.? + 1 ..] });
    }
    if (out.items.len == 0) return r.fail(.syntax, "Empty schema path: {f}", .{repr(path)});
    return out.items;
}

fn findToplevelSchemaChild(module: *Module, name: []const u8) ?*Statement {
    for (module.statements.items) |s| {
        if (std.mem.eql(u8, s.name, name) and s.schemaNode() != null) return s;
    }
    return null;
}

/// RFC 7950 7.14.2 / 7.14.3: every rpc and action has `input` and `output` schema nodes,
/// written or not. Add the empty node a schema node identifier names.
fn materializeOperationIo(a: std.mem.Allocator, parent: *Statement, name: []const u8) Error!?*Statement {
    if (parent.kind() != .rpc and parent.kind() != .action) return null;
    const is_input = std.mem.eql(u8, name, "input");
    if (!is_input and !std.mem.eql(u8, name, "output")) return null;
    const node = try a.create(Statement);
    node.* = if (is_input) .{ .name = "input", .data = .{ .input = .{} } } else .{ .name = "output", .data = .{ .output = .{} } };
    if (is_input) {
        for (parent.statements.items, 0..) |s, i| {
            if (s.kind() == .output) {
                try parent.statements.insert(a, i, node);
                return node;
            }
        }
    }
    try parent.statements.append(a, node);
    return node;
}

fn findNamedSchemaChild(a: std.mem.Allocator, parent: *Statement, name: []const u8) Error!?*Statement {
    if (parent.kind() == .choice) {
        for (parent.data.choice.cases.items) |case| {
            if (std.mem.eql(u8, case.name, name)) return case;
        }
        return null;
    }
    for (parent.statements.items) |s| {
        if (std.mem.eql(u8, s.name, name) and s.schemaNode() != null) return s;
    }
    return materializeOperationIo(a, parent, name);
}

const Walked = struct { parent: Owner, target: *Statement };

/// The lookup of the first path segment in its module (`find_toplevel`).
pub const FindToplevel = *const fn (module: *Module, name: []const u8) ?*Statement;

/// `_walk_absolute_schema_path`: `/prefix:name/...` to `(parent, target)`. Every prefix
/// must be bound in `ctx_module`; children are matched by name, through choices and cases.
fn walkAbsoluteSchemaPath(r: *Reporter, ctx_module: *Module, path: []const u8, kind: []const u8, segments: []const IdentifierRef) Error!Walked {
    return walkAbsoluteSchemaPathWith(r, ctx_module, path, kind, segments, findToplevelSchemaChild);
}

fn walkAbsoluteSchemaPathWith(r: *Reporter, ctx_module: *Module, path: []const u8, kind: []const u8, segments: []const IdentifierRef, find_toplevel: FindToplevel) Error!Walked {
    const first = segments[0];
    const pref0 = first.prefix orelse "";
    if (pref0.len == 0) return r.fail(.syntax, "{s}: invalid first segment in path {f} (expected 'prefix:identifier')", .{ kind, repr(path) });
    const mod0 = ctx_module.resolvePrefixedModule(pref0) orelse
        return r.fail(.syntax, "{s}: unknown prefix {f} in path {f} (module {f})", .{ kind, repr(pref0), repr(path), repr(ctx_module.name) });
    var cur = find_toplevel(mod0, first.name) orelse
        return r.fail(.syntax, "{s}: no top-level schema node {f} in module {f} (path {f})", .{ kind, repr(first.name), repr(mod0.name), repr(path) });
    var parent: Owner = .{ .module = mod0 };
    for (segments[1..]) |seg| {
        const pref = seg.prefix orelse "";
        if (pref.len == 0) return r.fail(.syntax, "{s}: invalid path segment {f} in path {f} (expected 'prefix:identifier')", .{ kind, repr(seg.name), repr(path) });
        if (ctx_module.resolvePrefixedModule(pref) == null) return r.fail(.syntax, "{s}: unknown prefix {f} in path {f}", .{ kind, repr(pref), repr(path) });
        const nxt = (try findNamedSchemaChild(r.arena, cur, seg.name)) orelse
            return r.fail(.syntax, "{s}: no child {f} under node in path {f} (after {f})", .{ kind, repr(seg.name), repr(path), repr(cur.name) });
        parent = .{ .stmt = cur };
        cur = nxt;
    }
    return .{ .parent = parent, .target = cur };
}

/// `resolve_absolute_schema_path`: an absolute schema path whose first segment is found
/// with `find_toplevel` (RFC 8791 `augment-structure` looks up registered structures).
pub fn resolveAbsoluteSchemaPath(r: *Reporter, ctx_module: *Module, path: []const u8, kind: []const u8, find_toplevel: FindToplevel) Error!*Statement {
    const segments = try absoluteSegments(r, path, &.{});
    return (try walkAbsoluteSchemaPathWith(r, ctx_module, path, kind, segments, find_toplevel)).target;
}

/// `resolve_augment_target`: the schema node that receives the augment's children.
pub fn resolveAugmentTarget(r: *Reporter, ctx_module: *Module, aug: *Statement) Error!*Statement {
    const d = aug.data.augment;
    const segments = try absoluteSegments(r, d.augment_path, d.augment_path_segments.items);
    return (try walkAbsoluteSchemaPath(r, ctx_module, d.augment_path, "augment", segments)).target;
}

/// Mark a node and its descendants as defined in `module_name` (RFC 7951 qualified names).
fn stampDefiningModule(s: *Statement, module_name: []const u8) void {
    if (s.hasWhen()) s.defining_module = module_name;
    for (s.statements.items) |child| stampDefiningModule(child, module_name);
    if (s.kind() == .choice) {
        for (s.data.choice.cases.items) |case| stampDefiningModule(case, module_name);
    }
}

fn mergeAugmentIntoTarget(r: *Reporter, aug: *Statement, target: *Statement, source_module: *Module) Error!void {
    const a = r.arena;
    const copies = try refine_expand.copyStatements(r, aug.statements.items);
    for (copies.items) |c| stampDefiningModule(c, source_module.name);
    try uses_expand.mergeIfFeaturesIntoRoots(a, copies.items, aug.if_features.items);
    try uses_expand.mergeWhenIntoRoots(a, copies.items, aug.when);
    for (copies.items) |c| {
        if (target.kind() == .choice and c.kind() == .case) {
            try target.data.choice.cases.append(a, c);
        } else {
            try target.statements.append(a, c);
        }
    }
}

/// `apply_augmentations`: merge each top-level `augment` (already `uses`-expanded) into its
/// target, in this module or an imported one, then drop the `augment` statements.
pub fn applyAugmentations(r: *Reporter, root: *Module) Error!void {
    var kept: StatementList = .empty;
    for (root.statements.items) |s| {
        if (s.kind() != .augment) try kept.append(r.arena, s);
    }
    if (kept.items.len == root.statements.items.len) return;
    const all = try root.statements.clone(r.arena);
    for (all.items) |s| {
        if (s.kind() != .augment) continue;
        const target = try resolveAugmentTarget(r, root, s);
        try mergeAugmentIntoTarget(r, s, target, root);
    }
    var out: StatementList = .empty;
    for (root.statements.items) |s| {
        if (s.kind() != .augment) try out.append(r.arena, s);
    }
    root.statements = out;
}

/// Drop `child` from `parent` (a choice keeps its cases in `cases`).
fn removeSchemaChild(r: *Reporter, parent: Owner, child: *Statement) Error!void {
    if (parent == .stmt and parent.stmt.kind() == .choice) {
        const cases = &parent.stmt.data.choice.cases;
        if (std.mem.indexOfScalar(*Statement, cases.items, child)) |i| {
            _ = cases.orderedRemove(i);
            if (std.mem.indexOfScalar(*Statement, parent.stmt.statements.items, child)) |j| _ = parent.stmt.statements.orderedRemove(j);
            return;
        }
    }
    const list = parent.statements();
    if (std.mem.indexOfScalar(*Statement, list.items, child)) |i| {
        _ = list.orderedRemove(i);
        return;
    }
    return r.fail(.semantic, "deviation: target node {f} is not a child of its parent", .{repr(child.name)});
}

/// Shallow copy with new child lists; descendants stay shared until copied.
fn cowStatement(a: std.mem.Allocator, s: *const Statement) Error!*Statement {
    const out = try a.create(Statement);
    out.* = s.*;
    out.statements = try s.statements.clone(a);
    if (out.kind() == .choice) out.data.choice.cases = try s.data.choice.cases.clone(a);
    return out;
}

const Slot = struct { cases: bool, index: usize };

fn schemaChildSlot(a: std.mem.Allocator, parent: Owner, name: []const u8) Error!?Slot {
    if (parent == .stmt and parent.stmt.kind() == .choice) {
        for (parent.stmt.data.choice.cases.items, 0..) |case, i| {
            if (std.mem.eql(u8, case.name, name) and case.schemaNode() != null) return .{ .cases = true, .index = i };
        }
    }
    for (parent.statements().items, 0..) |s, i| {
        if (std.mem.eql(u8, s.name, name) and s.schemaNode() != null) return .{ .cases = false, .index = i };
    }
    if (parent == .stmt) {
        if (try materializeOperationIo(a, parent.stmt, name)) |node| {
            return .{ .cases = false, .index = std.mem.indexOfScalar(*Statement, parent.stmt.statements.items, node).? };
        }
    }
    return null;
}

fn slotList(parent: Owner, slot: Slot) *StatementList {
    return if (slot.cases) &parent.stmt.data.choice.cases else parent.statements();
}

const Located = struct { owner: Owner, slot: Slot };

/// Copy the ancestors of the node `segments` name in a module copy; return the copied
/// parent and the target's slot in it. The target itself is not copied.
fn copiedPathToTarget(r: *Reporter, module: *Module, segments: []const IdentifierRef) Error!Located {
    const a = r.arena;
    var owner: Owner = .{ .module = module };
    var slot = (try schemaChildSlot(a, owner, segments[0].name)) orelse return missingOnPath(r, segments, segments[0].name, module.name);
    for (segments[1..]) |seg| {
        const current = try cowStatement(a, slotList(owner, slot).items[slot.index]);
        slotList(owner, slot).items[slot.index] = current;
        owner = .{ .stmt = current };
        slot = (try schemaChildSlot(a, owner, seg.name)) orelse return missingOnPath(r, segments, seg.name, current.name);
    }
    return .{ .owner = owner, .slot = slot };
}

fn missingOnPath(r: *Reporter, segments: []const IdentifierRef, name: []const u8, under: []const u8) Error {
    var joined: std.ArrayList(u8) = .empty;
    for (segments) |s| try joined.print(r.arena, "/{s}:{s}", .{ s.prefix orelse "None", s.name });
    return r.fail(.semantic, "deviation: no child {f} under {f} (path {f})", .{ repr(name), repr(under), repr(joined.items) });
}

const Copies = std.AutoArrayHashMapUnmanaged(*Module, *Module);

/// A module this build may edit: `root`, or a copy of an imported module made once and
/// rebound in `root`'s imports, so the parser cache keeps the original.
fn privateTargetModule(r: *Reporter, root: *Module, owner: *Module, copies: *Copies) Error!*Module {
    if (owner == root) return root;
    for (copies.values()) |cloned| if (cloned == owner) return owner;
    if (copies.get(owner)) |existing| return existing;
    const cloned = try owner.cowCopy(r.arena);
    try copies.put(r.arena, owner, cloned);
    for (root.import_prefixes.values()) |*mod| {
        if (mod.* == owner) mod.* = cloned;
    }
    return cloned;
}

/// YANG keyword of a schema node, for messages.
fn nodeKeyword(s: *const Statement) []const u8 {
    return switch (s.kind()) {
        .leaf_list => "leaf-list",
        else => @tagName(s.kind()),
    };
}

/// A `deviate` the target cannot take (RFC 7950 7.20.3.2): fail loudly, naming the deviation.
fn deviateFail(r: *Reporter, path: []const u8, comptime fmt: []const u8, args: anytype) Error {
    return r.fail(.semantic, "deviation {f}: " ++ fmt, .{repr(path)} ++ args);
}

fn requireKind(r: *Reporter, path: []const u8, node: *const Statement, prop: []const u8, ok: bool) Error!void {
    if (!ok) return deviateFail(r, path, "{s} does not apply to target {s} {f}", .{ prop, nodeKeyword(node), repr(node.name) });
}

/// `_single`: an `add` of a property the target has, or a `replace` of one it lacks, fails.
/// `always_present` properties (config, mandatory, min/max-elements) have an RFC default.
fn checkSingle(r: *Reporter, path: []const u8, node: *const Statement, dv: *const ast.Deviate, prop: []const u8, present: bool, always_present: bool) Error!void {
    if (dv.kind == .add and present) {
        return deviateFail(r, path, "cannot 'deviate add' {s}: target {s} {f} already has it (use 'deviate replace')", .{ prop, nodeKeyword(node), repr(node.name) });
    }
    if (dv.kind == .replace and !present and !always_present) {
        return deviateFail(r, path, "cannot 'deviate replace' {s}: target {s} {f} has no {s} (use 'deviate add')", .{ prop, nodeKeyword(node), repr(node.name), prop });
    }
}

fn applyDeviateDefaults(r: *Reporter, path: []const u8, node: *Statement, dv: *const ast.Deviate) Error!void {
    const a = r.arena;
    const values = dv.defaults.items;
    if (node.kind() == .leaf_list) {
        const d = &node.data.leaf_list;
        var current = try d.defaults.clone(a);
        switch (dv.kind) {
            .add => try current.appendSlice(a, values),
            .replace => {
                if (current.items.len == 0) return deviateFail(r, path, "cannot 'deviate replace' default: target leaf-list {f} has no default", .{repr(node.name)});
                current = .empty;
                try current.appendSlice(a, values);
            },
            .delete => for (values) |value| {
                const idx = for (current.items, 0..) |v, i| {
                    if (std.mem.eql(u8, v, value)) break i;
                } else return deviateFail(r, path, "cannot 'deviate delete' default {f}: target leaf-list {f} has no such default", .{ repr(value), repr(node.name) });
                _ = current.orderedRemove(idx);
            },
        }
        d.defaults = current;
        d.default_values = null;
        return;
    }
    const slot: *?[]const u8 = switch (node.data) {
        .leaf => |*d| &d.default,
        .choice => |*d| &d.default,
        else => return requireKind(r, path, node, "default", false),
    };
    if (values.len != 1) return deviateFail(r, path, "target {s} {f} takes one default, got {d}", .{ nodeKeyword(node), repr(node.name), values.len });
    if (dv.kind == .delete) {
        const matches = if (slot.*) |cur| std.mem.eql(u8, cur, values[0]) else false;
        if (!matches) {
            const current = if (slot.*) |cur| try std.fmt.allocPrint(r.arena, "{f}", .{repr(cur)}) else "None";
            return deviateFail(r, path, "cannot 'deviate delete' default {f}: target {s} {f} has default {s}", .{ repr(values[0]), nodeKeyword(node), repr(node.name), current });
        }
        slot.* = null;
        return;
    }
    try checkSingle(r, path, node, dv, "default", slot.* != null, false);
    slot.* = values[0];
}

fn applyDeviateMusts(r: *Reporter, path: []const u8, node: *Statement, dv: *const ast.Deviate) Error!void {
    try requireKind(r, path, node, "must", node.hasMust());
    var current = try node.must_statements.clone(r.arena);
    if (dv.kind == .add) {
        try current.appendSlice(r.arena, dv.must_statements.items);
    } else for (dv.must_statements.items) |must| {
        const idx = for (current.items, 0..) |m, i| {
            if (std.mem.eql(u8, m.expression, must.expression)) break i;
        } else return deviateFail(r, path, "cannot 'deviate delete' must {f}: target {s} {f} has no such must", .{ repr(must.expression), nodeKeyword(node), repr(node.name) });
        _ = current.orderedRemove(idx);
    }
    node.must_statements = current;
}

fn sameUnique(x: []const []const u8, y: []const []const u8) bool {
    if (x.len != y.len) return false;
    for (x, y) |p, q| if (!std.mem.eql(u8, p, q)) return false;
    return true;
}

fn applyDeviateUnique(r: *Reporter, path: []const u8, node: *Statement, dv: *const ast.Deviate) Error!void {
    try requireKind(r, path, node, "unique", node.kind() == .list);
    const d = &node.data.list;
    var current = try d.unique.clone(r.arena);
    if (dv.kind == .add) {
        try current.appendSlice(r.arena, dv.unique.items);
    } else for (dv.unique.items) |paths| {
        const idx = for (current.items, 0..) |u, i| {
            if (sameUnique(u, paths)) break i;
        } else {
            const joined = try std.mem.join(r.arena, " ", paths);
            return deviateFail(r, path, "cannot 'deviate delete' unique {f}: target list {f} has no such unique", .{ repr(joined), repr(node.name) });
        };
        _ = current.orderedRemove(idx);
    }
    d.unique = current;
}

/// `_apply_deviate`: one `deviate add|replace|delete` on `node` (RFC 7950 7.20.3.2).
fn applyDeviate(r: *Reporter, path: []const u8, node: *Statement, dv: *const ast.Deviate) Error!void {
    if (dv.config) |value| {
        try requireKind(r, path, node, "config", node.hasWhen() and node.kind() != .rpc and node.kind() != .action);
        try checkSingle(r, path, node, dv, "config", node.config != null, true);
        node.config = value;
    }
    if (dv.mandatory) |value| {
        const slot: *bool = switch (node.data) {
            .leaf => |*d| &d.mandatory,
            .choice => |*d| &d.mandatory,
            .anydata => |*d| &d.mandatory,
            .anyxml => |*d| &d.mandatory,
            else => return requireKind(r, path, node, "mandatory", false),
        };
        try checkSingle(r, path, node, dv, "mandatory", slot.*, true);
        slot.* = value;
    }
    if (dv.min_elements) |value| {
        const slot = if (node.kind() == .refine) null else node.minElementsSlot();
        try requireKind(r, path, node, "min-elements", slot != null);
        try checkSingle(r, path, node, dv, "min-elements", slot.?.* != null, true);
        slot.?.* = value;
    }
    if (dv.max_elements_set) {
        const slot = if (node.kind() == .refine) null else node.maxElementsSlot();
        try requireKind(r, path, node, "max-elements", slot != null);
        try checkSingle(r, path, node, dv, "max-elements", slot.?.* != null, true);
        slot.?.* = dv.max_elements;
    }
    if (dv.type) |t| {
        try requireKind(r, path, node, "type", node.kind() == .leaf or node.kind() == .leaf_list);
        node.typeSlot().?.* = t;
    }
    if (dv.units) |units| {
        try requireKind(r, path, node, "units", node.kind() == .leaf or node.kind() == .leaf_list);
        if (dv.kind == .delete) {
            if (!std.mem.eql(u8, node.units, units)) {
                return deviateFail(r, path, "cannot 'deviate delete' units {f}: target {s} {f} has units {f}", .{ repr(units), nodeKeyword(node), repr(node.name), repr(node.units) });
            }
            node.units = "";
        } else {
            try checkSingle(r, path, node, dv, "units", node.units.len > 0, false);
            node.units = units;
        }
    }
    if (dv.defaults.items.len > 0) try applyDeviateDefaults(r, path, node, dv);
    if (dv.must_statements.items.len > 0) try applyDeviateMusts(r, path, node, dv);
    if (dv.unique.items.len > 0) try applyDeviateUnique(r, path, node, dv);
}

fn applyDeviation(r: *Reporter, root: *Module, dev: *Statement, copies: *Copies) Error!void {
    const d = dev.data.deviation;
    const path = d.target_path;
    const segments = try absoluteSegments(r, path, d.target_path_segments.items);
    const walked = walkAbsoluteSchemaPath(r, root, path, "deviation", segments) catch |err| {
        if (err == error.YangLoad and r.diag.kind == .syntax) r.diag.kind = .semantic;
        return err;
    };
    const owner = root.resolvePrefixedModule(segments[0].prefix orelse "") orelse
        return r.fail(.semantic, "deviation: unknown prefix {f} in path {f}", .{ repr(segments[0].prefix orelse ""), repr(path) });
    var node = walked.target;
    if (owner == root) {
        if (d.not_supported) return removeSchemaChild(r, walked.parent, walked.target);
    } else {
        const private = try privateTargetModule(r, root, owner, copies);
        const at = try copiedPathToTarget(r, private, segments);
        const list = slotList(at.owner, at.slot);
        if (d.not_supported) {
            _ = list.orderedRemove(at.slot.index);
            return;
        }
        node = try cowStatement(r.arena, list.items[at.slot.index]);
        list.items[at.slot.index] = node;
    }
    for (d.deviates.items) |dv| try applyDeviate(r, path, node, dv);
}

/// `apply_deviations`: apply each `deviation` in order, then drop the `deviation`
/// statements. A target in another module is changed on a copy owned by `root`.
pub fn applyDeviations(r: *Reporter, root: *Module) Error!void {
    var pending: StatementList = .empty;
    for (root.statements.items) |s| {
        if (s.kind() == .deviation) try pending.append(r.arena, s);
    }
    if (pending.items.len == 0) return;
    var copies: Copies = .empty;
    for (pending.items) |dev| try applyDeviation(r, root, dev, &copies);
    var out: StatementList = .empty;
    for (root.statements.items) |s| {
        if (s.kind() != .deviation) try out.append(r.arena, s);
    }
    root.statements = out;
}

const yang_parser = @import("parser/yang_parser.zig");

test "augment merges into the target with if-feature and when" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const m = try yang_parser.parseString(arena.allocator(),
        \\module m { prefix m;
        \\  container top { choice c { case one { leaf a { type string; } } } }
        \\  augment "/m:top" { if-feature f; leaf b { type string; } }
        \\  augment "/m:top/m:c" { case two { leaf x { type string; } } }
        \\}
    , "m.yang", &diag);
    try std.testing.expectEqual(@as(usize, 1), m.statements.items.len);
    const top = m.statements.items[0];
    const b = top.statements.items[1];
    try std.testing.expectEqualStrings("b", b.name);
    try std.testing.expectEqualStrings("f", b.if_features.items[0]);
    try std.testing.expectEqualStrings("m", b.defining_module.?);
    try std.testing.expectEqual(@as(usize, 2), top.statements.items[0].data.choice.cases.items.len);
}

test "deviate not-supported removes the target; a missing target is an error" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const m = try yang_parser.parseString(arena.allocator(),
        \\module m { prefix m;
        \\  container top { leaf a { type string; } leaf b { type string; } }
        \\  deviation "/m:top/m:a" { deviate not-supported; }
        \\}
    , "m.yang", &diag);
    try std.testing.expectEqual(@as(usize, 1), m.statements.items.len);
    try std.testing.expectEqual(@as(usize, 1), m.statements.items[0].statements.items.len);
    try std.testing.expectError(error.YangLoad, yang_parser.parseString(arena.allocator(),
        \\module m { prefix m;
        \\  container top { }
        \\  deviation "/m:top/m:a" { deviate not-supported; }
        \\}
    , "m.yang", &diag));
    try std.testing.expectEqual(errors.Kind.semantic, diag.kind);
    try std.testing.expectEqualStrings("deviation: no child 'a' under node in path '/m:top/m:a' (after 'top')", diag.message);
}
