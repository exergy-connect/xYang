//! Syntax helpers for the two model-defined map projections.
const std = @import("std");
const jv = @import("../json_value.zig");
const Allocator = std.mem.Allocator;
const Error = error{ OutOfMemory, InvalidExpression };

const Scanner = struct {
    a: Allocator,
    text: []const u8,
    at: usize = 0,

    fn skip(self: *Scanner) void {
        while (self.at < self.text.len and std.ascii.isWhitespace(self.text[self.at])) : (self.at += 1) {}
    }
    fn take(self: *Scanner, token: []const u8) bool {
        self.skip();
        if (!std.mem.startsWith(u8, self.text[self.at..], token)) return false;
        const end = self.at + token.len;
        if (std.ascii.isAlphabetic(token[token.len - 1]) and end < self.text.len and (std.ascii.isAlphanumeric(self.text[end]) or self.text[end] == '_')) return false;
        self.at = end;
        return true;
    }
    fn identifier(self: *Scanner) []const u8 {
        self.skip();
        const start = self.at;
        while (self.at < self.text.len and (std.ascii.isAlphanumeric(self.text[self.at]) or self.text[self.at] == '_' or self.text[self.at] == '-')) self.at += 1;
        return self.text[start..self.at];
    }
    fn quoted(self: *Scanner) Error![]const u8 {
        self.skip();
        const start = self.at;
        if (self.at == self.text.len or self.text[self.at] != '"') return error.InvalidExpression;
        self.at += 1;
        while (self.at < self.text.len) {
            if (self.text[self.at] == '\\') {
                self.at += 2;
                continue;
            }
            if (self.text[self.at] == '"') {
                self.at += 1;
                break;
            }
            self.at += 1;
        }
        var message: []const u8 = "";
        const parsed = jv.parse(self.a, self.text[start..@min(self.at, self.text.len)], &message) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return error.InvalidExpression,
        };
        if (parsed != .string) return error.InvalidExpression;
        return parsed.string;
    }
};

pub const StringMap = struct { delimiter: []const u8, target: []const u8, field: []const u8 };

/// Parse a split-and-map expression, including a JSON-escaped delimiter.
pub fn stringMapping(a: Allocator, text: []const u8) error{OutOfMemory}!?StringMap {
    var p: Scanner = .{ .a = a, .text = text };
    if (!p.take("map") or !p.take("(") or !p.take("split") or !p.take("(")) return null;
    const delimiter = p.quoted() catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        error.InvalidExpression => return null,
    };
    if (!p.take(")") or !p.take(",")) return null;
    const target = p.identifier();
    if (target.len == 0 or !p.take(":") or !p.take("{")) return null;
    const field = p.identifier();
    if (field.len == 0 or !p.take(":") or !p.take("$value") or !p.take("}") or !p.take(")")) return null;
    p.skip();
    if (p.at != text.len) return null;
    return .{ .delimiter = delimiter, .target = target, .field = field };
}

pub const Projection = struct { target: []const u8, key: []const u8, path: []const u8 };

/// Parse the generic object key projection syntax. The selected XPath and output
/// field names are provided entirely by the model.
pub fn projection(text: []const u8) ?Projection {
    var p: Scanner = .{ .a = undefined, .text = text };
    if (!p.take("map") or !p.take("(") or !p.take("keys") or !p.take("(")) return null;
    p.skip();
    const start = p.at;
    while (p.at < text.len and text[p.at] != ')') : (p.at += 1) {}
    const path = std.mem.trim(u8, text[start..p.at], &std.ascii.whitespace);
    if (path.len == 0 or path[0] != '/' or !p.take(")") or !p.take(",")) return null;
    const target = p.identifier();
    if (target.len == 0 or !p.take(":") or !p.take("{")) return null;
    const key = p.identifier();
    if (key.len == 0 or !p.take(":") or !p.take("$key") or !p.take(",") or !p.take("...") or !p.take("$value") or !p.take("}") or !p.take(")")) return null;
    p.skip();
    if (p.at != text.len) return null;
    return .{ .target = target, .key = key, .path = path };
}

test "projection field names and XPath come from the expression" {
    const parsed = projection("map(keys(/inventory/name), members: {id: $key, ...$value})").?;
    try std.testing.expectEqualStrings("members", parsed.target);
    try std.testing.expectEqualStrings("id", parsed.key);
    try std.testing.expectEqualStrings("/inventory/name", parsed.path);
}
