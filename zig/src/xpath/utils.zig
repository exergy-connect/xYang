//! YANG boolean coercion, node-set helpers and comparisons (mirrors
//! `src/xyang/xpath/utils.py`), with Python's `float()`, `int()`, `str()` conversions.

const std = @import("std");
const jv = @import("../json_value.zig");
const registry = @import("../types/registry.zig");
const node_mod = @import("node.zig");
const pychars = @import("pychars.zig");

const Allocator = std.mem.Allocator;
const Val = jv.Val;
const Value = node_mod.Value;
const Node = node_mod.Node;

/// Python `float(text)` for a `str`, or null where it raises `ValueError`.
pub fn pyFloatText(text: []const u8) ?f64 {
    var s = pychars.strip(text);
    var negative = false;
    if (s.len > 0 and (s[0] == '+' or s[0] == '-')) {
        negative = s[0] == '-';
        s = s[1..];
    }
    const special: ?f64 = if (std.ascii.eqlIgnoreCase(s, "inf") or std.ascii.eqlIgnoreCase(s, "infinity"))
        std.math.inf(f64)
    else if (std.ascii.eqlIgnoreCase(s, "nan"))
        std.math.nan(f64)
    else
        null;
    if (special) |f| return if (negative) -f else f;
    var buf: [128]u8 = undefined;
    var n: usize = 0;
    var i: usize = 0;
    var mantissa_digits: usize = 0;
    // digitpart ["." [digitpart]] | "." digitpart, then [("e"|"E") [sign] digitpart]
    const Scan = struct {
        fn digits(str: []const u8, at: *usize, out: []u8, len: *usize) ?usize {
            var count: usize = 0;
            while (at.* < str.len) {
                const c = str[at.*];
                if (std.ascii.isDigit(c)) {
                    if (len.* >= out.len) return null;
                    out[len.*] = c;
                    len.* += 1;
                    count += 1;
                    at.* += 1;
                } else if (c == '_' and count > 0 and at.* + 1 < str.len and std.ascii.isDigit(str[at.* + 1])) {
                    at.* += 1;
                } else break;
            }
            return count;
        }
    };
    mantissa_digits += Scan.digits(s, &i, &buf, &n) orelse return null;
    if (i < s.len and s[i] == '.') {
        if (n >= buf.len) return null;
        buf[n] = '.';
        n += 1;
        i += 1;
        mantissa_digits += Scan.digits(s, &i, &buf, &n) orelse return null;
    }
    if (mantissa_digits == 0) return null;
    if (i < s.len and (s[i] == 'e' or s[i] == 'E')) {
        if (n + 2 >= buf.len) return null;
        buf[n] = 'e';
        n += 1;
        i += 1;
        if (i < s.len and (s[i] == '+' or s[i] == '-')) {
            buf[n] = s[i];
            n += 1;
            i += 1;
        }
        if ((Scan.digits(s, &i, &buf, &n) orelse return null) == 0) return null;
    }
    if (i != s.len) return null;
    const f = std.fmt.parseFloat(f64, buf[0..n]) catch return null;
    return if (negative) -f else f;
}

/// Python `float(v)` for an instance value, or null where it raises.
pub fn pyFloat(v: Val) ?f64 {
    return switch (v) {
        .bool => |b| if (b) 1.0 else 0.0,
        .int => |i| @floatFromInt(i),
        .float => |f| f,
        .decimal => |d| d.toFloat(),
        .string => |s| pyFloatText(s),
        .null, .array, .object => null,
    };
}

/// Python `int(text)`: surrounding whitespace, a sign and `_` between digits.
pub fn pyInt(text: []const u8) ?i128 {
    const t = std.mem.trim(u8, text, &std.ascii.whitespace);
    var body = t;
    if (body.len > 0 and (body[0] == '+' or body[0] == '-')) body = body[1..];
    if (body.len == 0 or body[0] == '_' or body[body.len - 1] == '_') return null;
    var prev_us = false;
    for (body) |c| {
        if (c == '_') {
            if (prev_us) return null;
            prev_us = true;
            continue;
        }
        prev_us = false;
        if (!std.ascii.isDigit(c)) return null;
    }
    return std.fmt.parseInt(i128, t, 10) catch null;
}

/// `coerce_default_value`: a schema default as the Python value of its built-in type,
/// so path comparisons work when a leaf is defaulted.
pub fn coerceDefaultValue(d: []const u8, type_name: []const u8) Val {
    if (std.mem.eql(u8, type_name, registry.BOOLEAN)) {
        if (std.mem.eql(u8, d, "true")) return .{ .bool = true };
        if (std.mem.eql(u8, d, "false")) return .{ .bool = false };
    }
    if (registry.get(type_name)) |b| if (b.bounds != null) {
        if (pyInt(d)) |i| return .{ .int = i };
    };
    if (registry.isDecimalName(type_name)) {
        if (pyFloatText(d)) |f| return .{ .float = f };
    }
    return .{ .string = d };
}

/// `yang_bool` on an instance value (`isinstance` order of the Python function).
pub fn valBool(v: Val) bool {
    return switch (v) {
        .null => false,
        .bool => |b| b,
        .int => |i| i != 0,
        .float => |f| f != 0,
        .string => |s| s.len > 0,
        .array => |items| items.len > 0,
        .decimal, .object => true,
    };
}

/// `yang_bool`.
pub fn yangBool(v: Value) bool {
    return switch (v) {
        .scalar => |s| valBool(s),
        .nodes => |ns| ns.len > 0,
        .node, .tuple => true,
    };
}

pub fn isNodeset(v: Value) bool {
    return v == .nodes;
}

/// `node_set_values`: data of a node-set or `Node`, or the scalar itself (none for `None`).
/// A tuple is one value, compared as its Python `str`.
pub fn nodeSetValues(a: Allocator, v: Value) error{OutOfMemory}![]const Val {
    switch (v) {
        .nodes => |ns| {
            const out = try a.alloc(Val, ns.len);
            for (ns, 0..) |n, i| out[i] = n.data;
            return out;
        },
        .node => |n| return try a.dupe(Val, &.{n.data}),
        .scalar => |s| return if (s == .null) &.{} else try a.dupe(Val, &.{s}),
        .tuple => |items| {
            const lit: @import("ast.zig").Literal = .{ .tuple = items };
            return try a.dupe(Val, &.{.{ .string = try lit.reprAlloc(a) }});
        },
    }
}

/// `first_value`.
pub fn firstValue(a: Allocator, v: Value) error{OutOfMemory}!Val {
    const vs = try nodeSetValues(a, v);
    return if (vs.len > 0) vs[0] else .null;
}

/// Python `str(v)`.
pub fn pyStr(a: Allocator, v: Val) error{OutOfMemory}![]const u8 {
    if (v == .string) return v.string;
    return std.fmt.allocPrint(a, "{f}", .{jv.pyStr(v)});
}

const Pair = union(enum) {
    bools: [2]bool,
    floats: [2]f64,
    strings: [2][]const u8,
};

/// `coerce_pair`: both as booleans when either is one, else both as floats, else both as
/// stripped strings.
fn coercePair(a: Allocator, l: Val, r: Val) error{OutOfMemory}!Pair {
    if (l == .bool or r == .bool) return .{ .bools = .{ valBool(l), valBool(r) } };
    if (pyFloat(l)) |lf| if (pyFloat(r)) |rf| return .{ .floats = .{ lf, rf } };
    return .{ .strings = .{ pychars.strip(try pyStr(a, l)), pychars.strip(try pyStr(a, r)) } };
}

/// `_comparison_values`: the right-hand side of `=`; a value-list tuple is its members.
fn comparisonValues(a: Allocator, right: Value) error{OutOfMemory}![]const Val {
    if (right == .tuple) {
        const out = try a.alloc(Val, right.tuple.len);
        for (right.tuple, 0..) |item, i| out[i] = try item.toVal(a);
        return out;
    }
    return nodeSetValues(a, right);
}

/// `compare_eq`: any pair equal after coercion; two empty sides are equal.
pub fn compareEq(a: Allocator, left: Value, right: Value) error{OutOfMemory}!bool {
    const lv = try nodeSetValues(a, left);
    const rv = try comparisonValues(a, right);
    if (lv.len == 0 or rv.len == 0) return lv.len == 0 and rv.len == 0;
    for (lv) |l| for (rv) |r| {
        if (l == .null and r == .null) return true;
        if (l == .null or r == .null) continue;
        switch (try coercePair(a, l, r)) {
            .bools => |p| if (p[0] == p[1]) return true,
            .floats => |p| if (p[0] == p[1]) return true,
            .strings => |p| if (std.mem.eql(u8, p[0], p[1])) return true,
        }
    };
    return false;
}

fn lessThan(p: Pair) bool {
    return switch (p) {
        .bools => |b| !b[0] and b[1],
        .floats => |f| f[0] < f[1],
        .strings => |s| std.mem.order(u8, s[0], s[1]) == .lt,
    };
}

fn swap(p: Pair) Pair {
    return switch (p) {
        .bools => |b| .{ .bools = .{ b[1], b[0] } },
        .floats => |f| .{ .floats = .{ f[1], f[0] } },
        .strings => |s| .{ .strings = .{ s[1], s[0] } },
    };
}

/// `compare_lt`: any pair satisfies `<`.
pub fn compareLt(a: Allocator, left: Value, right: Value) error{OutOfMemory}!bool {
    for (try nodeSetValues(a, left)) |l| for (try nodeSetValues(a, right)) |r| {
        if (lessThan(try coercePair(a, l, r))) return true;
    };
    return false;
}

/// `compare_gt`: any pair satisfies `>`.
pub fn compareGt(a: Allocator, left: Value, right: Value) error{OutOfMemory}!bool {
    for (try nodeSetValues(a, left)) |l| for (try nodeSetValues(a, right)) |r| {
        if (lessThan(swap(try coercePair(a, l, r)))) return true;
    };
    return false;
}

test "python float() syntax" {
    try std.testing.expectEqual(@as(?f64, 1.5), pyFloatText(" 1.5 "));
    try std.testing.expectEqual(@as(?f64, 1000), pyFloatText("1_000"));
    try std.testing.expectEqual(@as(?f64, -0.5), pyFloatText("-.5"));
    try std.testing.expectEqual(@as(?f64, 5), pyFloatText("5."));
    try std.testing.expectEqual(@as(?f64, 1e3), pyFloatText("1E3"));
    try std.testing.expect(std.math.isInf(pyFloatText("-Infinity").?));
    for ([_][]const u8{ "", "abc", "1_", "_1", "0x10", "1e", ".", "1.2.3", "true" }) |bad| {
        try std.testing.expectEqual(@as(?f64, null), pyFloatText(bad));
    }
}

test "comparisons coerce like Python" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const s = struct {
        fn v(x: Val) Value {
            return .{ .scalar = x };
        }
    }.v;
    try std.testing.expect(try compareEq(a, s(.{ .string = "1.0" }), s(.{ .int = 1 })));
    try std.testing.expect(try compareEq(a, s(.{ .string = "true" }), s(.{ .bool = true })));
    try std.testing.expect(try compareEq(a, s(.{ .string = " x" }), s(.{ .string = "x " })));
    try std.testing.expect(try compareEq(a, .{ .nodes = &.{} }, .{ .nodes = &.{} }));
    try std.testing.expect(!try compareEq(a, .{ .nodes = &.{} }, s(.{ .int = 0 })));
    try std.testing.expect(try compareLt(a, s(.{ .string = "abc" }), s(.{ .string = "abd" })));
    try std.testing.expect(try compareGt(a, s(.{ .int = 3 }), s(.{ .string = "2" })));
}
