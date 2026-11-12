//! Core objects for XPath evaluation (mirrors `src/xyang/xpath/node.py`).
//!
//! `Context` (current, root) is fixed for one expression evaluation. `Node` (data,
//! schema, parent) is the cursor, created on every path step.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const Module = @import("../module.zig").Module;

/// The schema object of a `Node`: the module at the root, a statement, or none (an
/// unknown member, or a value checked outside the tree).
pub const Schema = union(enum) {
    none,
    module: *Module,
    stmt: *ast.Statement,
};

pub const Node = struct {
    data: jv.Val,
    schema: Schema,
    parent: ?*const Node = null,

    /// `step`: a child one step down, with this node as parent.
    pub fn step(self: *const Node, a: std.mem.Allocator, data: jv.Val, schema: Schema) error{OutOfMemory}!*const Node {
        const out = try a.create(Node);
        out.* = .{ .data = data, .schema = schema, .parent = self };
        return out;
    }
};

pub const Context = struct {
    /// What `current()` returns: the node being validated.
    current: ?*const Node,
    /// Entry point for absolute paths.
    root: *const Node,

    pub fn child(self: Context, current: *const Node) Context {
        return .{ .current = current, .root = self.root };
    }
};

/// An evaluation result, as Python types it: a scalar (`str`, `int`, `float`, `bool`,
/// `None`), a node-set (`list[Node]`), one `Node` (`current()`), or a value-list `tuple`.
pub const Value = union(enum) {
    scalar: jv.Val,
    nodes: []const *const Node,
    node: *const Node,
    tuple: []const @import("ast.zig").Literal,

    pub const none: Value = .{ .scalar = .null };

    pub fn boolean(b: bool) Value {
        return .{ .scalar = .{ .bool = b } };
    }
};

pub fn newNode(a: std.mem.Allocator, data: jv.Val, schema: Schema, parent: ?*const Node) error{OutOfMemory}!*const Node {
    const out = try a.create(Node);
    out.* = .{ .data = data, .schema = schema, .parent = parent };
    return out;
}
