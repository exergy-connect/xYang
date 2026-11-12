//! AST nodes for XPath expressions (mirrors `src/xyang/xpath/ast.py`).

const std = @import("std");
const jv = @import("../json_value.zig");

const Allocator = std.mem.Allocator;

/// A `LiteralNode` value: Python `str`, `int`, `float`, `bool`, or a value-list `tuple`.
pub const Literal = union(enum) {
    string: []const u8,
    int: i128,
    float: f64,
    boolean: bool,
    tuple: []const Literal,

    /// The value as instance data compares it; a nested tuple is its Python `repr`.
    pub fn toVal(self: Literal, a: Allocator) error{OutOfMemory}!jv.Val {
        return switch (self) {
            .string => |s| .{ .string = s },
            .int => |i| .{ .int = i },
            .float => |f| .{ .float = f },
            .boolean => |b| .{ .bool = b },
            .tuple => .{ .string = try self.reprAlloc(a) },
        };
    }

    /// Python `repr` of the value.
    pub fn reprAlloc(self: Literal, a: Allocator) error{OutOfMemory}![]const u8 {
        var out: std.Io.Writer.Allocating = .init(a);
        self.writeRepr(&out.writer) catch return error.OutOfMemory;
        return out.written();
    }

    fn writeRepr(self: Literal, w: *std.Io.Writer) std.Io.Writer.Error!void {
        switch (self) {
            .string => |s| try w.print("{f}", .{@import("../pyfmt.zig").repr(s)}),
            .int => |i| try w.print("{d}", .{i}),
            .float => |f| try w.print("{f}", .{jv.floatRepr(f)}),
            .boolean => |b| try w.writeAll(if (b) "True" else "False"),
            .tuple => |items| {
                try w.writeByte('(');
                for (items, 0..) |item, i| {
                    if (i > 0) try w.writeAll(", ");
                    try item.writeRepr(w);
                }
                if (items.len == 1) try w.writeByte(',');
                try w.writeByte(')');
            },
        }
    }
};

pub const Segment = struct {
    step: []const u8,
    predicate: ?*Expr = null,
    /// Module a `prefix:name` or `prefix:*` step is bound to (`bind_xpath_prefixes`), from
    /// the prefixes of the module that wrote the expression (RFC 7950 6.4.1).
    module: ?[]const u8 = null,

    /// Lexical prefix of a `prefix:name` or `prefix:*` step.
    pub fn prefix(self: Segment) ?[]const u8 {
        if (std.mem.eql(u8, self.step, ".") or std.mem.eql(u8, self.step, "..")) return null;
        const colon = std.mem.indexOfScalar(u8, self.step, ':') orelse return null;
        return self.step[0..colon];
    }

    /// Local name (`name` for `prefix:name`).
    pub fn local(self: Segment) []const u8 {
        const colon = std.mem.indexOfScalar(u8, self.step, ':') orelse return self.step;
        return self.step[colon + 1 ..];
    }

    /// `*` or `prefix:*` (XPath 1.0 NameTest).
    pub fn isWildcard(self: Segment) bool {
        return std.mem.eql(u8, self.step, "*") or std.mem.endsWith(u8, self.step, ":*");
    }
};

pub const Path = struct {
    segments: []Segment,
    is_absolute: bool = false,

    /// `to_string`: the steps without predicates, for messages.
    pub fn toString(self: *const Path, a: Allocator) error{OutOfMemory}![]const u8 {
        var out: std.ArrayList(u8) = .empty;
        if (self.is_absolute) try out.append(a, '/');
        for (self.segments, 0..) |seg, i| {
            if (i > 0) try out.append(a, '/');
            try out.appendSlice(a, seg.step);
        }
        return out.items;
    }
};

pub const Binary = struct {
    left: *Expr,
    operator: []const u8,
    right: *Expr,
};

pub const Call = struct {
    name: []const u8,
    args: []*Expr,
};

pub const Expr = union(enum) {
    literal: Literal,
    path: Path,
    binary: Binary,
    call: Call,
};
