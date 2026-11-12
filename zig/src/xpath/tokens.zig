//! XPath token types and `Token` (mirrors `src/xyang/xpath/tokens.py`).

const std = @import("std");
const pyfmt = @import("../pyfmt.zig");

pub const TokenType = enum {
    identifier,
    number,
    string,
    operator,
    paren_open,
    paren_close,
    bracket_open,
    bracket_close,
    dot,
    dotdot,
    slash,
    comma,
    eof,

    /// `TokenType.X.name`.
    pub fn pyName(t: TokenType) []const u8 {
        return switch (t) {
            .identifier => "IDENTIFIER",
            .number => "NUMBER",
            .string => "STRING",
            .operator => "OPERATOR",
            .paren_open => "PAREN_OPEN",
            .paren_close => "PAREN_CLOSE",
            .bracket_open => "BRACKET_OPEN",
            .bracket_close => "BRACKET_CLOSE",
            .dot => "DOT",
            .dotdot => "DOTDOT",
            .slash => "SLASH",
            .comma => "COMMA",
            .eof => "EOF",
        };
    }
};

pub const Token = struct {
    type: TokenType,
    value: []const u8,
    /// Code point offset into the expression, like Python's string index.
    position: usize = 0,

    /// `Token.__repr__`: `Token(EOF, '', pos=4)`.
    pub fn format(self: Token, w: *std.Io.Writer) std.Io.Writer.Error!void {
        try w.print("Token({s}, {f}, pos={d})", .{ self.type.pyName(), pyfmt.repr(self.value), self.position });
    }
};
