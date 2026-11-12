//! Built-in XPath functions (mirrors `src/xyang/xpath/functions.py`): one registry the
//! parser checks names against and the evaluator dispatches through.

const std = @import("std");
const jv = @import("../json_value.zig");
const identity_graph = @import("../identity_graph.zig");
const xast = @import("ast.zig");
const node_mod = @import("node.zig");
const utils = @import("utils.zig");
const schema_nav = @import("schema_nav.zig");
const evaluator = @import("evaluator.zig");

const Val = jv.Val;
const Value = node_mod.Value;
const Node = node_mod.Node;
const Context = node_mod.Context;
const Call = xast.Call;
const Evaluator = evaluator.Evaluator;
const Error = evaluator.Error;

/// Same code string as the TypeScript dispatcher (`ts/src/xpath/functions.ts`).
pub const UNKNOWN_FUNCTION_CODE = "xpath-unknown-function";

pub const Fn = *const fn (ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value;

const FUNCTIONS = std.StaticStringMap(Fn).initComptime(.{
    .{ "current", fCurrent },
    .{ "not", fNot },
    .{ "true", fTrue },
    .{ "false", fFalse },
    .{ "count", fCount },
    .{ "string", fString },
    .{ "number", fNumber },
    // XPath 1.0 (RFC 7950 when/must)
    .{ "boolean", fBool },
    .{ "string-length", fStringLength },
    .{ "concat", fConcat },
    .{ "contains", fContains },
    .{ "starts-with", fStartsWith },
    .{ "substring-before", fSubstringBefore },
    .{ "substring-after", fSubstringAfter },
    .{ "translate", fTranslate },
    .{ "deref", fDeref },
    .{ "derived-from", fDerivedFrom },
    .{ "derived-from-or-self", fDerivedFromOrSelf },
});

/// The function registered under a lower-case name.
pub fn lookup(lower_name: []const u8) ?Fn {
    return FUNCTIONS.get(lower_name);
}

fn str(ev: *Evaluator, s: []const u8) Error!Value {
    _ = ev;
    return .{ .scalar = .{ .string = s } };
}

fn int(n: usize) Value {
    return .{ .scalar = .{ .int = @intCast(n) } };
}

/// XPath 1.0 string conversion of one argument, the same as `string()`.
fn asString(ev: *Evaluator, arg: *const xast.Expr, ctx: Context, node: *const Node) Error![]const u8 {
    const v = try utils.firstValue(ev.a, try ev.eval(arg, ctx, node));
    return if (v == .null) "" else utils.pyStr(ev.a, v);
}

/// Wrong arity is an `XPathEvaluationError`; validation reports it as `xpath-error`.
fn requireArity(ev: *Evaluator, call: *const Call, expected: usize) Error!void {
    if (call.args.len == expected) return;
    var buf: [64]u8 = undefined;
    const name = if (call.name.len <= buf.len) std.ascii.lowerString(&buf, call.name) else call.name;
    return ev.fail("{s}() expects {d} arguments, got {d}", .{ name, expected, call.args.len });
}

/// `current()`: the validation anchor as a node, so `current()/child` works.
fn fCurrent(_: *Evaluator, _: *const Call, ctx: Context, _: *const Node) Error!Value {
    return if (ctx.current) |c| .{ .node = c } else Value.none;
}

fn fNot(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return Value.none;
    return Value.boolean(!utils.yangBool(try ev.eval(call.args[0], ctx, node)));
}

fn fTrue(_: *Evaluator, _: *const Call, _: Context, _: *const Node) Error!Value {
    return Value.boolean(true);
}

fn fFalse(_: *Evaluator, _: *const Call, _: Context, _: *const Node) Error!Value {
    return Value.boolean(false);
}

fn fCount(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return int(0);
    const v = try ev.eval(call.args[0], ctx, node);
    return int(if (v == .nodes) v.nodes.len else 1);
}

fn fString(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return str(ev, "");
    return str(ev, try asString(ev, call.args[0], ctx, node));
}

fn fNumber(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return .{ .scalar = .{ .float = std.math.nan(f64) } };
    const v = try utils.firstValue(ev.a, try ev.eval(call.args[0], ctx, node));
    return .{ .scalar = .{ .float = utils.pyFloat(v) orelse std.math.nan(f64) } };
}

fn fBool(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return Value.boolean(false);
    return Value.boolean(utils.yangBool(try ev.eval(call.args[0], ctx, node)));
}

fn fStringLength(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return int(0);
    const s = try asString(ev, call.args[0], ctx, node);
    return int(std.unicode.utf8CountCodepoints(s) catch s.len);
}

fn fConcat(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    var out: std.ArrayList(u8) = .empty;
    for (call.args) |arg| try out.appendSlice(ev.a, try asString(ev, arg, ctx, node));
    return str(ev, out.items);
}

/// `contains(source, needle)`: an empty needle is contained.
fn fContains(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    try requireArity(ev, call, 2);
    const source = try asString(ev, call.args[0], ctx, node);
    const needle = try asString(ev, call.args[1], ctx, node);
    return Value.boolean(std.mem.indexOf(u8, source, needle) != null);
}

fn fStartsWith(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    try requireArity(ev, call, 2);
    const source = try asString(ev, call.args[0], ctx, node);
    const needle = try asString(ev, call.args[1], ctx, node);
    return Value.boolean(std.mem.startsWith(u8, source, needle));
}

/// The substring before the first needle; empty when the needle is empty or absent.
fn fSubstringBefore(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    try requireArity(ev, call, 2);
    const source = try asString(ev, call.args[0], ctx, node);
    const needle = try asString(ev, call.args[1], ctx, node);
    const i = std.mem.indexOf(u8, source, needle) orelse return str(ev, "");
    return str(ev, source[0..i]);
}

/// The substring after the first needle; an empty needle returns the whole source.
fn fSubstringAfter(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    try requireArity(ev, call, 2);
    const source = try asString(ev, call.args[0], ctx, node);
    const needle = try asString(ev, call.args[1], ctx, node);
    const i = std.mem.indexOf(u8, source, needle) orelse return str(ev, "");
    return str(ev, source[i + needle.len ..]);
}

/// Python truthiness of an instance value.
fn truthy(v: Val) bool {
    return switch (v) {
        .null => false,
        .bool => |b| b,
        .int => |i| i != 0,
        .float => |f| f != 0,
        .decimal => |d| !std.mem.eql(u8, d.digits, "0"),
        .string => |s| s.len > 0,
        .array => |items| items.len > 0,
        .object => |o| o.count() > 0,
    };
}

/// `str(value or "")` of an evaluation result.
fn valueText(ev: *Evaluator, v: Value) Error![]const u8 {
    switch (v) {
        .scalar => |s| return if (truthy(s)) utils.pyStr(ev.a, s) else "",
        .nodes => |ns| return if (ns.len == 0) "" else utils.pyStr(ev.a, ns[0].data),
        .node => |n| return utils.pyStr(ev.a, n.data),
        .tuple => |items| {
            const lit: xast.Literal = .{ .tuple = items };
            return lit.reprAlloc(ev.a);
        },
    }
}

fn codepoints(ev: *Evaluator, s: []const u8) Error![]const u21 {
    var out: std.ArrayList(u21) = .empty;
    const view = std.unicode.Utf8View.init(s) catch {
        for (s) |b| try out.append(ev.a, b);
        return out.items;
    };
    var it = view.iterator();
    while (it.nextCodepoint()) |cp| try out.append(ev.a, cp);
    return out.items;
}

/// `translate(source, from, to)` with `str.translate`: a later duplicate in `from` wins;
/// a character past the end of `to` is deleted.
fn fTranslate(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 3) return str(ev, "");
    const first = try utils.firstValue(ev.a, try ev.eval(call.args[0], ctx, node));
    const source = if (truthy(first)) try utils.pyStr(ev.a, first) else "";
    const from = try codepoints(ev, std.mem.trim(u8, try valueText(ev, try ev.eval(call.args[1], ctx, node)), "'\""));
    const to = try codepoints(ev, std.mem.trim(u8, try valueText(ev, try ev.eval(call.args[2], ctx, node)), "'\""));
    if (from.len == 0) return str(ev, source);
    var out: std.ArrayList(u8) = .empty;
    for (try codepoints(ev, source)) |cp| {
        var mapped: ?u21 = cp;
        var i = from.len;
        while (i > 0) {
            i -= 1;
            if (from[i] == cp) {
                mapped = if (i < to.len) to[i] else null;
                break;
            }
        }
        if (mapped) |m| {
            var buf: [4]u8 = undefined;
            const n = std.unicode.utf8Encode(m, &buf) catch continue;
            try out.appendSlice(ev.a, buf[0..n]);
        }
    }
    return str(ev, out.items);
}

/// `deref(path)`: the leafref targets of each source node whose value matches it.
fn fDeref(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    if (call.args.len != 1) return .{ .nodes = &.{} };
    // The argument starts at the node the must is on, so `deref(../child_fk)` in a
    // predicate does not use the predicate's cursor.
    const start = ctx.current orelse node;
    const sources: []const *const Node = switch (try ev.eval(call.args[0], ctx, start)) {
        .nodes => |ns| ns,
        .node => |n| try ev.a.dupe(*const Node, &.{n}),
        else => &.{},
    };
    var out: std.ArrayList(*const Node) = .empty;
    for (sources) |src| {
        const path = schema_nav.leafrefPath(src.schema) orelse continue;
        for (try ev.evalPath(&path.path, ctx, src)) |t| {
            if (jv.pyEql(t.data, src.data)) try out.append(ev.a, t);
        }
    }
    return .{ .nodes = out.items };
}

/// The two `derived-from` operands as strings, or null when Python returns false. The
/// arguments use the evaluation cursor; only `current()` uses the expression origin
/// (RFC 7950 10.1.1).
fn identityOperands(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!?[2][]const u8 {
    if (call.args.len != 2) return null;
    if (ctx.root.schema != .module) return null;
    const v1: Val = switch (try ev.eval(call.args[0], ctx, node)) {
        .nodes => |ns| if (ns.len == 0) return null else ns[0].data,
        .node => |n| n.data,
        else => |v| try utils.firstValue(ev.a, v),
    };
    if (v1 != .string) return null;
    const v2 = try utils.firstValue(ev.a, try ev.eval(call.args[1], ctx, node));
    if (v2 != .string) return null;
    return .{ v1.string, v2.string };
}

/// `derived-from(identityref, identity)`: a strict descendant (RFC 7950 10.4.1).
fn fDerivedFrom(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    const ops = try identityOperands(ev, call, ctx, node) orelse return Value.boolean(false);
    return Value.boolean(try identity_graph.isDerivedFromStrict(ev.a, ctx.root.schema.module, ops[0], ops[1]));
}

/// `derived-from-or-self(identityref, identity)`: equal or a strict descendant.
fn fDerivedFromOrSelf(ev: *Evaluator, call: *const Call, ctx: Context, node: *const Node) Error!Value {
    const ops = try identityOperands(ev, call, ctx, node) orelse return Value.boolean(false);
    return Value.boolean(try identity_graph.isDerivedFromOrSelf(ev.a, ctx.root.schema.module, ops[0], ops[1]));
}
