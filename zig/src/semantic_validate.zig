//! Semantic checks on the effective schema after `uses`, `augment` and `deviation`
//! (mirrors `src/xyang/semantic_validate.py`).

const std = @import("std");
const ast = @import("ast.zig");
const errors = @import("errors.zig");
const pyfmt = @import("pyfmt.zig");
const Module = @import("module.zig").Module;

const Statement = ast.Statement;
const Error = errors.Error;
const repr = pyfmt.repr;

pub fn validateSemantics(r: *errors.Reporter, module: *Module) Error!void {
    try validateListKeys(r, module.statements.items);
}

/// RFC 7950 7.8.2: every key names a child leaf, and a key leaf has no `when` or `if-feature`.
fn validateListKeys(r: *errors.Reporter, statements: []const *Statement) Error!void {
    for (statements) |s| {
        if (s.data == .list) try checkListKeys(r, s);
        if (s.kind() == .choice) {
            for (s.data.choice.cases.items) |case| try validateListKeys(r, case.statements.items);
        }
        try validateListKeys(r, s.statements.items);
    }
}

fn checkListKeys(r: *errors.Reporter, list: *Statement) Error!void {
    const key = list.data.list.key orelse return;
    var it = std.mem.tokenizeAny(u8, key, &std.ascii.whitespace);
    while (it.next()) |key_name| {
        var child: ?*Statement = null;
        for (list.statements.items) |c| {
            if (c.kind() == .leaf and std.mem.eql(u8, c.name, key_name)) child = c;
        }
        const leaf = child orelse return r.fail(
            .semantic,
            "List {f}: key leaf {f} does not exist (RFC 7950: each list key name must refer to a child leaf).",
            .{ repr(list.name), repr(key_name) },
        );
        const illegal: []const u8 = if (leaf.when != null) "when" else if (leaf.if_features.items.len > 0) "if-feature" else continue;
        return r.fail(
            .semantic,
            "List {f}: key leaf {f} must not have {f} (RFC 7950: 'when' and 'if-feature' are illegal on list keys).",
            .{ repr(list.name), repr(leaf.name), repr(illegal) },
        );
    }
}

test "list key checks" {
    const yang_parser = @import("parser/yang_parser.zig");
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, yang_parser.parseString(arena.allocator(), "module m { prefix m; list items { key \"missing\"; leaf name { type string; } } }", "m.yang", &diag));
    try std.testing.expectEqualStrings("List 'items': key leaf 'missing' does not exist (RFC 7950: each list key name must refer to a child leaf).", diag.message);
    try std.testing.expectError(error.YangLoad, yang_parser.parseString(arena.allocator(), "module m { prefix m; list items { key name; leaf name { type string; when \"1\"; } } }", "m.yang", &diag));
    try std.testing.expectEqualStrings("List 'items': key leaf 'name' must not have 'when' (RFC 7950: 'when' and 'if-feature' are illegal on list keys).", diag.message);
}
