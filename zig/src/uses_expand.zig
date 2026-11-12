//! Expand `uses` and apply `refine` and `uses`-level `augment` (mirrors
//! `src/xyang/uses_expand.py`).

const std = @import("std");
const ast = @import("ast.zig");
const errors = @import("errors.zig");
const pyfmt = @import("pyfmt.zig");
const Module = @import("module.zig").Module;
const refine_expand = @import("refine_expand.zig");
const xpath_ast = @import("xpath/ast.zig");
const xpath = @import("xpath/xpath.zig");

const Statement = ast.Statement;
const Error = errors.Error;
const Reporter = errors.Reporter;
const repr = pyfmt.repr;
const Groupings = std.StringArrayHashMapUnmanaged(*Statement);
const StatementList = std.ArrayList(*Statement);

/// `ExpandUsesContext`.
const Ctx = struct {
    module: *Module,
    expanding_chain: []const []const u8 = &.{},
    refines: *StatementList,
    refine_path_prefix: []const u8 = "",
    typedef_target: ?*Module = null,
    /// Groupings in lexical scope (a container and its descendants), shadowing the module.
    local_groupings: ?*const Groupings = null,

    fn regModule(c: Ctx) *Module {
        return c.typedef_target orelse c.module;
    }

    fn child(c: Ctx, prefix: []const u8, local: ?*const Groupings) Ctx {
        return .{
            .module = c.module,
            .expanding_chain = c.expanding_chain,
            .refines = c.refines,
            .refine_path_prefix = prefix,
            .typedef_target = c.regModule(),
            .local_groupings = local,
        };
    }
};

fn extendRefinePath(a: std.mem.Allocator, prefix: []const u8, segment: []const u8) Error![]const u8 {
    if (prefix.len == 0) return segment;
    return std.fmt.allocPrint(a, "{s}/{s}", .{ prefix, segment });
}

/// Expose a grouping typedef on the module where `uses` is expanded (RFC 7950 scoping).
fn registerTypedefForUses(r: *Reporter, target: *Module, source: *Module, td: *Statement) Error!void {
    if (target.typedefs.contains(td.name)) return;
    const resolved = source.typedefs.get(td.name) orelse td;
    if (target == source) return target.typedefs.put(r.arena, td.name, resolved);
    try target.typedefs.put(r.arena, td.name, try refine_expand.copyStatement(r, resolved));
}

fn registerGroupingTypedefs(r: *Reporter, target: *Module, source: *Module, grouping: *Statement) Error!void {
    for (grouping.data.grouping.typedef_names.items) |name| {
        if (source.typedefs.get(name)) |td| try registerTypedefForUses(r, target, source, td);
    }
    for (grouping.statements.items) |s| {
        if (s.kind() == .typedef) try registerTypedefForUses(r, target, source, s);
    }
}

fn groupingBodyWithoutTypedefs(r: *Reporter, target: *Module, source: *Module, grouping: *Statement) Error!StatementList {
    try registerGroupingTypedefs(r, target, source, grouping);
    var out: StatementList = .empty;
    for (grouping.statements.items) |s| {
        if (s.kind() != .typedef) try out.append(r.arena, try refine_expand.copyStatement(r, s));
    }
    return out;
}

/// RFC 7950 7.13.1: `if-feature` on `uses` (or `augment`) ANDs with each root it adds.
pub fn mergeIfFeaturesIntoRoots(a: std.mem.Allocator, roots: []const *Statement, if_features: []const []const u8) Error!void {
    if (if_features.len == 0) return;
    for (roots) |node| {
        if (!node.hasWhen()) continue;
        var merged: ast.StringList = .empty;
        try merged.appendSlice(a, if_features);
        try merged.appendSlice(a, node.if_features.items);
        node.if_features = merged;
    }
}

/// RFC 7950 7.21.5: `when` on `uses` (or `augment`) is ANDed onto each root it adds and is
/// evaluated with the parent of that statement as the context node.
pub fn mergeWhenIntoRoots(a: std.mem.Allocator, roots: []const *Statement, uses_when: ?*ast.WhenStmt) Error!void {
    const uw = uses_when orelse return;
    uw.evaluate_with_parent_context = true;
    for (roots) |node| {
        if (!node.hasWhen()) continue;
        const old = node.when orelse {
            node.when = uw;
            continue;
        };
        const old_desc = std.mem.trim(u8, old.description, &refine_expand.pyWhitespace);
        const merged = try a.create(ast.WhenStmt);
        merged.* = .{
            .expression = try std.fmt.allocPrint(a, "({s}) and ({s})", .{ uw.expression, old.expression }),
            .description = if (old_desc.len > 0) old_desc else std.mem.trim(u8, uw.description, &refine_expand.pyWhitespace),
            .evaluate_with_parent_context = true,
        };
        if (uw.ast != null and old.ast != null) {
            // Keep each operand's prefix binding; re-parsing the text would lose it.
            const both = try a.create(xpath_ast.Expr);
            both.* = .{ .binary = .{ .left = uw.ast.?, .operator = "and", .right = old.ast.? } };
            merged.ast = both;
        }
        node.when = merged;
    }
}

/// True if a refine target matches the path of a statement: equal, or a suffix after `/`
/// (pending refines of an outer `uses` still match inside nested groupings).
fn refineTargetMatches(target: []const u8, stmt_path: []const u8) bool {
    if (stmt_path.len == 0 or target.len == 0) return false;
    if (std.mem.eql(u8, stmt_path, target)) return true;
    return stmt_path.len > target.len and std.mem.endsWith(u8, stmt_path, target) and stmt_path[stmt_path.len - target.len - 1] == '/';
}

/// Apply, then drop, every pending refine whose target matches `stmt_path`.
fn applyRefinesMatchingPath(a: std.mem.Allocator, s: *Statement, stmt_path: []const u8, refines: *StatementList) Error!void {
    var i = refines.items.len;
    while (i > 0) {
        i -= 1;
        const rf = refines.items[i];
        if (refineTargetMatches(rf.data.refine.target_path, stmt_path)) {
            try refine_expand.applyRefineToNode(a, s, rf);
            _ = refines.orderedRemove(i);
        }
    }
}

/// RFC 7950 7.17: merge `augment` substatements of `uses` into the expanded grouping.
fn applyUsesAugmentations(r: *Reporter, body: []const *Statement, uses: *Statement, grouping_name: []const u8) Error!void {
    const a = r.arena;
    for (uses.data.uses.augmentations.items) |aug| {
        const path = aug.data.augment.augment_path;
        var xp = try xpath.Parser.init(a, path);
        const parsed = xp.parsePath(true) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.UnsupportedNumber => return r.fail(.unsupported, "{s}", .{xp.message}),
            error.XPathSyntax, error.UnknownFunction => return r.fail(.syntax, "uses '{s}' augment: invalid path {f}: {s}", .{ grouping_name, repr(path), xp.message }),
        };
        var steps: std.ArrayList([]const u8) = .empty;
        for (parsed.path.segments) |seg| try steps.append(a, seg.step);
        const targets = try refine_expand.findNodesByRefinePath(a, body, steps.items);
        if (targets.len == 0) return r.fail(.syntax, "uses '{s}' augment: no target for path {f}", .{ grouping_name, repr(path) });
        if (targets.len != 1) {
            return r.fail(.syntax, "uses '{s}' augment: path {f} matched {d} nodes, expected one", .{ grouping_name, repr(path), targets.len });
        }
        const copies = try refine_expand.copyStatements(r, aug.statements.items);
        try mergeIfFeaturesIntoRoots(a, copies.items, aug.if_features.items);
        try mergeWhenIntoRoots(a, copies.items, aug.when);
        try targets[0].statements.appendSlice(a, copies.items);
    }
}

const Resolved = struct { qname: []const u8, module: *Module, grouping: *Statement };

/// The grouping a `uses` names: by prefix, else the lexical (container) scope, then the module.
fn resolveUsesGrouping(a: std.mem.Allocator, s: *Statement, ctx: Ctx) Error!?Resolved {
    const u = s.data.uses;
    const qname = if (u.grouping_prefix) |pre| try std.fmt.allocPrint(a, "{s}:{s}", .{ pre, u.grouping_name }) else u.grouping_name;
    var gmod: *Module = ctx.module;
    var grouping: ?*Statement = null;
    if (u.grouping_prefix) |pre| {
        gmod = ctx.module.resolvePrefixedModule(pre) orelse return null;
        grouping = gmod.groupings.get(u.grouping_name);
    } else {
        if (ctx.local_groupings) |local| grouping = local.get(u.grouping_name);
        if (grouping == null) grouping = gmod.groupings.get(u.grouping_name);
    }
    return .{ .qname = qname, .module = gmod, .grouping = grouping orelse return null };
}

fn expandOneUses(r: *Reporter, s: *Statement, ctx: Ctx) Error!StatementList {
    const a = r.arena;
    // Python logs a warning and drops the `uses`; the shared case
    // parser/substatements/container-grouping-hidden requires a load error (an `xfail` for
    // Python), so this port fails the way TypeScript does instead of dropping nodes.
    const resolved = try resolveUsesGrouping(a, s, ctx) orelse {
        const u = s.data.uses;
        if (u.grouping_prefix) |pre| {
            const qname = try std.fmt.allocPrint(a, "{s}:{s}", .{ pre, u.grouping_name });
            if (ctx.module.resolvePrefixedModule(pre) == null) {
                return r.fail(.semantic, "Unknown import prefix '{s}' in uses '{s}'", .{ pre, qname });
            }
            return r.fail(.semantic, "Unknown grouping '{s}'", .{qname});
        }
        return r.fail(.semantic, "Unknown grouping '{s}'", .{u.grouping_name});
    };
    for (ctx.expanding_chain) |name| {
        if (!std.mem.eql(u8, name, resolved.qname)) continue;
        const cycle = try std.mem.join(a, " -> ", ctx.expanding_chain);
        return r.fail(.semantic, "Circular uses chain: groupings are expanded at compile-time and this cycle would not terminate ({s} -> {s}). Restructure groupings to break the cycle.", .{ cycle, resolved.qname });
    }
    const chain = try std.mem.concat(a, []const u8, &.{ ctx.expanding_chain, &.{resolved.qname} });
    const body = try groupingBodyWithoutTypedefs(r, ctx.module, resolved.module, resolved.grouping);
    try mergeIfFeaturesIntoRoots(a, body.items, s.if_features.items);
    try mergeWhenIntoRoots(a, body.items, s.when);
    var pending = try s.data.uses.refines.clone(a);
    const inner: Ctx = .{
        .module = resolved.module,
        .expanding_chain = chain,
        .refines = &pending,
        .refine_path_prefix = if (ctx.refines.items.len > 0) ctx.refine_path_prefix else "",
        .typedef_target = ctx.module,
        .local_groupings = ctx.local_groupings,
    };
    const out = try expandUsesInStatements(r, body.items, inner);
    if (pending.items.len > 0) {
        return r.fail(.semantic, "Refine target path matches no node in the used grouping: {f}", .{repr(pending.items[0].data.refine.target_path)});
    }
    if (s.data.uses.augmentations.items.len > 0) try applyUsesAugmentations(r, out.items, s, resolved.qname);
    return out;
}

/// `expand_all_uses_in_module`: every `uses` in the module body and in each grouping.
pub fn expandAllUsesInModule(r: *Reporter, module: *Module) Error!void {
    var refines: StatementList = .empty;
    const root: Ctx = .{ .module = module, .refines = &refines };
    module.statements = try expandUsesInStatements(r, module.statements.items, root);
    for (module.groupings.values()) |g| g.statements = try expandUsesInStatements(r, g.statements.items, root);
}

/// `expand_uses_in_statements(statements, ctx=ExpandUsesContext(module=module))`.
pub fn expandUsesInStatementsOf(r: *Reporter, module: *Module, statements: []const *Statement) Error!StatementList {
    var refines: StatementList = .empty;
    return expandUsesInStatements(r, statements, .{ .module = module, .refines = &refines });
}

/// `expand_uses_in_statements`. Nested typedefs register on `ctx.typedef_target` when set.
fn expandUsesInStatements(r: *Reporter, statements: []const *Statement, ctx: Ctx) Error!StatementList {
    const a = r.arena;
    var expanded: StatementList = .empty;
    for (statements) |s| {
        const stmt_path = if (s.schemaNode()) |seg| try extendRefinePath(a, ctx.refine_path_prefix, seg) else ctx.refine_path_prefix;
        try applyRefinesMatchingPath(a, s, stmt_path, ctx.refines);
        switch (s.data) {
            .uses => {
                const body = try expandOneUses(r, s, ctx);
                const again = try expandUsesInStatements(r, body.items, ctx.child(stmt_path, ctx.local_groupings));
                try expanded.appendSlice(a, again.items);
            },
            .typedef => {
                if (ctx.typedef_target != null) {
                    try registerTypedefForUses(r, ctx.regModule(), ctx.module, s);
                } else {
                    try expanded.append(a, s);
                }
            },
            .choice => |*c| {
                for (c.cases.items) |case| {
                    const case_prefix = try extendRefinePath(a, stmt_path, case.name);
                    try applyRefinesMatchingPath(a, case, case_prefix, ctx.refines);
                    case.statements = try expandUsesInStatements(r, case.statements.items, ctx.child(case_prefix, ctx.local_groupings));
                }
                try expanded.append(a, s);
            },
            else => {
                var local = ctx.local_groupings;
                const own: ?*const Groupings = switch (s.data) {
                    .container, .notification, .input, .output => |*cd| &cd.groupings,
                    else => null,
                };
                if (own) |g| if (g.count() > 0) {
                    const merged = try a.create(Groupings);
                    merged.* = if (ctx.local_groupings) |l| try l.clone(a) else .empty;
                    for (g.keys(), g.values()) |k, v| try merged.put(a, k, v);
                    local = merged;
                };
                s.statements = try expandUsesInStatements(r, s.statements.items, ctx.child(stmt_path, local));
                try expanded.append(a, s);
            },
        }
    }
    return expanded;
}

const yang_parser = @import("parser/yang_parser.zig");

fn load(arena: std.mem.Allocator, source: []const u8, diag: *errors.Diagnostic) !*Module {
    return yang_parser.parseString(arena, source, "m.yang", diag);
}

test "uses expands the grouping with refine, if-feature and when" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const m = try load(arena.allocator(),
        \\module m { prefix m;
        \\  feature f;
        \\  grouping g { leaf a { type string; } container c { leaf b { type string; when "../a"; } } }
        \\  container top {
        \\    uses g { if-feature f; when "x"; refine "c/b" { mandatory true; description " refined "; } }
        \\  }
        \\}
    , &diag);
    const top = m.statements.items[0];
    try std.testing.expectEqual(@as(usize, 2), top.statements.items.len);
    const a = top.statements.items[0];
    try std.testing.expectEqualStrings("a", a.name);
    try std.testing.expectEqualStrings("f", a.if_features.items[0]);
    try std.testing.expectEqualStrings("x", a.when.?.expression);
    try std.testing.expect(a.when.?.evaluate_with_parent_context);
    const b = top.statements.items[1].statements.items[0];
    try std.testing.expect(b.data.leaf.mandatory);
    try std.testing.expectEqualStrings("refined", b.description);
    try std.testing.expectEqualStrings("../a", b.when.?.expression);
    // The grouping itself is unchanged.
    try std.testing.expect(!m.groupings.get("g").?.statements.items[1].statements.items[0].data.leaf.mandatory);
}

test "uses errors carry Python's text" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, load(arena.allocator(), "module m { prefix m; grouping a { uses b; } grouping b { uses a; } container t { uses a; } }", &diag));
    try std.testing.expectEqualStrings("Circular uses chain: groupings are expanded at compile-time and this cycle would not terminate (a -> b -> a). Restructure groupings to break the cycle.", diag.message);
    try std.testing.expectError(error.YangLoad, load(arena.allocator(), "module m { prefix m; grouping g { leaf a { type string; } } container t { uses g { refine nope { mandatory true; } } } }", &diag));
    try std.testing.expectEqualStrings("Refine target path matches no node in the used grouping: 'nope'", diag.message);
    try std.testing.expectError(error.YangLoad, load(arena.allocator(), "module m { prefix m; grouping g { leaf a { type string; } } container t { uses g { augment missing { leaf b { type string; } } } } }", &diag));
    try std.testing.expectEqualStrings("uses 'g' augment: no target for path 'missing'", diag.message);
}

test "a container-local grouping is visible inside the container only" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const m = try load(arena.allocator(), "module m { prefix m; container inner { grouping g { leaf x { type string; } } container deep { uses g; } } }", &diag);
    try std.testing.expectEqualStrings("x", m.statements.items[0].statements.items[0].statements.items[0].name);
    try std.testing.expectError(error.YangLoad, load(arena.allocator(),
        \\module m { prefix m;
        \\  container inner { grouping g { leaf x { type string; } } }
        \\  container outer { uses g; }
        \\}
    , &diag));
    try std.testing.expectEqualStrings("Unknown grouping 'g'", diag.message);
    try std.testing.expectError(error.YangLoad, load(arena.allocator(), "module m { prefix m; container t { uses x:g; } }", &diag));
    try std.testing.expectEqualStrings("Unknown import prefix 'x' in uses 'x:g'", diag.message);
}
