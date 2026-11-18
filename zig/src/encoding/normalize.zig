//! Model-defined normalization expressions.
const std = @import("std");
const jv = @import("../json_value.zig");
const Allocator = std.mem.Allocator;
const Val = jv.Val;
const Error = error{ OutOfMemory, InvalidExpression };

pub const Evaluator = struct {
    a: Allocator,
    text: []const u8,
    at: usize = 0,
    message: []const u8 = "invalid normalization expression",

    fn skip(self: *Evaluator) void {
        while (self.at < self.text.len and std.ascii.isWhitespace(self.text[self.at])) : (self.at += 1) {}
    }
    fn take(self: *Evaluator, token: []const u8) bool {
        self.skip();
        if (!std.mem.startsWith(u8, self.text[self.at..], token)) return false;
        const end = self.at + token.len;
        if (std.ascii.isAlphabetic(token[token.len - 1]) and end < self.text.len and (std.ascii.isAlphanumeric(self.text[end]) or self.text[end] == '_')) return false;
        self.at = end;
        return true;
    }
    fn need(self: *Evaluator, token: []const u8) Error!void {
        if (!self.take(token)) return self.fail("expected token");
    }
    fn fail(self: *Evaluator, message: []const u8) Error {
        self.message = message;
        return error.InvalidExpression;
    }
    fn truth(value: Val) bool {
        return switch (value) {
            .null => false,
            .bool => |b| b,
            else => true,
        };
    }
    pub fn run(self: *Evaluator, value: Val) Error!Val {
        const result = try self.pipe(value, true);
        self.skip();
        if (self.at != self.text.len) return self.fail("unexpected expression token");
        return result;
    }
    pub fn validate(self: *Evaluator) Error!void {
        _ = try self.pipe(.null, false);
        self.skip();
        if (self.at != self.text.len) return self.fail("unexpected expression token");
    }
    fn pipe(self: *Evaluator, value: Val, active: bool) Error!Val {
        var result = try self.boolean(value, active);
        while (self.take("|")) result = try self.boolean(result, active);
        return result;
    }
    fn boolean(self: *Evaluator, value: Val, active: bool) Error!Val {
        var result = try self.equal(value, active);
        while (true) {
            const and_op = self.take("and");
            if (!and_op and !self.take("or")) break;
            const left = truth(result);
            const right = try self.equal(value, active and (if (and_op) left else !left));
            result = .{ .bool = if (and_op) left and truth(right) else left or truth(right) };
        }
        return result;
    }
    fn equal(self: *Evaluator, value: Val, active: bool) Error!Val {
        const left = try self.primary(value, active);
        const eq = self.take("==");
        if (!eq and !self.take("!=")) return left;
        const right = try self.primary(value, active);
        const same = std.meta.activeTag(left) == std.meta.activeTag(right) and jv.pyEql(left, right);
        return .{ .bool = if (eq) same else !same };
    }
    fn identifier(self: *Evaluator) []const u8 {
        self.skip();
        const start = self.at;
        while (self.at < self.text.len and (std.ascii.isAlphanumeric(self.text[self.at]) or self.text[self.at] == '_' or self.text[self.at] == '-')) self.at += 1;
        return self.text[start..self.at];
    }
    fn quoted(self: *Evaluator) Error![]const u8 {
        self.skip();
        const start = self.at;
        if (self.at == self.text.len or self.text[self.at] != '"') return self.fail("expected string");
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
        const parsed = jv.parse(self.a, self.text[start..@min(self.at, self.text.len)], &message) catch return self.fail("invalid string");
        if (parsed != .string) return self.fail("invalid string");
        return parsed.string;
    }
    fn primary(self: *Evaluator, value: Val, active: bool) Error!Val {
        if (self.take("[")) {
            try self.need("]");
            return .{ .array = &.{} };
        }
        if (self.take("(")) {
            const out = try self.pipe(value, active);
            try self.need(")");
            return out;
        }
        if (self.take("{")) {
            const obj = try self.a.create(jv.Object);
            obj.* = .empty;
            if (!self.take("}")) while (true) {
                self.skip();
                const key = if (self.at < self.text.len and self.text[self.at] == '"') try self.quoted() else self.identifier();
                if (key.len == 0) return self.fail("expected object field name");
                if (obj.contains(key)) return self.fail("duplicate object field");
                try self.need(":");
                const item = try self.pipe(value, active);
                try obj.put(self.a, key, item);
                if (self.take("}")) break;
                try self.need(",");
            };
            return .{ .object = obj };
        }
        if (self.take(".")) {
            var out = value;
            while (self.take("[")) {
                self.skip();
                const is_string = self.at < self.text.len and self.text[self.at] == '"';
                const key = if (is_string) try self.quoted() else self.identifier();
                if (key.len == 0) return self.fail("expected array index or object key");
                try self.need("]");
                if (!active) {
                    out = .null;
                    continue;
                }
                if (is_string and out == .object) out = out.object.get(key) orelse .null else if (!is_string and out == .array) {
                    const index = std.fmt.parseInt(usize, key, 10) catch return self.fail("expected array index");
                    out = if (index < out.array.len) out.array[index] else .null;
                } else return self.fail("index requires an array index or object key");
            }
            return out;
        }
        self.skip();
        if (self.at < self.text.len and self.text[self.at] == '"') return .{ .string = try self.quoted() };
        const word = self.identifier();
        if (word.len == 0) return self.fail("expected expression");
        if (std.ascii.isDigit(word[0])) return .{ .int = std.fmt.parseInt(i128, word, 10) catch return self.fail("invalid integer") };
        if (std.mem.eql(u8, word, "null")) return .null;
        if (std.mem.eql(u8, word, "true")) return .{ .bool = true };
        if (std.mem.eql(u8, word, "false")) return .{ .bool = false };
        if (std.mem.eql(u8, word, "type")) return .{ .string = switch (value) {
            .null => "null",
            .bool => "boolean",
            .int, .float, .decimal => "number",
            .string => "string",
            .array => "array",
            .object => "object",
        } };
        if (std.mem.eql(u8, word, "to_entries")) {
            if (!active) return .null;
            if (value != .object and value != .array) return self.fail("to_entries requires an array or object");
            var entries: std.ArrayList(Val) = .empty;
            const count = if (value == .object) value.object.count() else value.array.len;
            for (0..count) |index| {
                const entry = try self.a.create(jv.Object);
                entry.* = .empty;
                const key: Val = if (value == .object) .{ .string = value.object.keys()[index] } else .{ .int = @intCast(index) };
                const item = if (value == .object) value.object.values()[index] else value.array[index];
                try entry.put(self.a, "key", key);
                try entry.put(self.a, "value", item);
                try entries.append(self.a, .{ .object = entry });
            }
            return .{ .array = entries.items };
        }
        if (std.mem.eql(u8, word, "length")) {
            if (!active) return .null;
            return .{ .int = switch (value) {
                .string => |s| @intCast(std.unicode.utf8CountCodepoints(s) catch s.len),
                .array => |arr| @intCast(arr.len),
                .object => |obj| @intCast(obj.count()),
                else => return self.fail("length requires a string, array, or object"),
            } };
        }
        if (std.mem.eql(u8, word, "contains") or std.mem.eql(u8, word, "split") or std.mem.eql(u8, word, "has")) {
            try self.need("(");
            const arg = try self.pipe(value, active);
            try self.need(")");
            if (!active) return .null;
            if (std.mem.eql(u8, word, "has")) {
                if (value == .object and arg == .string) return .{ .bool = value.object.contains(arg.string) };
                if (value == .array and arg == .int) return .{ .bool = arg.int >= 0 and arg.int < value.array.len };
                return self.fail("has requires an object key or array index");
            }
            if (value != .string or arg != .string) return self.fail(if (std.mem.eql(u8, word, "split")) "split requires string input and argument" else "contains requires string input and argument");
            if (std.mem.eql(u8, word, "contains")) return .{ .bool = std.mem.indexOf(u8, value.string, arg.string) != null };
            var items: std.ArrayList(Val) = .empty;
            if (arg.string.len == 0) {
                var i: usize = 0;
                while (i < value.string.len) {
                    const width = std.unicode.utf8ByteSequenceLength(value.string[i]) catch 1;
                    const end = @min(i + width, value.string.len);
                    try items.append(self.a, .{ .string = value.string[i..end] });
                    i = end;
                }
            } else {
                var it = std.mem.splitSequence(u8, value.string, arg.string);
                while (it.next()) |part| try items.append(self.a, .{ .string = part });
            }
            return .{ .array = items.items };
        }
        return self.fail("unsupported function or identifier");
    }
};

pub const StringMap = struct { delimiter: []const u8, target: []const u8, field: []const u8 };

/// Parse a split-and-map expression, including a JSON-escaped delimiter.
pub fn stringMapping(a: Allocator, text: []const u8) error{OutOfMemory}!?StringMap {
    var p: Evaluator = .{ .a = a, .text = text };
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
    var p: Evaluator = .{ .a = undefined, .text = text };
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

test "normalization expressions short circuit and preserve Unicode characters" {
    const a = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(a);
    defer arena.deinit();
    const alloc = arena.allocator();
    var predicate: Evaluator = .{ .a = alloc, .text = "type == \"string\" and contains(\"-\")" };
    const no_match = try predicate.run(.{ .int = 7 });
    try std.testing.expect(no_match == .bool and !no_match.bool);
    var split: Evaluator = .{ .a = alloc, .text = "split(\"\")" };
    const parts = try split.run(.{ .string = "aé😀" });
    try std.testing.expectEqual(@as(usize, 3), parts.array.len);
    try std.testing.expectEqualStrings("é", parts.array[1].string);
}

test "projection field names and XPath come from the expression" {
    const parsed = projection("map(keys(/inventory/name), members: {id: $key, ...$value})").?;
    try std.testing.expectEqualStrings("members", parsed.target);
    try std.testing.expectEqualStrings("id", parsed.key);
    try std.testing.expectEqualStrings("/inventory/name", parsed.path);
}
