//! XPath expression tokenizer (mirrors `src/xyang/xpath/tokenizer.py`). Positions are
//! code point offsets, as Python indexes a `str`.

const std = @import("std");
const tokens = @import("tokens.zig");
const pychars = @import("pychars.zig");

const Allocator = std.mem.Allocator;
pub const Token = tokens.Token;
pub const TokenType = tokens.TokenType;

const OPERATORS = [_][]const u8{ "<=", ">=", "!=", "==", "//", "=", "<", ">", "+", "-", "*", "/" };
const OPERATOR_NAMES = [_][]const u8{ "and", "or", "div", "mod" };

fn isQuote(cp: u21) bool {
    return cp == '"' or cp == '\'';
}

fn isOperatorChar(cp: u21) bool {
    return switch (cp) {
        '=', '<', '>', '!', '+', '-', '*', '/' => true,
        else => false,
    };
}

/// `normalize_yang_escaped_quotes`: YANG-style `\"` / `\'` become the quote character.
pub fn normalizeYangEscapedQuotes(a: Allocator, expression: []const u8) error{OutOfMemory}![]const u8 {
    if (std.mem.indexOfScalar(u8, expression, '\\') == null) return expression;
    var out: std.ArrayList(u8) = .empty;
    var i: usize = 0;
    while (i < expression.len) {
        const c = expression[i];
        if (c == '\\' and i + 1 < expression.len and (expression[i + 1] == '"' or expression[i + 1] == '\'')) {
            try out.append(a, expression[i + 1]);
            i += 2;
            continue;
        }
        try out.append(a, c);
        i += 1;
    }
    return out.items;
}

pub const Tokenizer = struct {
    a: Allocator,
    text: []const u8,
    cps: []const u21,
    /// Byte offset of each code point, plus the text length.
    offs: []const usize,
    position: usize = 0,
    tokens: std.ArrayList(Token) = .empty,

    pub fn init(a: Allocator, expression: []const u8) error{OutOfMemory}!Tokenizer {
        const text = try normalizeYangEscapedQuotes(a, expression);
        var cps: std.ArrayList(u21) = .empty;
        var offs: std.ArrayList(usize) = .empty;
        var i: usize = 0;
        while (i < text.len) {
            const n = std.unicode.utf8ByteSequenceLength(text[i]) catch 1;
            const end = @min(i + n, text.len);
            const cp: u21 = std.unicode.utf8Decode(text[i..end]) catch text[i];
            try cps.append(a, cp);
            try offs.append(a, i);
            i = if (end > i) end else i + 1;
        }
        try offs.append(a, text.len);
        return .{ .a = a, .text = text, .cps = cps.items, .offs = offs.items };
    }

    fn slice(self: *const Tokenizer, start: usize, end: usize) []const u8 {
        return self.text[self.offs[start]..self.offs[end]];
    }

    fn peekChar(self: *const Tokenizer, offset: usize) ?u21 {
        const pos = self.position + offset;
        return if (pos < self.cps.len) self.cps[pos] else null;
    }

    fn add(self: *Tokenizer, t: TokenType, value: []const u8, position: usize) error{OutOfMemory}!void {
        try self.tokens.append(self.a, .{ .type = t, .value = value, .position = position });
    }

    pub fn tokenize(self: *Tokenizer) error{OutOfMemory}![]const Token {
        self.position = 0;
        self.tokens = .empty;
        const n = self.cps.len;
        while (self.position < n) {
            if (pychars.isSpace(self.cps[self.position])) {
                while (self.position < n and pychars.isSpace(self.cps[self.position])) self.position += 1;
                continue;
            }
            const c = self.cps[self.position];
            if (isQuote(c)) {
                try self.tokenizeString();
            } else if (pychars.isDigit(c) or (c == '-' and self.isNextDigit())) {
                try self.tokenizeNumber();
            } else if (pychars.isAlpha(c) or c == '_') {
                try self.tokenizeIdentifier();
            } else if (c == '/') {
                if (self.peekChar(1) == '/') {
                    try self.add(.operator, "//", self.position);
                    self.position += 2;
                } else {
                    try self.add(.slash, "/", self.position);
                    self.position += 1;
                }
            } else if (c == '.') {
                if (self.peekChar(1) == '.') {
                    try self.add(.dotdot, "..", self.position);
                    self.position += 2;
                } else {
                    try self.add(.dot, ".", self.position);
                    self.position += 1;
                }
            } else if (isOperatorChar(c)) {
                try self.tokenizeOperator();
            } else if (simple(c)) |st| {
                try self.add(st.t, st.v, self.position);
                self.position += 1;
            } else {
                self.position += 1;
            }
        }
        try self.add(.eof, "", self.position);
        return self.tokens.items;
    }

    const Simple = struct { t: TokenType, v: []const u8 };

    fn simple(c: u21) ?Simple {
        return switch (c) {
            '(' => .{ .t = .paren_open, .v = "(" },
            ')' => .{ .t = .paren_close, .v = ")" },
            '[' => .{ .t = .bracket_open, .v = "[" },
            ']' => .{ .t = .bracket_close, .v = "]" },
            ',' => .{ .t = .comma, .v = "," },
            else => null,
        };
    }

    fn isNextDigit(self: *const Tokenizer) bool {
        return if (self.peekChar(1)) |c| pychars.isDigit(c) else false;
    }

    fn tokenizeString(self: *Tokenizer) error{OutOfMemory}!void {
        const quote = self.cps[self.position];
        const start = self.position;
        self.position += 1;
        var value: std.ArrayList(u8) = .empty;
        while (self.position < self.cps.len) {
            const c = self.cps[self.position];
            if (c == '\\' and self.peekChar(1) == quote) {
                try value.append(self.a, @intCast(quote));
                self.position += 2;
                continue;
            }
            if (c == quote) {
                self.position += 1;
                break;
            }
            try value.appendSlice(self.a, self.slice(self.position, self.position + 1));
            self.position += 1;
        }
        try self.add(.string, value.items, start);
    }

    fn tokenizeNumber(self: *Tokenizer) error{OutOfMemory}!void {
        const start = self.position;
        if (self.cps[self.position] == '-') self.position += 1;
        while (self.position < self.cps.len and pychars.isDigit(self.cps[self.position])) self.position += 1;
        if (self.peekChar(0) == '.' and (if (self.peekChar(1)) |d| pychars.isDigit(d) else false)) {
            self.position += 1;
            while (self.position < self.cps.len and pychars.isDigit(self.cps[self.position])) self.position += 1;
        }
        try self.add(.number, self.slice(start, self.position), start);
    }

    fn tokenizeIdentifier(self: *Tokenizer) error{OutOfMemory}!void {
        const start = self.position;
        while (self.position < self.cps.len) {
            const c = self.cps[self.position];
            if (pychars.isAlnum(c) or c == '_' or c == '-' or c == ':') self.position += 1 else break;
        }
        if (self.cps[self.position - 1] == ':' and self.peekChar(0) == '*') self.position += 1;
        try self.add(.identifier, self.slice(start, self.position), start);
    }

    /// XPath 1.0 3.7: `*` is a NameTest unless an operand precedes it.
    fn starIsNameTest(self: *const Tokenizer) bool {
        if (self.tokens.items.len == 0) return true;
        const prev = self.tokens.items[self.tokens.items.len - 1];
        switch (prev.type) {
            .operator, .slash, .paren_open, .bracket_open, .comma => return true,
            .identifier => {
                for (OPERATOR_NAMES) |name| if (std.ascii.eqlIgnoreCase(prev.value, name)) return true;
                return false;
            },
            else => return false,
        }
    }

    fn tokenizeOperator(self: *Tokenizer) error{OutOfMemory}!void {
        const start = self.position;
        if (self.cps[self.position] == '*' and self.starIsNameTest()) {
            try self.add(.identifier, "*", start);
            self.position += 1;
            return;
        }
        const rest = self.text[self.offs[self.position]..];
        for (OPERATORS) |op| {
            if (std.mem.startsWith(u8, rest, op)) {
                try self.add(.operator, op, start);
                self.position += op.len;
                return;
            }
        }
        try self.add(.operator, self.slice(start, start + 1), start);
        self.position += 1;
    }
};

pub fn tokenize(a: Allocator, expression: []const u8) error{OutOfMemory}![]const Token {
    var t = try Tokenizer.init(a, expression);
    return t.tokenize();
}

test "tokens follow the Python tokenizer" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const toks = try tokenize(a, "count(m:*) * 2 >= -1.5 and ../x[. = 'it''s']");
    const want = [_]struct { TokenType, []const u8 }{
        .{ .identifier, "count" }, .{ .paren_open, "(" },    .{ .identifier, "m:*" }, .{ .paren_close, ")" },
        .{ .operator, "*" },       .{ .number, "2" },        .{ .operator, ">=" },    .{ .number, "-1.5" },
        .{ .identifier, "and" },   .{ .dotdot, ".." },       .{ .slash, "/" },        .{ .identifier, "x" },
        .{ .bracket_open, "[" },   .{ .dot, "." },           .{ .operator, "=" },     .{ .string, "it" },
        .{ .string, "s" },         .{ .bracket_close, "]" }, .{ .eof, "" },
    };
    try std.testing.expectEqual(want.len, toks.len);
    for (want, toks) |w, t| {
        try std.testing.expectEqual(w[0], t.type);
        try std.testing.expectEqualStrings(w[1], t.value);
    }
    const star = try tokenize(a, "* * *");
    try std.testing.expectEqual(TokenType.identifier, star[0].type);
    try std.testing.expectEqual(TokenType.operator, star[1].type);
    try std.testing.expectEqual(TokenType.identifier, star[2].type);
    const esc = try tokenize(a, "derived-from(., \\\"m:x\\\")");
    try std.testing.expectEqualStrings("m:x", esc[4].value);
}
