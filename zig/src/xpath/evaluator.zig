//! Stateless YANG XPath evaluator (mirrors `src/xyang/xpath/evaluator.py`).
//!
//! `ctx` is passed unchanged through one expression; `node` is replaced on every path
//! step. Python's per-run path cache is not ported: it only memoizes absolute paths,
//! whose results do not change during one validation.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const xast = @import("ast.zig");
const node_mod = @import("node.zig");
const schema_nav = @import("schema_nav.zig");
const utils = @import("utils.zig");
const functions = @import("functions.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const Val = jv.Val;
pub const Node = node_mod.Node;
pub const Context = node_mod.Context;
pub const Value = node_mod.Value;
pub const Schema = node_mod.Schema;
const Expr = xast.Expr;
const Path = xast.Path;
const Segment = xast.Segment;

/// `XPathEvaluationError` / `XPathSyntaxError` raised while evaluating, with Python's
/// `str(exc)` in `Evaluator.message`.
pub const Error = error{ OutOfMemory, XPathEval };

const BinaryFn = *const fn (ev: *Evaluator, left: Value, right: Value) Error!Value;

fn binEq(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(try utils.compareEq(ev.a, l, r));
}
fn binNe(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(!try utils.compareEq(ev.a, l, r));
}
fn binLt(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(try utils.compareLt(ev.a, l, r));
}
fn binGt(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(try utils.compareGt(ev.a, l, r));
}
fn binLe(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(try utils.compareEq(ev.a, l, r) or try utils.compareLt(ev.a, l, r));
}
fn binGe(ev: *Evaluator, l: Value, r: Value) Error!Value {
    return Value.boolean(try utils.compareEq(ev.a, l, r) or try utils.compareGt(ev.a, l, r));
}

/// Both operands as `float(first_value(...))`; null where Python returns NaN.
fn floats(ev: *Evaluator, l: Value, r: Value) Error!?[2]f64 {
    const lf = utils.pyFloat(try utils.firstValue(ev.a, l)) orelse return null;
    const rf = utils.pyFloat(try utils.firstValue(ev.a, r)) orelse return null;
    return .{ lf, rf };
}

fn float(f: f64) Value {
    return .{ .scalar = .{ .float = f } };
}

const nan = std.math.nan(f64);

fn binPlus(ev: *Evaluator, l: Value, r: Value) Error!Value {
    const p = try floats(ev, l, r) orelse return float(nan);
    return float(p[0] + p[1]);
}
fn binMinus(ev: *Evaluator, l: Value, r: Value) Error!Value {
    const p = try floats(ev, l, r) orelse return float(nan);
    return float(p[0] - p[1]);
}
fn binMul(ev: *Evaluator, l: Value, r: Value) Error!Value {
    const p = try floats(ev, l, r) orelse return float(nan);
    return float(p[0] * p[1]);
}
/// XPath 1.0 `div` is IEEE 754: +/-Infinity, and NaN for 0/0.
fn binDiv(ev: *Evaluator, l: Value, r: Value) Error!Value {
    const p = try floats(ev, l, r) orelse return float(nan);
    if (p[1] != 0) return float(p[0] / p[1]);
    if (p[0] == 0 or std.math.isNan(p[0])) return float(nan);
    const sign: f64 = if (std.math.signbit(p[1])) -1.0 else 1.0;
    return float(std.math.copysign(std.math.inf(f64), p[0] * sign));
}
/// `math.fmod`: truncating remainder; NaN where Python raises.
fn binMod(ev: *Evaluator, l: Value, r: Value) Error!Value {
    const p = try floats(ev, l, r) orelse return float(nan);
    if (std.math.isNan(p[0]) or std.math.isNan(p[1])) return float(nan);
    if (p[1] == 0 or std.math.isInf(p[0])) return float(nan);
    if (std.math.isInf(p[1])) return float(p[0]);
    return float(@rem(p[0], p[1]));
}

/// `_BINARY_OP_HANDLERS`: every operator except `and`, `or` and path composition `/`.
const BINARY_OPS = std.StaticStringMap(BinaryFn).initComptime(.{
    .{ "=", binEq },
    .{ "!=", binNe },
    .{ "<", binLt },
    .{ ">", binGt },
    .{ "<=", binLe },
    .{ ">=", binGe },
    .{ "+", binPlus },
    .{ "-", binMinus },
    .{ "*", binMul },
    .{ "div", binDiv },
    .{ "mod", binMod },
});

pub const Evaluator = struct {
    a: Allocator,
    message: []const u8 = "",

    pub fn fail(self: *Evaluator, comptime fmt: []const u8, args: anytype) Error {
        self.message = try std.fmt.allocPrint(self.a, fmt, args);
        return error.XPathEval;
    }

    pub fn eval(self: *Evaluator, e: *const Expr, ctx: Context, node: *const Node) Error!Value {
        return switch (e.*) {
            .literal => |lit| switch (lit) {
                .tuple => |items| .{ .tuple = items },
                else => .{ .scalar = try lit.toVal(self.a) },
            },
            .path => |*p| .{ .nodes = try self.evalPath(p, ctx, node) },
            .binary => |*b| self.evalBinary(b, ctx, node),
            .call => |*c| self.evalFunction(c, ctx, node),
        };
    }

    // -- path ------------------------------------------------------------------------------

    fn rootModule(ctx: Context) []const u8 {
        return switch (ctx.root.schema) {
            .module => |m| m.name,
            else => "",
        };
    }

    /// `eval_path`: the node-set a path selects.
    pub fn evalPath(self: *Evaluator, path: *const Path, ctx: Context, node: *const Node) Error![]const *const Node {
        var nodes: []const *const Node = try self.a.dupe(*const Node, &.{if (path.is_absolute) ctx.root else node});
        for (path.segments) |*seg| {
            if (std.mem.eql(u8, seg.step, ".")) {
                // unchanged
            } else if (std.mem.eql(u8, seg.step, "..")) {
                var next: std.ArrayList(*const Node) = .empty;
                for (nodes) |n| if (n.parent) |p| try next.append(self.a, p);
                nodes = next.items;
            } else if (seg.isWildcard()) {
                if (!std.mem.eql(u8, seg.step, "*") and seg.module == null) {
                    return self.fail("Prefix of {f} is not bound to a module", .{pyfmt.repr(seg.step)});
                }
                var next: std.ArrayList(*const Node) = .empty;
                for (nodes) |n| try self.stepWildcard(n, ctx, seg.module, &next);
                nodes = next.items;
            } else {
                var next: std.ArrayList(*const Node) = .empty;
                for (nodes) |n| try self.stepNamed(n, ctx, seg, &next);
                nodes = next.items;
            }
            if (seg.predicate) |pred| nodes = try self.applyPredicate(nodes, pred, ctx);
        }
        return nodes;
    }

    fn isListLike(n: *const Node) bool {
        return n.data == .array and (schema_nav.isList(n.schema) or schema_nav.isLeafList(n.schema));
    }

    /// `instance_member_keys` under the root module: the one member name of `stmt`.
    fn memberKey(self: *Evaluator, stmt: *const Statement, root_module: []const u8) error{OutOfMemory}![]const u8 {
        const def = rfc7951.definingModuleName(stmt, root_module);
        if (std.mem.eql(u8, def, root_module)) return stmt.name;
        return std.fmt.allocPrint(self.a, "{s}:{s}", .{ def, stmt.name });
    }

    /// `*` / `prefix:*`: every data-node child present in the instance (or by default).
    /// With `module`, only the children that module defines.
    fn stepWildcard(self: *Evaluator, node: *const Node, ctx: Context, module: ?[]const u8, out: *std.ArrayList(*const Node)) Error!void {
        if (isListLike(node)) {
            for (node.data.array) |item| try self.stepWildcard(try node.step(self.a, item, node.schema), ctx, module, out);
            return;
        }
        if (node.data != .object) return;
        const root_module = rootModule(ctx);
        for (try schema_nav.dataChildren(self.a, node.schema)) |c| {
            if (module) |m| if (!std.mem.eql(u8, rfc7951.definingModuleName(c, root_module), m)) continue;
            const key = try self.memberKey(c, root_module);
            const val: Val = if (node.data.object.get(key)) |v| (if (v == .null) Val{ .bool = true } else v) else schema_nav.default(c) orelse continue;
            try self.appendChild(node, val, c, out);
        }
    }

    fn appendChild(self: *Evaluator, node: *const Node, val: Val, c: *Statement, out: *std.ArrayList(*const Node)) Error!void {
        const kind = c.kind();
        if ((kind == .list or kind == .leaf_list) and val == .array) {
            for (val.array) |item| try out.append(self.a, try node.step(self.a, item, .{ .stmt = c }));
        } else {
            try out.append(self.a, try node.step(self.a, val, .{ .stmt = c }));
        }
    }

    /// `_step_named`: an unprefixed step matches the local name; `prefix:name` only a
    /// child that module defines (`seg.module`, or the prefix itself as a module name when
    /// unbound, as in an RFC 7951 instance-identifier value).
    fn stepNamed(self: *Evaluator, node: *const Node, ctx: Context, seg: *const Segment, out: *std.ArrayList(*const Node)) Error!void {
        const root_module = rootModule(ctx);
        const prefix = seg.prefix() orelse return self.step(node, seg.step, root_module, out);
        const module = seg.module orelse prefix;
        if (isListLike(node)) {
            for (node.data.array) |item| try self.stepNamed(try node.step(self.a, item, node.schema), ctx, seg, out);
            return;
        }
        const c = schema_nav.childInModule(node.schema, seg.local(), module, root_module) orelse return;
        try self.stepChild(node, try self.memberKey(c, root_module), c, out);
    }

    /// `_step`: into the child `key`; at a list or leaf-list node, from each entry.
    fn step(self: *Evaluator, node: *const Node, key_in: []const u8, root_module: []const u8, out: *std.ArrayList(*const Node)) Error!void {
        if (isListLike(node)) {
            for (node.data.array) |item| try self.step(try node.step(self.a, item, node.schema), key_in, root_module, out);
            return;
        }
        const c = schema_nav.child(node.schema, key_in);
        var key = key_in;
        if (c) |sc| if (sc.name.len > 0) {
            const k = try self.memberKey(sc, root_module);
            if (!std.mem.eql(u8, k, key)) key = k;
        };
        try self.stepChild(node, key, c, out);
    }

    fn stepChild(self: *Evaluator, node: *const Node, key: []const u8, c: ?*Statement, out: *std.ArrayList(*const Node)) Error!void {
        const val: Val = if (node.data == .object)
            (if (node.data.object.get(key)) |v| (if (v == .null) Val{ .bool = true } else v) else schema_nav.default(c) orelse return)
        else
            return;
        const sc = c orelse {
            try out.append(self.a, try node.step(self.a, val, .none));
            return;
        };
        try self.appendChild(node, val, sc, out);
    }

    /// `_apply_predicate`: a number keeps the node at that 1-based position; anything else
    /// keeps the node when it is true.
    fn applyPredicate(self: *Evaluator, nodes: []const *const Node, pred: *const Expr, ctx: Context) Error![]const *const Node {
        var out: std.ArrayList(*const Node) = .empty;
        for (nodes, 0..) |n, i| {
            const val = try self.eval(pred, ctx, n);
            const keep = if (val == .scalar and (val.scalar == .int or val.scalar == .float)) blk: {
                const pos: i128 = switch (val.scalar) {
                    .int => |x| x,
                    .float => |f| int: {
                        if (std.math.isNan(f)) return self.fail("cannot convert float NaN to integer", .{});
                        if (std.math.isInf(f)) return self.fail("cannot convert float infinity to integer", .{});
                        break :int std.math.lossyCast(i128, @trunc(f));
                    },
                    else => unreachable,
                };
                break :blk pos == @as(i128, @intCast(i + 1));
            } else utils.yangBool(val);
            if (keep) try out.append(self.a, n);
        }
        return out.items;
    }

    // -- operators -------------------------------------------------------------------------

    fn evalBinary(self: *Evaluator, b: *const xast.Binary, ctx: Context, node: *const Node) Error!Value {
        const op = b.operator;
        if (std.mem.eql(u8, op, "or")) {
            if (utils.yangBool(try self.eval(b.left, ctx, node))) return Value.boolean(true);
            return Value.boolean(utils.yangBool(try self.eval(b.right, ctx, node)));
        }
        if (std.mem.eql(u8, op, "and")) {
            if (!utils.yangBool(try self.eval(b.left, ctx, node))) return Value.boolean(false);
            return Value.boolean(utils.yangBool(try self.eval(b.right, ctx, node)));
        }
        if (std.mem.eql(u8, op, "/")) return self.evalComposition(b, ctx, node);
        const left = try self.eval(b.left, ctx, node);
        const right = try self.eval(b.right, ctx, node);
        const handler = BINARY_OPS.get(op) orelse return Value.none;
        return handler(self, left, right);
    }

    /// Path composition `left/right`, evaluated from each node `left` selects.
    fn evalComposition(self: *Evaluator, b: *const xast.Binary, ctx: Context, node: *const Node) Error!Value {
        const left = try self.eval(b.left, ctx, node);
        const left_nodes: []const *const Node = switch (left) {
            .nodes => |ns| ns,
            .node => |n| try self.a.dupe(*const Node, &.{n}),
            else => &.{},
        };
        var out: std.ArrayList(*const Node) = .empty;
        for (left_nodes) |n| {
            switch (try self.eval(b.right, ctx, n)) {
                .nodes => |ns| try out.appendSlice(self.a, ns),
                .node => |x| try out.append(self.a, x),
                else => {},
            }
        }
        return .{ .nodes = out.items };
    }

    fn evalFunction(self: *Evaluator, c: *const xast.Call, ctx: Context, node: *const Node) Error!Value {
        var buf: [64]u8 = undefined;
        const key = if (c.name.len <= buf.len) std.ascii.lowerString(&buf, c.name) else try std.ascii.allocLowerString(self.a, c.name);
        const f = functions.lookup(key) orelse return self.fail("{s}: unknown XPath function {f}", .{ functions.UNKNOWN_FUNCTION_CODE, pyfmt.repr(key) });
        return f(self, c, ctx, node);
    }
};
