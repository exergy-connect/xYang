//! Statement copies, descendant-path lookup and `refine` application for `uses`
//! expansion (mirrors `src/xyang/refine_expand.py`).

const std = @import("std");
const ast = @import("ast.zig");
const errors = @import("errors.zig");

const Statement = ast.Statement;
const Error = errors.Error;
const Allocator = std.mem.Allocator;

/// `copy_yang_statement`: a deep copy of the statement tree. Like Python's
/// `dataclasses.replace`, `type`, `when` and the must statements stay shared; the lists a
/// later pass extends (children, cases, must, if-feature, uses augments) are new.
pub fn copyStatement(r: *errors.Reporter, s: *const Statement) Error!*Statement {
    const a = r.arena;
    const out = try a.create(Statement);
    out.* = s.*;
    out.statements = try copyStatements(r, s.statements.items);
    switch (out.data) {
        .choice => |*c| {
            var cases: std.ArrayList(*Statement) = .empty;
            for (c.cases.items) |case| try cases.append(a, try copyStatement(r, case));
            c.cases = cases;
            out.if_features = try s.if_features.clone(a);
        },
        .uses => |*u| {
            u.refines = try u.refines.clone(a);
            var augs: std.ArrayList(*Statement) = .empty;
            for (u.augmentations.items) |aug| try augs.append(a, try copyStatement(r, aug));
            u.augmentations = augs;
            out.if_features = try s.if_features.clone(a);
        },
        .case, .augment => out.if_features = try s.if_features.clone(a),
        .container, .notification, .input, .output, .rpc, .action, .list, .leaf, .leaf_list, .anydata, .anyxml, .extension_invocation => {
            out.must_statements = try s.must_statements.clone(a);
            out.if_features = try s.if_features.clone(a);
        },
        .extension, .typedef => {},
        .identity, .grouping, .deviation, .refine => return r.fail(.semantic, "Unsupported statement type for copy: {s}", .{@tagName(s.kind())}),
    }
    return out;
}

pub fn copyStatements(r: *errors.Reporter, items: []const *Statement) Error!std.ArrayList(*Statement) {
    var out: std.ArrayList(*Statement) = .empty;
    try out.ensureTotalCapacity(r.arena, items.len);
    for (items) |s| out.appendAssumeCapacity(try copyStatement(r, s));
    return out;
}

/// `statement_children`: direct schema children; a choice flattens to its case bodies.
pub fn statementChildren(a: Allocator, s: *const Statement) Error![]const *Statement {
    switch (s.data) {
        .choice => |c| {
            var out: std.ArrayList(*Statement) = .empty;
            for (c.cases.items) |case| try out.appendSlice(a, case.statements.items);
            return out.items;
        },
        else => return s.statements.items,
    }
}

/// `find_nodes_by_refine_path`: resolve a descendant path (`a/b/c`) from the roots,
/// walking through choices and cases. Steps compare to names verbatim, prefix included.
pub fn findNodesByRefinePath(a: Allocator, roots: []const *Statement, segments: []const []const u8) Error![]const *Statement {
    var out: std.ArrayList(*Statement) = .empty;
    if (segments.len == 0) return out.items;
    for (roots) |root| try findFromNode(a, root, segments, 0, &out);
    return out.items;
}

fn findFromNode(a: Allocator, s: *Statement, segments: []const []const u8, idx: usize, out: *std.ArrayList(*Statement)) Error!void {
    const want = segments[idx];
    const last = idx == segments.len - 1;
    if (std.mem.eql(u8, s.name, want)) {
        if (last) return out.append(a, s);
        // A path may name the case after the choice; statement_children() drops cases.
        if (s.kind() == .choice and idx + 1 < segments.len) {
            const case_name = segments[idx + 1];
            var matches: std.ArrayList(*Statement) = .empty;
            for (s.data.choice.cases.items) |case| {
                if (!std.mem.eql(u8, case.name, case_name)) continue;
                if (idx + 1 == segments.len - 1) {
                    try out.append(a, case);
                    return;
                }
                for (case.statements.items) |ch| try findFromNode(a, ch, segments, idx + 2, &matches);
            }
            return out.appendSlice(a, matches.items);
        }
        for (try statementChildren(a, s)) |ch| try findFromNode(a, ch, segments, idx + 1, out);
        return;
    }
    if (s.kind() == .choice) {
        for (s.data.choice.cases.items) |case| {
            if (!std.mem.eql(u8, case.name, want)) continue;
            if (last) return out.append(a, case);
            for (case.statements.items) |ch| try findFromNode(a, ch, segments, idx + 1, out);
            return;
        }
    }
    for (try statementChildren(a, s)) |ch| try findFromNode(a, ch, segments, idx, out);
}

/// `apply_refine_to_node`: apply one `refine` to a resolved schema node.
pub fn applyRefineToNode(a: Allocator, s: *Statement, refine: *const Statement) Error!void {
    const rf = refine.data.refine;
    if (rf.type) |t| switch (s.data) {
        .leaf => |*d| d.type = t,
        else => {},
    };
    if (rf.refined_config) |rc| switch (s.kind()) {
        .container, .notification, .input, .output, .list, .leaf, .leaf_list => s.config = rc,
        else => {},
    };
    if (rf.refined_mandatory) |rm| switch (s.data) {
        .leaf => |*d| d.mandatory = rm,
        .choice => |*d| d.mandatory = rm,
        else => {},
    };
    if (rf.refined_defaults.items.len > 0) switch (s.data) {
        .leaf => |*d| d.default = rf.refined_defaults.items[0],
        .leaf_list => |*d| d.defaults = try rf.refined_defaults.clone(a),
        else => {},
    };
    if (s.hasMust()) try s.must_statements.appendSlice(a, refine.must_statements.items);
    switch (s.kind()) {
        .list, .leaf_list => {
            if (rf.min_elements) |v| s.minElementsSlot().?.* = v;
            if (rf.max_elements) |v| s.maxElementsSlot().?.* = v;
        },
        else => {},
    }
    if (refine.if_features.items.len > 0 and s.hasWhen()) try s.if_features.appendSlice(a, refine.if_features.items);
    const desc = std.mem.trim(u8, refine.description, &pyWhitespace);
    if (desc.len > 0) s.description = desc;
}

/// The characters Python's `str.strip()` removes in the ASCII range.
pub const pyWhitespace = [_]u8{ ' ', '\t', '\n', '\r', 0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x1f };

test "copies are independent where later passes write" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    var r: errors.Reporter = .{ .arena = a, .diag = &diag };
    const leaf = try a.create(Statement);
    leaf.* = .{ .name = "x", .data = .{ .leaf = .{} } };
    const top = try a.create(Statement);
    top.* = .{ .name = "top", .data = .{ .container = .{} } };
    try top.statements.append(a, leaf);
    const copy = try copyStatement(&r, top);
    try copy.statements.items[0].if_features.append(a, "f");
    try std.testing.expect(copy.statements.items[0] != leaf);
    try std.testing.expectEqual(@as(usize, 0), leaf.if_features.items.len);
    const found = try findNodesByRefinePath(a, &.{copy}, &.{ "top", "x" });
    try std.testing.expectEqual(@as(usize, 1), found.len);
    try std.testing.expect(found[0] == copy.statements.items[0]);
}
