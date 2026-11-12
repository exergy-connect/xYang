//! Resolve RFC 7950 `augment` targets, merge augmented schema into the target module
//! (this module's tree or an imported one), and apply `deviate not-supported` (mirrors
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

fn findNamedSchemaChild(parent: *Statement, name: []const u8) ?*Statement {
    if (parent.kind() == .choice) {
        for (parent.data.choice.cases.items) |case| {
            if (std.mem.eql(u8, case.name, name)) return case;
        }
        return null;
    }
    for (parent.statements.items) |s| {
        if (std.mem.eql(u8, s.name, name) and s.schemaNode() != null) return s;
    }
    return null;
}

const Walked = struct { parent: Owner, target: *Statement };

/// `_walk_absolute_schema_path`: `/prefix:name/...` to `(parent, target)`. Every prefix
/// must be bound in `ctx_module`; children are matched by name, through choices and cases.
fn walkAbsoluteSchemaPath(r: *Reporter, ctx_module: *Module, path: []const u8, kind: []const u8, segments: []const IdentifierRef) Error!Walked {
    const first = segments[0];
    const pref0 = first.prefix orelse "";
    if (pref0.len == 0) return r.fail(.syntax, "{s}: invalid first segment in path {f} (expected 'prefix:identifier')", .{ kind, repr(path) });
    const mod0 = ctx_module.resolvePrefixedModule(pref0) orelse
        return r.fail(.syntax, "{s}: unknown prefix {f} in path {f} (module {f})", .{ kind, repr(pref0), repr(path), repr(ctx_module.name) });
    var cur = findToplevelSchemaChild(mod0, first.name) orelse
        return r.fail(.syntax, "{s}: no top-level schema node {f} in module {f} (path {f})", .{ kind, repr(first.name), repr(mod0.name), repr(path) });
    var parent: Owner = .{ .module = mod0 };
    for (segments[1..]) |seg| {
        const pref = seg.prefix orelse "";
        if (pref.len == 0) return r.fail(.syntax, "{s}: invalid path segment {f} in path {f} (expected 'prefix:identifier')", .{ kind, repr(seg.name), repr(path) });
        if (ctx_module.resolvePrefixedModule(pref) == null) return r.fail(.syntax, "{s}: unknown prefix {f} in path {f}", .{ kind, repr(pref), repr(path) });
        const nxt = findNamedSchemaChild(cur, seg.name) orelse
            return r.fail(.syntax, "{s}: no child {f} under node in path {f} (after {f})", .{ kind, repr(seg.name), repr(path), repr(cur.name) });
        parent = .{ .stmt = cur };
        cur = nxt;
    }
    return .{ .parent = parent, .target = cur };
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

fn schemaChildSlot(parent: Owner, name: []const u8) ?Slot {
    if (parent == .stmt and parent.stmt.kind() == .choice) {
        for (parent.stmt.data.choice.cases.items, 0..) |case, i| {
            if (std.mem.eql(u8, case.name, name) and case.schemaNode() != null) return .{ .cases = true, .index = i };
        }
    }
    for (parent.statements().items, 0..) |s, i| {
        if (std.mem.eql(u8, s.name, name) and s.schemaNode() != null) return .{ .cases = false, .index = i };
    }
    return null;
}

fn slotList(parent: Owner, slot: Slot) *StatementList {
    return if (slot.cases) &parent.stmt.data.choice.cases else parent.statements();
}

/// Remove the node named by `segments` from a module copy, copying its ancestors only.
fn detachCopiedPath(r: *Reporter, module: *Module, segments: []const IdentifierRef) Error!void {
    const a = r.arena;
    const root: Owner = .{ .module = module };
    var slot = schemaChildSlot(root, segments[0].name) orelse {
        var joined: std.ArrayList(u8) = .empty;
        for (segments, 0..) |s, i| {
            if (i != 0) try joined.append(a, '/');
            try joined.print(a, "{s}:{s}", .{ s.prefix orelse "None", s.name });
        }
        return r.fail(.semantic, "deviation: no schema node for path '/{s}'", .{joined.items});
    };
    if (segments.len == 1) {
        _ = slotList(root, slot).orderedRemove(slot.index);
        return;
    }
    var current = try cowStatement(a, slotList(root, slot).items[slot.index]);
    slotList(root, slot).items[slot.index] = current;
    for (segments[1 .. segments.len - 1]) |seg| {
        const owner: Owner = .{ .stmt = current };
        slot = schemaChildSlot(owner, seg.name) orelse
            return r.fail(.semantic, "deviation: no child {f} under {f}", .{ repr(seg.name), repr(current.name) });
        const nxt = try cowStatement(a, slotList(owner, slot).items[slot.index]);
        slotList(owner, slot).items[slot.index] = nxt;
        current = nxt;
    }
    const owner: Owner = .{ .stmt = current };
    const last = segments[segments.len - 1];
    slot = schemaChildSlot(owner, last.name) orelse
        return r.fail(.semantic, "deviation: no child {f} under {f}", .{ repr(last.name), repr(current.name) });
    _ = slotList(owner, slot).orderedRemove(slot.index);
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

fn applyNotSupported(r: *Reporter, root: *Module, dev: *Statement, copies: *Copies) Error!void {
    const d = dev.data.deviation;
    const path = d.target_path;
    const segments = try absoluteSegments(r, path, d.target_path_segments.items);
    const walked = walkAbsoluteSchemaPath(r, root, path, "deviation", segments) catch |err| {
        if (err == error.YangLoad and r.diag.kind == .syntax) r.diag.kind = .semantic;
        return err;
    };
    const owner = root.resolvePrefixedModule(segments[0].prefix orelse "") orelse
        return r.fail(.semantic, "deviation: unknown prefix {f} in path {f}", .{ repr(segments[0].prefix orelse ""), repr(path) });
    if (owner == root) return removeSchemaChild(r, walked.parent, walked.target);
    const private = try privateTargetModule(r, root, owner, copies);
    try detachCopiedPath(r, private, segments);
}

/// `apply_deviations`: remove each `deviate not-supported` target, then drop the
/// `deviation` statements. `deviate add|replace|delete` were reported as warnings when
/// parsed and are not applied.
pub fn applyDeviations(r: *Reporter, root: *Module) Error!void {
    var pending: StatementList = .empty;
    for (root.statements.items) |s| {
        if (s.kind() == .deviation) try pending.append(r.arena, s);
    }
    if (pending.items.len == 0) return;
    var copies: Copies = .empty;
    for (pending.items) |dev| {
        if (dev.data.deviation.not_supported) try applyNotSupported(r, root, dev, &copies);
    }
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
