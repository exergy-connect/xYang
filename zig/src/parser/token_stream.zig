//! Token cursor with Python-identical error messages (mirrors `TokenStream` in
//! `src/xyang/parser/parser_context.py`).

const std = @import("std");
const errors = @import("../errors.zig");
const tokenizer = @import("tokenizer.zig");
const pyfmt = @import("../pyfmt.zig");

pub const Token = tokenizer.Token;
pub const TokenType = tokenizer.TokenType;
const repr = pyfmt.repr;

pub const TokenStream = struct {
    tokens: []const Token,
    index: usize = 0,
    arena: std.mem.Allocator,
    diag: *errors.Diagnostic,
    filename: ?[]const u8,

    pub fn hasMore(self: *const TokenStream) bool {
        return self.index < self.tokens.len;
    }

    pub fn peekToken(self: *const TokenStream) ?Token {
        return if (self.hasMore()) self.tokens[self.index] else null;
    }

    pub fn peek(self: *const TokenStream) ?[]const u8 {
        return if (self.peekToken()) |t| t.value else null;
    }

    /// Current token type. Raises `Unexpected end of input` at the end, like Python.
    pub fn peekType(self: *TokenStream) errors.Error!TokenType {
        if (!self.hasMore()) return self.fail("Unexpected end of input", .{});
        return self.tokens[self.index].type;
    }

    pub fn peekTypeAt(self: *const TokenStream, offset: usize) ?TokenType {
        const i = self.index + offset;
        return if (i < self.tokens.len) self.tokens[i].type else null;
    }

    /// True when the current token exists and has type `tt`.
    pub fn at(self: *const TokenStream, tt: TokenType) bool {
        return self.hasMore() and self.tokens[self.index].type == tt;
    }

    /// True when the current token value equals `value` (any token type, like `peek() == value`).
    pub fn atValue(self: *const TokenStream, value: []const u8) bool {
        return if (self.peek()) |v| std.mem.eql(u8, v, value) else false;
    }

    pub fn consumeAny(self: *TokenStream) errors.Error![]const u8 {
        if (!self.hasMore()) return self.fail("Unexpected end of input", .{});
        const v = self.tokens[self.index].value;
        self.index += 1;
        return v;
    }

    /// `consume(expected)`: the current value must equal `expected`.
    pub fn consume(self: *TokenStream, expected: []const u8) errors.Error![]const u8 {
        if (!self.hasMore()) return self.fail("Unexpected end of input", .{});
        const v = self.tokens[self.index].value;
        if (!std.mem.eql(u8, v, expected)) return self.fail("Expected {f}, got {f}", .{ repr(expected), repr(v) });
        self.index += 1;
        return v;
    }

    pub fn consumeIf(self: *TokenStream, expected: []const u8) bool {
        if (self.atValue(expected)) {
            self.index += 1;
            return true;
        }
        return false;
    }

    /// `consume_type(YangTokenType.X)`.
    pub fn consumeType(self: *TokenStream, expected: TokenType) errors.Error![]const u8 {
        if (!self.hasMore()) return self.fail("Unexpected end of input", .{});
        const tok = self.tokens[self.index];
        if (tok.type != expected) {
            return self.fail("Expected {s}, got {s} ({f})", .{ expected.pyName(), tok.type.pyName(), repr(tok.value) });
        }
        self.index += 1;
        return tok.value;
    }

    pub fn consumeIfType(self: *TokenStream, expected: TokenType) bool {
        if (self.at(expected)) {
            self.index += 1;
            return true;
        }
        return false;
    }

    /// `consume_oneof([...])` over token types.
    pub fn consumeOneOf(self: *TokenStream, allowed: []const TokenType) errors.Error![]const u8 {
        if (!self.hasMore()) return self.fail("Unexpected end of input", .{});
        const tok = self.tokens[self.index];
        for (allowed) |a| {
            if (tok.type == a) {
                self.index += 1;
                return tok.value;
            }
        }
        var names: std.Io.Writer.Allocating = .init(self.arena);
        for (allowed, 0..) |a, i| {
            if (i != 0) names.writer.writeAll(", ") catch return error.OutOfMemory;
            names.writer.writeAll(a.pyName()) catch return error.OutOfMemory;
        }
        const got = if (tok.type == .identifier) tok.value else tok.type.pyName();
        return self.fail("Expected one of ({s}), got {f}", .{ names.written(), repr(got) });
    }

    /// Line of the current token (or the last one at the end), like `position()`.
    pub fn line(self: *const TokenStream) usize {
        if (self.index < self.tokens.len) return self.tokens[self.index].line;
        if (self.tokens.len > 0) return self.tokens[self.tokens.len - 1].line;
        return 1;
    }

    /// `raise tokens.make_error(message)`.
    pub fn fail(self: *TokenStream, comptime fmt: []const u8, args: anytype) errors.Error {
        return self.failKind(.syntax, fmt, args);
    }

    pub fn failKind(self: *TokenStream, kind: errors.Kind, comptime fmt: []const u8, args: anytype) errors.Error {
        const msg = try std.fmt.allocPrint(self.arena, fmt, args);
        self.diag.* = .{ .kind = kind, .message = msg, .line = self.line(), .filename = self.filename };
        return error.YangLoad;
    }

    /// An error without a source location (`YangSyntaxError(str(exc))` / `YangSemanticError`).
    pub fn failUnlocated(self: *TokenStream, kind: errors.Kind, comptime fmt: []const u8, args: anytype) errors.Error {
        const msg = try std.fmt.allocPrint(self.arena, fmt, args);
        self.diag.* = .{ .kind = kind, .message = msg, .line = null, .filename = null };
        return error.YangLoad;
    }
};
