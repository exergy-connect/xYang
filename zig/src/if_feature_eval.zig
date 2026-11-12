//! YANG 1.1 `if-feature` expressions (RFC 7950 7.20.2, section 14) and the enabled
//! feature set per module (mirrors `src/xyang/validator/if_feature_eval.py`). Several
//! `if-feature` substatements on one node combine with AND.

const std = @import("std");
const Module = @import("module.zig").Module;
const identity_graph = @import("identity_graph.zig");

const Allocator = std.mem.Allocator;
pub const FeatureSet = std.StringArrayHashMapUnmanaged(void);
/// Module name -> enabled feature names.
pub const EnabledFeatures = std.StringArrayHashMapUnmanaged(FeatureSet);

/// `reachable_modules`: `root` and every module reachable over `import`.
pub fn reachableModules(a: Allocator, root: *Module) error{OutOfMemory}![]const *Module {
    var out: std.ArrayList(*Module) = .empty;
    try walk(a, root, &out);
    return out.items;
}

fn walk(a: Allocator, m: *Module, out: *std.ArrayList(*Module)) error{OutOfMemory}!void {
    if (std.mem.indexOfScalar(*Module, out.items, m) != null) return;
    try out.append(a, m);
    for (m.import_prefixes.values()) |im| try walk(a, im, out);
}

/// `build_enabled_features_map`. `override == null` enables every declared feature; a
/// module missing from `override` keeps all its features. Features whose own
/// `if-feature` fails are then removed until nothing changes (RFC 7950 7.20.1).
pub fn buildEnabledFeatures(a: Allocator, root: *Module, override: ?*const EnabledFeatures) error{OutOfMemory}!EnabledFeatures {
    const modules = try reachableModules(a, root);
    var result: EnabledFeatures = .empty;
    for (modules) |m| {
        const chosen: FeatureSet = if (override) |o| (o.get(m.name) orelse m.features) else m.features;
        try result.put(a, m.name, try chosen.clone(a));
    }
    var changed = true;
    while (changed) {
        changed = false;
        var frozen: EnabledFeatures = .empty;
        for (result.keys(), result.values()) |k, v| try frozen.put(a, k, try v.clone(a));
        for (modules) |m| {
            const set = result.getPtr(m.name).?;
            var i: usize = set.count();
            while (i > 0) {
                i -= 1;
                const fname = set.keys()[i];
                const reqs = m.feature_if_features.get(fname) orelse continue;
                if (reqs.items.len == 0) continue;
                if (!try ifFeaturesSatisfied(a, reqs.items, m, &frozen)) {
                    set.orderedRemoveAt(i);
                    changed = true;
                }
            }
        }
    }
    return result;
}

/// `feature_is_supported`: `name` or `prefix:name` in the scope of `ctx_module`.
pub fn featureIsSupported(ctx_module: *Module, enabled: *const EnabledFeatures, ref_text: []const u8) bool {
    const ref = identity_graph.parseIdentifierRefAtom(ref_text);
    const mod = if (ref.prefix) |pre| ctx_module.resolvePrefixedModule(pre) orelse return false else ctx_module;
    if (!mod.features.contains(ref.name)) return false;
    const set = enabled.get(mod.name) orelse return false;
    return set.contains(ref.name);
}

const ParseError = error{ Malformed, OutOfMemory };

const ExprParser = struct {
    toks: []const []const u8,
    i: usize = 0,
    ctx: *Module,
    enabled: *const EnabledFeatures,

    fn peek(p: *const ExprParser) ?[]const u8 {
        return if (p.i < p.toks.len) p.toks[p.i] else null;
    }

    fn peekIs(p: *const ExprParser, s: []const u8) bool {
        return if (p.peek()) |t| std.mem.eql(u8, t, s) else false;
    }

    fn eat(p: *ExprParser, expected: ?[]const u8) ParseError![]const u8 {
        const t = p.peek() orelse return error.Malformed;
        if (expected) |e| if (!std.mem.eql(u8, t, e)) return error.Malformed;
        p.i += 1;
        return t;
    }

    fn expr(p: *ExprParser) ParseError!bool {
        var left = try p.term();
        while (p.peekIs("or")) {
            _ = try p.eat("or");
            const right = try p.expr();
            left = left or right;
        }
        return left;
    }

    fn term(p: *ExprParser) ParseError!bool {
        var left = try p.factor();
        while (p.peekIs("and")) {
            _ = try p.eat("and");
            const right = try p.term();
            left = left and right;
        }
        return left;
    }

    fn factor(p: *ExprParser) ParseError!bool {
        const t = p.peek() orelse return error.Malformed;
        if (std.mem.eql(u8, t, "not")) {
            _ = try p.eat("not");
            return !try p.factor();
        }
        if (std.mem.eql(u8, t, "(")) {
            _ = try p.eat("(");
            const v = try p.expr();
            _ = try p.eat(")");
            return v;
        }
        _ = try p.eat(null);
        return featureIsSupported(p.ctx, p.enabled, t);
    }
};

fn tokenize(a: Allocator, text: []const u8) error{OutOfMemory}![]const []const u8 {
    var out: std.ArrayList([]const u8) = .empty;
    var i: usize = 0;
    while (i < text.len) {
        const c = text[i];
        if (std.ascii.isWhitespace(c)) {
            i += 1;
            continue;
        }
        if (c == '(' or c == ')') {
            try out.append(a, text[i .. i + 1]);
            i += 1;
            continue;
        }
        var j = i;
        while (j < text.len and !std.ascii.isWhitespace(text[j]) and text[j] != '(' and text[j] != ')') j += 1;
        try out.append(a, text[i..j]);
        i = j;
    }
    return out.items;
}

/// `evaluate_if_feature_expression`: a malformed expression is false (the node is inactive).
pub fn evaluate(a: Allocator, text: []const u8, ctx_module: *Module, enabled: *const EnabledFeatures) error{OutOfMemory}!bool {
    const trimmed = std.mem.trim(u8, text, &std.ascii.whitespace);
    if (trimmed.len == 0) return false;
    var p: ExprParser = .{ .toks = try tokenize(a, trimmed), .ctx = ctx_module, .enabled = enabled };
    const out = p.expr() catch |err| switch (err) {
        error.Malformed => return false,
        error.OutOfMemory => return error.OutOfMemory,
    };
    if (p.i < p.toks.len) return false;
    return out;
}

/// `stmt_if_features_satisfied`: every expression holds.
pub fn ifFeaturesSatisfied(a: Allocator, if_features: []const []const u8, ctx_module: *Module, enabled: *const EnabledFeatures) error{OutOfMemory}!bool {
    for (if_features) |e| {
        if (!try evaluate(a, e, ctx_module, enabled)) return false;
    }
    return true;
}

test "if-feature expressions and dependent features" {
    const yang_parser = @import("parser/yang_parser.zig");
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("errors.zig").Diagnostic = .{};
    const m = try yang_parser.parseString(a, "module m { prefix m; feature a; feature b; feature c { if-feature \"a and b\"; } }", "m.yang", &diag);
    var all = try buildEnabledFeatures(a, m, null);
    try std.testing.expect(try evaluate(a, "a and (b or not c)", m, &all));
    try std.testing.expect(try evaluate(a, "m:c", m, &all));
    try std.testing.expect(!try evaluate(a, "a and", m, &all));
    try std.testing.expect(!try evaluate(a, "a b", m, &all));
    try std.testing.expect(!try evaluate(a, "unknown", m, &all));
    var only_a: EnabledFeatures = .empty;
    var set: FeatureSet = .empty;
    try set.put(a, "a", {});
    try set.put(a, "c", {});
    try only_a.put(a, "m", set);
    const pruned = try buildEnabledFeatures(a, m, &only_a);
    try std.testing.expect(pruned.get("m").?.contains("a"));
    try std.testing.expect(!pruned.get("m").?.contains("c"));
    try std.testing.expect(!try ifFeaturesSatisfied(a, &.{ "a", "c" }, m, &pruned));
}
