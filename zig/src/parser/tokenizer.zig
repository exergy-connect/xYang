//! YANG tokenizer (mirrors `src/xyang/parser/tokenizer.py`).
//!
//! Positions are byte offsets. Python counts code points, but only ASCII is lexed outside
//! quoted strings and comments here, so lines and adjacency checks agree. A non-ASCII
//! character outside a quoted string or comment is rejected loudly: classifying it would
//! need Unicode tables (`str.isalpha` / `str.isspace`).

const std = @import("std");
const errors = @import("../errors.zig");
const yang_strings = @import("yang_strings.zig");

pub const TokenType = enum {
    lbrace,
    rbrace,
    semicolon,
    colon,
    equals,
    plus,
    slash,
    dot,
    string,
    identifier,
    integer,
    dotted_number,
    other,

    /// The Python `YangTokenType` member name, used verbatim in error messages.
    pub fn pyName(self: TokenType) []const u8 {
        return switch (self) {
            .lbrace => "LBRACE",
            .rbrace => "RBRACE",
            .semicolon => "SEMICOLON",
            .colon => "COLON",
            .equals => "EQUALS",
            .plus => "PLUS",
            .slash => "SLASH",
            .dot => "DOT",
            .string => "STRING",
            .identifier => "IDENTIFIER",
            .integer => "INTEGER",
            .dotted_number => "DOTTED_NUMBER",
            .other => "OTHER",
        };
    }
};

pub const Token = struct {
    type: TokenType,
    value: []const u8,
    line: usize,
    col: usize,
};

fn isSpace(c: u8) bool {
    return switch (c) {
        0x09...0x0d, 0x1c...0x1f, ' ' => true,
        else => false,
    };
}

fn isDigit(c: u8) bool {
    return c >= '0' and c <= '9';
}

fn isAlpha(c: u8) bool {
    return (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z');
}

fn punctuation(c: u8) TokenType {
    return switch (c) {
        '{' => .lbrace,
        '}' => .rbrace,
        ';' => .semicolon,
        ':' => .colon,
        '=' => .equals,
        '+' => .plus,
        '/' => .slash,
        '.' => .dot,
        else => .other,
    };
}

/// Tokenize `content`. Token values point into `content` or into `arena`.
pub fn tokenize(arena: std.mem.Allocator, content: []const u8, diag: *errors.Diagnostic) errors.Error![]Token {
    var tokens: std.ArrayList(Token) = .empty;
    var i: usize = 0;
    const n = content.len;
    var line: usize = 1;
    var line_start: usize = 0;

    while (i < n) {
        const c = content[i];
        if (isSpace(c)) {
            if (c == '\n') {
                line += 1;
                line_start = i + 1;
            }
            i += 1;
            continue;
        }

        if (c == '/' and i + 1 < n) {
            const nxt = content[i + 1];
            if (nxt == '*') {
                const close = std.mem.indexOfPos(u8, content, i + 2, "*/");
                const end = if (close) |e| e + 2 else n;
                countLines(content, i, end, &line, &line_start);
                i = end;
                continue;
            }
            if (nxt == '/') {
                i = std.mem.indexOfScalarPos(u8, content, i + 2, '\n') orelse n;
                continue;
            }
        }

        if (c == '"' or c == '\'') {
            const token_line = line;
            const token_col = i - line_start;
            const start = i + 1;
            var j = start;
            while (j < n) {
                const b = content[j];
                if (b == c) break;
                if (b == '\\') {
                    j += if (j + 1 < n) 2 else 1;
                } else {
                    j += 1;
                }
            }
            const end = @min(j, n);
            countLines(content, i, end, &line, &line_start);
            const value = try yang_strings.unescapeQuoted(arena, content[start..end], c);
            const len = tokens.items.len;
            // RFC 7950 6.1.3 permits concatenation only between quoted strings.
            if (len >= 2 and tokens.items[len - 1].type == .plus and tokens.items[len - 2].type == .string) {
                const prev = &tokens.items[len - 2];
                prev.value = try std.mem.concat(arena, u8, &.{ prev.value, value });
                _ = tokens.pop();
            } else {
                try tokens.append(arena, .{ .type = .string, .value = value, .line = token_line, .col = token_col });
            }
            i = end + 1;
            continue;
        }

        if (c == '-' and i + 1 < n and isDigit(content[i + 1])) {
            var j = i + 1;
            while (j < n and isDigit(content[j])) j += 1;
            try tokens.append(arena, .{ .type = .integer, .value = content[i..j], .line = line, .col = i - line_start });
            i = j;
            continue;
        }

        if (isDigit(c)) {
            var j = i;
            while (j < n and isDigit(content[j])) j += 1;
            var tt: TokenType = .integer;
            if (j < n and content[j] == '.' and j + 1 < n and isDigit(content[j + 1])) {
                j += 1;
                while (j < n and isDigit(content[j])) j += 1;
                tt = .dotted_number;
            }
            try tokens.append(arena, .{ .type = tt, .value = content[i..j], .line = line, .col = i - line_start });
            i = j;
            continue;
        }

        if (isAlpha(c) or c == '_') {
            var j = i + 1;
            while (j < n) : (j += 1) {
                const d = content[j];
                if (d >= 0x80) break;
                if (!(isAlpha(d) or isDigit(d) or d == '_' or d == '-' or d == '.')) break;
            }
            if (j < n and content[j] >= 0x80) return nonAscii(diag, line);
            try tokens.append(arena, .{ .type = .identifier, .value = content[i..j], .line = line, .col = i - line_start });
            i = j;
            continue;
        }

        if (c >= 0x80) return nonAscii(diag, line);

        try tokens.append(arena, .{ .type = punctuation(c), .value = content[i .. i + 1], .line = line, .col = i - line_start });
        i += 1;
    }
    return tokens.items;
}

fn countLines(content: []const u8, from: usize, to: usize, line: *usize, line_start: *usize) void {
    var k = from;
    while (k < to) : (k += 1) {
        if (content[k] == '\n') {
            line.* += 1;
            line_start.* = k + 1;
        }
    }
}

fn nonAscii(diag: *errors.Diagnostic, line: usize) errors.Error {
    diag.* = .{
        .kind = .unsupported,
        .message = "xyang-zig does not support a non-ASCII character outside a quoted string or comment yet",
        .line = line,
    };
    return error.YangLoad;
}

test "tokens follow the Python lexer" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const toks = try tokenize(arena.allocator(),
        \\module m { // c
        \\  yang-version 1.1; /* x
        \\  */ length 1..127; must "a" + 'b'; default -5; enum 50|100GE;
        \\}
    , &diag);
    const expect = [_]struct { TokenType, []const u8, usize }{
        .{ .identifier, "module", 1 },       .{ .identifier, "m", 1 },      .{ .lbrace, "{", 1 },
        .{ .identifier, "yang-version", 2 }, .{ .dotted_number, "1.1", 2 }, .{ .semicolon, ";", 2 },
        .{ .identifier, "length", 3 },       .{ .integer, "1", 3 },         .{ .dot, ".", 3 },
        .{ .dot, ".", 3 },                   .{ .integer, "127", 3 },       .{ .semicolon, ";", 3 },
        .{ .identifier, "must", 3 },         .{ .string, "ab", 3 },         .{ .semicolon, ";", 3 },
        .{ .identifier, "default", 3 },      .{ .integer, "-5", 3 },        .{ .semicolon, ";", 3 },
        .{ .identifier, "enum", 3 },         .{ .integer, "50", 3 },        .{ .other, "|", 3 },
        .{ .integer, "100", 3 },             .{ .identifier, "GE", 3 },     .{ .semicolon, ";", 3 },
        .{ .rbrace, "}", 4 },
    };
    try std.testing.expectEqual(expect.len, toks.len);
    for (expect, toks) |e, t| {
        try std.testing.expectEqual(e[0], t.type);
        try std.testing.expectEqualStrings(e[1], t.value);
        try std.testing.expectEqual(e[2], t.line);
    }
}

test "non-ASCII outside quotes fails loudly" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, tokenize(arena.allocator(), "module m {\n leaf caf\xc3\xa9 {}\n}", &diag));
    try std.testing.expectEqual(errors.Kind.unsupported, diag.kind);
    try std.testing.expectEqual(@as(?usize, 2), diag.line);
    _ = try tokenize(arena.allocator(), "description \"caf\xc3\xa9\"; // \xc3\xa9", &diag);
}
