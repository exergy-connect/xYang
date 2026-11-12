//! XPath parser (mirrors `src/xyang/xpath/parser.py`), and `bind_xpath_prefixes`.
//!
//! Failures carry Python's message: `XPathSyntaxError` (`error.XPathSyntax`), an unknown
//! function (`UnsupportedXPathError`, `error.UnknownFunction`) and an unbound prefix
//! (`YangSyntaxError`, `error.UnknownPrefix`).

const std = @import("std");
const xast = @import("ast.zig");
const tokenizer = @import("tokenizer.zig");
const functions = @import("functions.zig");
const pychars = @import("pychars.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Token = tokenizer.Token;
const TokenType = tokenizer.TokenType;
const Expr = xast.Expr;
const Literal = xast.Literal;
const Segment = xast.Segment;
const Path = xast.Path;

pub const Error = error{ OutOfMemory, XPathSyntax, UnknownFunction, UnsupportedNumber };

const COMPARISON_OPS = [_][]const u8{ "=", "!=", "<", ">", "<=", ">=" };
const ADDITIVE_OPS = [_][]const u8{ "+", "-" };

fn oneOf(v: []const u8, ops: []const []const u8) bool {
    for (ops) |op| if (std.mem.eql(u8, v, op)) return true;
    return false;
}

pub const Parser = struct {
    a: Allocator,
    expression: []const u8,
    tokens: []const Token,
    position: usize = 0,
    /// Python's `str(exc)` when a parse function fails.
    message: []const u8 = "",

    pub fn init(a: Allocator, expression: []const u8) error{OutOfMemory}!Parser {
        return .{ .a = a, .expression = expression, .tokens = try tokenizer.tokenize(a, expression) };
    }

    fn fail(self: *Parser, err: Error, comptime fmt: []const u8, args: anytype) Error {
        self.message = try std.fmt.allocPrint(self.a, fmt, args);
        return err;
    }

    fn new(self: *Parser, e: Expr) error{OutOfMemory}!*Expr {
        const out = try self.a.create(Expr);
        out.* = e;
        return out;
    }

    /// `parse`: the whole input as one expression.
    pub fn parse(self: *Parser) Error!*Expr {
        if (self.tokens.len == 0 or self.tokens[0].type == .eof) return self.fail(error.XPathSyntax, "Empty expression", .{});
        const node = try self.parseExpression();
        const t = self.current();
        if (t.type != .eof) return self.fail(error.XPathSyntax, "Unexpected token: {s} ({f})", .{ t.type.pyName(), pyfmt.repr(t.value) });
        return node;
    }

    /// `parse_path`: the input strictly as a path (leafref `path`), without wildcards.
    pub fn parsePath(self: *Parser, allow_predicate: bool) Error!*Expr {
        if (self.tokens.len == 0 or self.tokens[0].type == .eof) return self.fail(error.XPathSyntax, "Empty path expression", .{});
        const is_absolute = self.current().type == .slash;
        if (is_absolute) _ = try self.consume(.slash);
        const path = try self.parsePathSteps(is_absolute, null, allow_predicate);
        if (self.current().type != .eof) {
            const t = self.current();
            return self.fail(error.XPathSyntax, "Unexpected token after path: {s} ({f})", .{ t.type.pyName(), pyfmt.repr(t.value) });
        }
        for (path.path.segments) |seg| {
            if (seg.isWildcard()) return self.fail(error.XPathSyntax, "Wildcard {f} is not allowed in a schema path", .{pyfmt.repr(seg.step)});
        }
        return path;
    }

    fn current(self: *const Parser) Token {
        if (self.position < self.tokens.len) return self.tokens[self.position];
        return .{ .type = .eof, .value = "", .position = 0 };
    }

    fn consume(self: *Parser, expected: ?TokenType) Error!Token {
        const t = self.current();
        if (expected) |e| if (t.type != e) {
            return self.fail(error.XPathSyntax, "Expected {s}, got {s} ({f})", .{ e.pyName(), t.type.pyName(), pyfmt.repr(t.value) });
        };
        self.position += 1;
        return t;
    }

    fn isKeyword(self: *const Parser, keyword: []const u8) bool {
        const t = self.current();
        return t.type == .identifier and std.ascii.eqlIgnoreCase(t.value, keyword);
    }

    fn parseExpression(self: *Parser) Error!*Expr {
        return self.parseLogicalOr();
    }

    fn binary(self: *Parser, left: *Expr, op: []const u8, right: *Expr) error{OutOfMemory}!*Expr {
        return self.new(.{ .binary = .{ .left = left, .operator = op, .right = right } });
    }

    fn parseLogicalOr(self: *Parser) Error!*Expr {
        var left = try self.parseLogicalAnd();
        while (self.isKeyword("or")) {
            _ = try self.consume(null);
            left = try self.binary(left, "or", try self.parseLogicalAnd());
        }
        return left;
    }

    fn parseLogicalAnd(self: *Parser) Error!*Expr {
        var left = try self.parseComparison();
        while (self.isKeyword("and")) {
            _ = try self.consume(null);
            left = try self.binary(left, "and", try self.parseComparison());
        }
        return left;
    }

    fn parseComparison(self: *Parser) Error!*Expr {
        const left = try self.parseAdditive();
        const t = self.current();
        if (t.type == .operator and oneOf(t.value, &COMPARISON_OPS)) {
            const op = (try self.consume(null)).value;
            return self.binary(left, op, try self.parseAdditive());
        }
        return left;
    }

    fn parseAdditive(self: *Parser) Error!*Expr {
        var left = try self.parseMultiplicative();
        while (true) {
            const t = self.current();
            if (t.type != .operator or !oneOf(t.value, &ADDITIVE_OPS)) break;
            const op = (try self.consume(null)).value;
            left = try self.binary(left, op, try self.parseMultiplicative());
        }
        return left;
    }

    fn parseMultiplicative(self: *Parser) Error!*Expr {
        var left = try self.parseUnary();
        while (true) {
            const t = self.current();
            if (t.type == .slash) {
                _ = try self.consume(null);
                left = try self.binary(left, "/", try self.parsePathSteps(false, null, true));
            } else if (t.type == .operator and std.mem.eql(u8, t.value, "*")) {
                _ = try self.consume(null);
                left = try self.binary(left, "*", try self.parseUnary());
            } else if (self.isKeyword("div") or self.isKeyword("mod")) {
                // XPath 1.0 3.7: div/mod after an operand are multiplicative operators.
                const op = if (self.isKeyword("div")) "div" else "mod";
                _ = try self.consume(null);
                left = try self.binary(left, op, try self.parseUnary());
            } else break;
        }
        return left;
    }

    fn parseUnary(self: *Parser) Error!*Expr {
        const t = self.current();
        if (t.type == .operator and std.mem.eql(u8, t.value, "-")) {
            _ = try self.consume(null);
            const operand = try self.parseUnary();
            return self.binary(try self.new(.{ .literal = .{ .int = 0 } }), "-", operand);
        }
        if (t.type == .operator and std.mem.eql(u8, t.value, "+")) {
            _ = try self.consume(null);
            return self.parseUnary();
        }
        if (self.isKeyword("not")) {
            _ = try self.consume(null);
            _ = try self.consume(.paren_open);
            const operand = try self.parseExpression();
            _ = try self.consume(.paren_close);
            const args = try self.a.alloc(*Expr, 1);
            args[0] = operand;
            return self.new(.{ .call = .{ .name = "not", .args = args } });
        }
        return self.parsePrimary();
    }

    fn number(self: *Parser, t: Token) Error!Literal {
        const raw = t.value;
        var ascii: std.ArrayList(u8) = .empty;
        const view = std.unicode.Utf8View.init(raw) catch return self.fail(error.XPathSyntax, "Invalid number: {s}", .{raw});
        var it = view.iterator();
        while (it.nextCodepoint()) |cp| {
            if (cp == '-' or cp == '.') {
                try ascii.append(self.a, @intCast(cp));
            } else if (pychars.decimalValue(cp)) |d| {
                try ascii.append(self.a, '0' + d);
            } else return self.fail(error.XPathSyntax, "Invalid number: {s}", .{raw});
        }
        if (std.mem.indexOfScalar(u8, raw, '.') != null) {
            return .{ .float = std.fmt.parseFloat(f64, ascii.items) catch return self.fail(error.XPathSyntax, "Invalid number: {s}", .{raw}) };
        }
        return .{ .int = std.fmt.parseInt(i128, ascii.items, 10) catch
            return self.fail(error.UnsupportedNumber, "xyang-zig does not support the XPath number {f} outside the 128-bit range", .{pyfmt.repr(raw)}) };
    }

    fn parsePrimary(self: *Parser) Error!*Expr {
        const t = self.current();
        switch (t.type) {
            .string => {
                _ = try self.consume(null);
                return self.new(.{ .literal = .{ .string = t.value } });
            },
            .number => {
                _ = try self.consume(null);
                return self.new(.{ .literal = try self.number(t) });
            },
            .identifier => {
                for ([_][]const u8{ "true", "false" }) |kw| {
                    if (!self.isKeyword(kw)) continue;
                    _ = try self.consume(null);
                    if (self.current().type == .paren_open) {
                        _ = try self.consume(.paren_open);
                        _ = try self.consume(.paren_close);
                    }
                    return self.new(.{ .literal = .{ .boolean = kw[0] == 't' } });
                }
                if (self.position + 1 < self.tokens.len and self.tokens[self.position + 1].type == .paren_open) {
                    return self.parseFunctionCall();
                }
                return self.parsePathSteps(false, null, true);
            },
            .dot => {
                _ = try self.consume(null);
                if (self.current().type == .paren_open) {
                    _ = try self.consume(.paren_open);
                    _ = try self.consume(.paren_close);
                    return self.new(.{ .call = .{ .name = "current", .args = &.{} } });
                }
                return self.parsePathSteps(false, ".", true);
            },
            .dotdot => return self.parsePathSteps(false, null, true),
            .slash => {
                _ = try self.consume(null);
                return self.parsePathSteps(true, null, true);
            },
            .paren_open => {
                _ = try self.consume(.paren_open);
                // XPath 2.0 value list: ( 'a', 'b', 'c' ) when the first token is a literal.
                const peek = self.current();
                if (peek.type == .string or peek.type == .number) {
                    const first = try self.parsePrimary();
                    if (first.* == .literal and self.current().type == .comma) {
                        var values: std.ArrayList(Literal) = .empty;
                        try values.append(self.a, first.literal);
                        while (self.current().type == .comma) {
                            _ = try self.consume(.comma);
                            const next = try self.parsePrimary();
                            if (next.* != .literal) return self.fail(error.XPathSyntax, "Value list may only contain literals (string or number)", .{});
                            try values.append(self.a, next.literal);
                        }
                        _ = try self.consume(.paren_close);
                        return self.new(.{ .literal = .{ .tuple = values.items } });
                    }
                    if (self.current().type == .paren_close) {
                        _ = try self.consume(.paren_close);
                        return first;
                    }
                }
                const expr = try self.parseExpression();
                _ = try self.consume(.paren_close);
                return expr;
            },
            else => return self.fail(error.XPathSyntax, "Unexpected token: {f}", .{t}),
        }
    }

    fn parseFunctionCall(self: *Parser) Error!*Expr {
        const name = (try self.consume(null)).value;
        _ = try self.consume(.paren_open);
        var args: std.ArrayList(*Expr) = .empty;
        if (self.current().type != .paren_close) {
            try args.append(self.a, try self.parseExpression());
            while (self.current().type == .comma) {
                _ = try self.consume(.comma);
                try args.append(self.a, try self.parseExpression());
            }
        }
        _ = try self.consume(.paren_close);
        const key = try std.ascii.allocLowerString(self.a, name);
        if (functions.lookup(key) == null) {
            return self.fail(error.UnknownFunction, "{s}: unknown XPath function {f}", .{ functions.UNKNOWN_FUNCTION_CODE, pyfmt.repr(key) });
        }
        return self.new(.{ .call = .{ .name = name, .args = args.items } });
    }

    /// `_parse_path`: steps with optional predicates, each followed by an optional `/`.
    fn parsePathSteps(self: *Parser, is_absolute: bool, first_step: ?[]const u8, allow_predicate: bool) Error!*Expr {
        var segments: std.ArrayList(Segment) = .empty;
        const out = try self.new(.{ .path = .{ .segments = &.{}, .is_absolute = is_absolute } });
        var more = true;
        if (first_step) |step| {
            // Stop when '.' is not followed by '/', so `. div 2` leaves div for the
            // multiplicative operator instead of treating it as a step name.
            more = try self.addStep(&segments, step, allow_predicate);
        }
        while (more) {
            switch (self.current().type) {
                .dot, .dotdot, .identifier => {},
                else => break,
            }
            const step = (try self.consume(null)).value;
            more = try self.addStep(&segments, step, allow_predicate);
        }
        out.path.segments = segments.items;
        return out;
    }

    /// Append a step and its predicates; true when a trailing `/` was consumed.
    fn addStep(self: *Parser, segments: *std.ArrayList(Segment), step: []const u8, allow_predicate: bool) Error!bool {
        var seg: Segment = .{ .step = step };
        while (self.current().type == .bracket_open) {
            if (!allow_predicate) return self.fail(error.XPathSyntax, "Predicates are not allowed in this path context", .{});
            _ = try self.consume(.bracket_open);
            const pred = try self.parseExpression();
            seg.predicate = if (seg.predicate) |prev| try self.binary(prev, "and", pred) else pred;
            _ = try self.consume(.bracket_close);
        }
        try segments.append(self.a, seg);
        if (self.current().type == .slash) {
            _ = try self.consume(null);
            return true;
        }
        return false;
    }
};

/// Resolves a lexical prefix to a module name in the module that wrote the expression.
pub const Resolver = struct {
    ctx: *anyopaque,
    resolve: *const fn (ctx: *anyopaque, prefix: []const u8) ?[]const u8,
};

pub const BindError = error{ OutOfMemory, UnknownPrefix };

/// `bind_xpath_prefixes`: bind each `prefix:name` and `prefix:*` step to the module the
/// writing module maps the prefix to (RFC 7950 6.4.1, 7.13). An unbound prefix fails with
/// Python's `YangSyntaxError` text in `message`.
pub fn bindPrefixes(a: Allocator, node: ?*Expr, resolver: Resolver, expression: []const u8, message: *[]const u8) BindError!void {
    const e = node orelse return;
    switch (e.*) {
        .path => |*p| for (p.segments) |*seg| {
            if (seg.prefix()) |prefix| {
                seg.module = resolver.resolve(resolver.ctx, prefix) orelse {
                    message.* = try std.fmt.allocPrint(a, "xpath: unknown prefix {f} in {f} of {f}", .{ pyfmt.repr(prefix), pyfmt.repr(seg.step), pyfmt.repr(expression) });
                    return error.UnknownPrefix;
                };
            }
            try bindPrefixes(a, seg.predicate, resolver, expression, message);
        },
        .binary => |b| {
            try bindPrefixes(a, b.left, resolver, expression, message);
            try bindPrefixes(a, b.right, resolver, expression, message);
        },
        .call => |c| for (c.args) |arg| try bindPrefixes(a, arg, resolver, expression, message),
        .literal => {},
    }
}

fn expectSyntax(a: Allocator, text: []const u8, want: []const u8) !void {
    var p = try Parser.init(a, text);
    if (p.parse()) |_| return error.TestExpectedError else |_| try std.testing.expectEqualStrings(want, p.message);
}

test "parse errors match XPathSyntaxError" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    try expectSyntax(a, "a = ", "Unexpected token: Token(EOF, '', pos=4)");
    try expectSyntax(a, "(a", "Expected PAREN_CLOSE, got EOF ('')");
    try expectSyntax(a, "a ]", "Unexpected token: BRACKET_CLOSE (']')");
    try expectSyntax(a, "1.2.3", "Unexpected token: DOT ('.')");
    try expectSyntax(a, "foo:bar(1)", "xpath-unknown-function: unknown XPath function 'foo:bar'");
    try expectSyntax(a, "", "Empty expression");
    var leafref = try Parser.init(a, "/top/*");
    try std.testing.expectError(error.XPathSyntax, leafref.parsePath(true));
    try std.testing.expectEqualStrings("Wildcard '*' is not allowed in a schema path", leafref.message);
}

test "the parser builds Python's tree" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var p = try Parser.init(a, "../a[b = current()]/c and (1 + 2)");
    const e = try p.parse();
    try std.testing.expectEqualStrings("and", e.binary.operator);
    const path = e.binary.left.path;
    try std.testing.expectEqual(@as(usize, 3), path.segments.len);
    try std.testing.expectEqualStrings("../a/c", try path.toString(a));
    try std.testing.expect(path.segments[1].predicate != null);
    // Python reads `(1 + 2)` as the literal 1 followed by the expression `+ 2`.
    try std.testing.expectEqual(@as(i128, 2), e.binary.right.literal.int);
    var vl = try Parser.init(a, ". = ('a', 1)");
    try std.testing.expectEqual(@as(usize, 2), (try vl.parse()).binary.right.literal.tuple.len);
}
