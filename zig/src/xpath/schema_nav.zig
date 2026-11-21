//! Schema navigation for XPath (mirrors `src/xyang/xpath/schema_nav.py`). All knowledge
//! of the schema object model the evaluator needs lives here. Groupings are expanded
//! when the module loads, so `uses` never appears.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const node_mod = @import("node.zig");
const utils = @import("utils.zig");
const xast = @import("ast.zig");

const Statement = ast.Statement;
const Schema = node_mod.Schema;

fn statementsOf(schema: Schema) []const *Statement {
    return switch (schema) {
        .none => &.{},
        .module => |m| m.statements.items,
        .stmt => |s| s.statements.items,
    };
}

/// Per-validation lookup table; the first matching statement preserves `find` order.
pub const Index = struct {
    owners: std.AutoHashMapUnmanaged(*const Statement, std.StringHashMapUnmanaged(*Statement)) = .empty,

    pub fn prepare(self: *Index, a: std.mem.Allocator, owner: *const Statement) error{OutOfMemory}!void {
        if (owner.statements.items.len == 0 or self.owners.contains(owner)) return;
        var names: std.StringHashMapUnmanaged(*Statement) = .empty;
        errdefer names.deinit(a);
        try collectNames(a, owner.statements.items, &names);
        try self.owners.put(a, owner, names);
    }
    pub fn deinit(self: *Index, a: std.mem.Allocator) void {
        var it = self.owners.valueIterator();
        while (it.next()) |names| names.deinit(a);
        self.owners.deinit(a);
        self.* = .{};
    }
};

fn collectNames(a: std.mem.Allocator, stmts: []const *Statement, names: *std.StringHashMapUnmanaged(*Statement)) error{OutOfMemory}!void {
    for (stmts) |s| {
        const entry = try names.getOrPut(a, s.name);
        if (!entry.found_existing) entry.value_ptr.* = s;
        switch (s.kind()) {
            .choice => for (s.data.choice.cases.items) |case| try collectNames(a, case.statements.items, names),
            .case => try collectNames(a, s.statements.items, names),
            else => {},
        }
    }
}

pub fn indexedChild(index: ?*const Index, schema: Schema, name: []const u8) ?*Statement {
    if (index) |idx| if (schema == .stmt) {
        if (idx.owners.get(schema.stmt)) |names| return names.get(name);
    };
    return child(schema, name);
}

/// `child`: the named child, looking through `choice` and `case` (no data of their own).
pub fn child(schema: Schema, name: []const u8) ?*Statement {
    return find(statementsOf(schema), name);
}

fn find(stmts: []const *Statement, name: []const u8) ?*Statement {
    for (stmts) |s| {
        if (std.mem.eql(u8, s.name, name)) return s;
        switch (s.kind()) {
            .choice => for (s.data.choice.cases.items) |case| {
                if (find(case.statements.items, name)) |found| return found;
            },
            .case => if (find(s.statements.items, name)) |found| return found,
            else => {},
        }
    }
    return null;
}

/// `child_in_module`: the data-node child `name` that `module` defines (its RFC 7951
/// namespace).
pub fn childInModule(schema: Schema, name: []const u8, module: []const u8, root_module: []const u8) ?*Statement {
    return findInModule(statementsOf(schema), name, module, root_module);
}

fn findInModule(stmts: []const *Statement, name: []const u8, module: []const u8, root_module: []const u8) ?*Statement {
    for (stmts) |s| {
        switch (s.kind()) {
            .choice => for (s.data.choice.cases.items) |case| {
                if (findInModule(case.statements.items, name, module, root_module)) |found| return found;
            },
            .case => if (findInModule(s.statements.items, name, module, root_module)) |found| return found,
            else => if (isDataNode(s) and std.mem.eql(u8, s.name, name) and
                std.mem.eql(u8, rfc7951.definingModuleName(s, root_module), module)) return s,
        }
    }
    return null;
}

fn isDataNode(s: *const Statement) bool {
    return switch (s.kind()) {
        .container, .list, .leaf, .leaf_list, .anydata, .anyxml => true,
        else => false,
    };
}

/// `data_children`: data-node children in schema order, through `choice` and `case`.
pub fn dataChildren(a: std.mem.Allocator, schema: Schema) error{OutOfMemory}![]const *Statement {
    var out: std.ArrayList(*Statement) = .empty;
    try collect(a, statementsOf(schema), &out);
    return out.items;
}

fn collect(a: std.mem.Allocator, stmts: []const *Statement, out: *std.ArrayList(*Statement)) error{OutOfMemory}!void {
    for (stmts) |s| {
        switch (s.kind()) {
            .choice => for (s.data.choice.cases.items) |case| try collect(a, case.statements.items, out),
            .case => try collect(a, s.statements.items, out),
            else => if (isDataNode(s)) try out.append(a, s),
        }
    }
}

/// `default`: a leaf's schema default as its built-in type's value, else null. A
/// leaf-list has no single `default` here, like Python's `getattr(schema, "default")`.
pub fn default(s: ?*const Statement) ?jv.Val {
    const stmt = s orelse return null;
    const leaf = switch (stmt.data) {
        .leaf => |d| d,
        else => return null,
    };
    const d = leaf.default orelse return null;
    const t = leaf.type orelse return .{ .string = d };
    return utils.coerceDefaultValue(d, t.name);
}

pub fn isList(schema: Schema) bool {
    return schema == .stmt and schema.stmt.kind() == .list;
}

pub fn isLeafList(schema: Schema) bool {
    return schema == .stmt and schema.stmt.kind() == .leaf_list;
}

/// `leafref_path`: the parsed `path` of a leaf whose type is written `leafref`.
pub fn leafrefPath(schema: Schema) ?*xast.Expr {
    if (schema != .stmt or schema.stmt.kind() != .leaf) return null;
    const t = schema.stmt.data.leaf.type orelse return null;
    if (!std.mem.eql(u8, t.name, "leafref")) return null;
    return t.pathAst();
}

test "indexed child lookup preserves choice traversal and first match" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module m { namespace 'urn:m'; prefix m; container top {
        \\ choice select { case a { leaf alpha { type string; } }
        \\ case b { leaf beta { type string; } } }
        \\ leaf gamma { type string; } } }
    , "test.yang", &diag);
    const top = module.statements.items[0];
    var index: Index = .{};
    defer index.deinit(a);
    try index.prepare(a, top);
    for ([_][]const u8{ "alpha", "beta", "gamma", "select", "missing" }) |name| {
        try std.testing.expectEqual(child(.{ .stmt = top }, name), indexedChild(&index, .{ .stmt = top }, name));
    }
}
