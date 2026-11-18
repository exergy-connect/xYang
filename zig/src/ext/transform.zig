//! Model-defined jq-style instance normalization (mirrors
//! `src/xyang/ext/transform/__init__.py`).

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const Module = module_mod.Module;
const Val = jv.Val;
const Object = jv.Object;
const repr = pyfmt.repr;

pub const Error = error{ OutOfMemory, Raised, Unsupported };

pub const TRANSFORM_MODULE = "xyang-transform";

const TokenKind = enum { literal, word, number, symbol };

const Token = struct {
    kind: TokenKind,
    string: []const u8 = "",
    number: i128 = 0,
    literal: Val = .null,
};

pub const Expr = union(enum) {
    input,
    literal: Val,
    pipe: struct { left: *Expr, right: *Expr },
    type_of,
    length,
    to_entries,
    object: []const ObjectField,
    index: struct { base: *Expr, key: IndexKey },
    eq: Binary,
    ne: Binary,
    @"and": Binary,
    @"or": Binary,
    contains: *Expr,
    split: *Expr,
    has: *Expr,
};

const ObjectField = struct { key: []const u8, value: *Expr };
const Binary = struct { left: *Expr, right: *Expr };
const IndexKey = union(enum) { number: i128, string: []const u8 };

const Parser = struct {
    a: Allocator,
    tokens: []const Token,
    i: usize = 0,
    message: *[]const u8,

    fn fail(self: *Parser, comptime fmt: []const u8, args: anytype) Error {
        self.message.* = try self.a.print(fmt, args);
        return error.Raised;
    }

    fn take(self: *Parser, value: []const u8) bool {
        if (self.i >= self.tokens.len) return false;
        const t = self.tokens[self.i];
        const match = switch (t.kind) {
            .symbol, .word => std.mem.eql(u8, t.string, value),
            else => false,
        };
        if (match) self.i += 1;
        return match;
    }

    fn require(self: *Parser, value: []const u8) Error!void {
        if (!self.take(value)) return self.fail("expected {f}", .{repr(value)});
    }

    fn parse(self: *Parser) Error!*Expr {
        const result = try self.pipeline();
        if (self.i != self.tokens.len) return self.fail("unexpected token {f}", .{repr(self.tokens[self.i].string)});
        return result;
    }

    fn pipeline(self: *Parser) Error!*Expr {
        var node = try self.boolean();
        while (self.take("|")) {
            const right = try self.boolean();
            const out = try self.a.create(Expr);
            out.* = .{ .pipe = .{ .left = node, .right = right } };
            node = out;
        }
        return node;
    }

    fn boolean(self: *Parser) Error!*Expr {
        var node = try self.equality();
        while (self.i < self.tokens.len and self.tokens[self.i].kind == .word and
            (std.mem.eql(u8, self.tokens[self.i].string, "and") or std.mem.eql(u8, self.tokens[self.i].string, "or")))
        {
            const op = self.tokens[self.i].string;
            self.i += 1;
            const right = try self.equality();
            const out = try self.a.create(Expr);
            out.* = if (std.mem.eql(u8, op, "and"))
                .{ .@"and" = .{ .left = node, .right = right } }
            else
                .{ .@"or" = .{ .left = node, .right = right } };
            node = out;
        }
        return node;
    }

    fn equality(self: *Parser) Error!*Expr {
        const node = try self.primary();
        if (self.take("==")) {
            const right = try self.primary();
            const out = try self.a.create(Expr);
            out.* = .{ .eq = .{ .left = node, .right = right } };
            return out;
        }
        if (self.take("!=")) {
            const right = try self.primary();
            const out = try self.a.create(Expr);
            out.* = .{ .ne = .{ .left = node, .right = right } };
            return out;
        }
        return node;
    }

    fn fieldKey(self: *Parser) Error![]const u8 {
        if (self.i >= self.tokens.len) return self.fail("expected object field name", .{});
        const t = self.tokens[self.i];
        self.i += 1;
        return switch (t.kind) {
            .word => t.string,
            .literal => if (t.literal == .string) t.literal.string else self.fail("expected object field name", .{}),
            else => self.fail("expected object field name", .{}),
        };
    }

    fn primary(self: *Parser) Error!*Expr {
        if (self.take("[")) {
            try self.require("]");
            const out = try self.a.create(Expr);
            out.* = .{ .literal = .{ .array = &.{} } };
            return out;
        }
        if (self.take("(")) {
            const node = try self.pipeline();
            try self.require(")");
            return node;
        }
        if (self.take("{")) {
            var fields: std.ArrayList(ObjectField) = .empty;
            if (!self.take("}")) {
                while (true) {
                    const key = try self.fieldKey();
                    for (fields.items) |f| if (std.mem.eql(u8, f.key, key)) return self.fail("duplicate object field {f}", .{repr(key)});
                    try self.require(":");
                    try fields.append(self.a, .{ .key = key, .value = try self.pipeline() });
                    if (self.take("}")) break;
                    try self.require(",");
                }
            }
            const out = try self.a.create(Expr);
            out.* = .{ .object = fields.items };
            return out;
        }
        if (self.take(".")) {
            var node = try self.a.create(Expr);
            node.* = .input;
            while (self.take("[")) {
                if (self.i >= self.tokens.len or (self.tokens[self.i].kind != .number and self.tokens[self.i].kind != .literal)) {
                    return self.fail("expected array index or object key", .{});
                }
                const key: IndexKey = switch (self.tokens[self.i].kind) {
                    .number => .{ .number = self.tokens[self.i].number },
                    .literal => if (self.tokens[self.i].literal == .string)
                        .{ .string = self.tokens[self.i].literal.string }
                    else
                        return self.fail("expected array index or object key", .{}),
                    else => unreachable,
                };
                self.i += 1;
                try self.require("]");
                const out = try self.a.create(Expr);
                out.* = .{ .index = .{ .base = node, .key = key } };
                node = out;
            }
            return node;
        }
        if (self.i >= self.tokens.len) return self.fail("expected expression", .{});
        const t = self.tokens[self.i];
        self.i += 1;
        if (t.kind == .literal or t.kind == .number) {
            const out = try self.a.create(Expr);
            out.* = .{ .literal = if (t.kind == .number) .{ .int = t.number } else t.literal };
            return out;
        }
        if (t.kind != .word) return self.fail("unexpected token {f}", .{repr(t.string)});
        if (std.mem.eql(u8, t.string, "true") or std.mem.eql(u8, t.string, "false") or std.mem.eql(u8, t.string, "null")) {
            const out = try self.a.create(Expr);
            out.* = .{ .literal = if (std.mem.eql(u8, t.string, "true"))
                .{ .bool = true }
            else if (std.mem.eql(u8, t.string, "false"))
                .{ .bool = false }
            else
                .null };
            return out;
        }
        if (std.mem.eql(u8, t.string, "type") or std.mem.eql(u8, t.string, "length") or std.mem.eql(u8, t.string, "to_entries")) {
            const out = try self.a.create(Expr);
            out.* = if (std.mem.eql(u8, t.string, "type")) .type_of else if (std.mem.eql(u8, t.string, "length")) .length else .to_entries;
            return out;
        }
        if (std.mem.eql(u8, t.string, "contains") or std.mem.eql(u8, t.string, "split") or std.mem.eql(u8, t.string, "has")) {
            try self.require("(");
            const arg = try self.pipeline();
            try self.require(")");
            const out = try self.a.create(Expr);
            out.* = if (std.mem.eql(u8, t.string, "contains"))
                .{ .contains = arg }
            else if (std.mem.eql(u8, t.string, "split"))
                .{ .split = arg }
            else
                .{ .has = arg };
            return out;
        }
        return self.fail("unsupported function or identifier {f}", .{repr(t.string)});
    }
};

fn tokenize(a: Allocator, text: []const u8, message: *[]const u8) Error![]Token {
    var tokens: std.ArrayList(Token) = .empty;
    var pos: usize = 0;
    while (pos < text.len) {
        while (pos < text.len and std.ascii.isWhitespace(text[pos])) pos += 1;
        if (pos >= text.len) break;
        if (text[pos] == '"') {
            var end = pos + 1;
            while (end < text.len) {
                if (text[end] == '\\' and end + 1 < text.len) {
                    end += 2;
                    continue;
                }
                if (text[end] == '"') break;
                end += 1;
            }
            if (end >= text.len) {
                message.* = try a.print("unsupported expression syntax at offset {d}", .{pos});
                return error.Raised;
            }
            const slice = text[pos .. end + 1];
            var msg: []const u8 = "";
            const parsed = jv.parse(a, slice, &msg) catch {
                message.* = try a.print("invalid string: {s}", .{msg});
                return error.Raised;
            };
            try tokens.append(a, .{ .kind = .literal, .literal = parsed, .string = slice });
            pos = end + 1;
            continue;
        }
        if (std.ascii.isDigit(text[pos])) {
            var end = pos;
            while (end < text.len and std.ascii.isDigit(text[end])) end += 1;
            const n = std.fmt.parseInt(i128, text[pos..end], 10) catch {
                message.* = try a.print("unsupported expression syntax at offset {d}", .{pos});
                return error.Raised;
            };
            try tokens.append(a, .{ .kind = .number, .number = n, .string = text[pos..end] });
            pos = end;
            continue;
        }
        if (std.ascii.isAlphabetic(text[pos]) or text[pos] == '_') {
            var end = pos + 1;
            while (end < text.len) {
                const c = text[end];
                if (std.ascii.isAlphanumeric(c) or c == '_' or c == '-') end += 1 else break;
            }
            try tokens.append(a, .{ .kind = .word, .string = text[pos..end] });
            pos = end;
            continue;
        }
        if (pos + 1 < text.len and ((text[pos] == '=' and text[pos + 1] == '=') or (text[pos] == '!' and text[pos + 1] == '='))) {
            try tokens.append(a, .{ .kind = .symbol, .string = text[pos .. pos + 2] });
            pos += 2;
            continue;
        }
        if (std.mem.indexOfScalar(u8, ".[]{}():,|", text[pos]) != null) {
            try tokens.append(a, .{ .kind = .symbol, .string = text[pos .. pos + 1] });
            pos += 1;
            continue;
        }
        message.* = try a.print("unsupported expression syntax at offset {d}", .{pos});
        return error.Raised;
    }
    return tokens.items;
}

pub fn compile(a: Allocator, expression: []const u8, message: *[]const u8) Error!*Expr {
    const tokens = tokenize(a, expression, message) catch |err| {
        if (err == error.Raised) message.* = try a.print("invalid normalization expression {f}: {s}", .{ repr(expression), message.* });
        return err;
    };
    var p: Parser = .{ .a = a, .tokens = tokens, .message = message };
    return p.parse() catch |err| {
        if (err == error.Raised) message.* = try a.print("invalid normalization expression {f}: {s}", .{ repr(expression), message.* });
        return err;
    };
}

fn truth(value: Val) bool {
    return switch (value) {
        .null => false,
        .bool => |b| b,
        else => true,
    };
}

fn sameTag(a: Val, b: Val) bool {
    return std.meta.activeTag(a) == std.meta.activeTag(b);
}

fn typedEql(a: Val, b: Val) bool {
    if (!sameTag(a, b)) return false;
    return switch (a) {
        .null => true,
        .bool => |x| x == b.bool,
        .int => |x| x == b.int,
        .float => |x| x == b.float,
        .decimal => |x| jv.Decimal.eql(x, b.decimal),
        .string => |x| std.mem.eql(u8, x, b.string),
        .array => |xs| {
            if (xs.len != b.array.len) return false;
            for (xs, b.array) |p, q| if (!typedEql(p, q)) return false;
            return true;
        },
        .object => |xo| {
            if (xo.count() != b.object.count()) return false;
            var it = xo.iterator();
            while (it.next()) |e| {
                const other = b.object.get(e.key_ptr.*) orelse return false;
                if (!typedEql(e.value_ptr.*, other)) return false;
            }
            return true;
        },
    };
}

pub fn evaluate(a: Allocator, expr: *const Expr, value: Val, message: *[]const u8) Error!Val {
    return switch (expr.*) {
        .input => value,
        .literal => |v| v,
        .pipe => |p| evaluate(a, p.right, try evaluate(a, p.left, value, message), message),
        .type_of => .{ .string = switch (value) {
            .null => "null",
            .bool => "boolean",
            .string => "string",
            .int, .float, .decimal => "number",
            .array => "array",
            .object => "object",
        } },
        .object => |fields| blk: {
            const out = try a.create(Object);
            out.* = .empty;
            for (fields) |f| try out.put(a, f.key, try evaluate(a, f.value, value, message));
            break :blk .{ .object = out };
        },
        .length => switch (value) {
            .string => |s| .{ .int = @intCast(std.unicode.utf8CountCodepoints(s) catch s.len) },
            .array => |arr| .{ .int = @intCast(arr.len) },
            .object => |obj| .{ .int = @intCast(obj.count()) },
            else => {
                message.* = "length requires a string, array, or object";
                return error.Raised;
            },
        },
        .to_entries => blk: {
            var entries: std.ArrayList(Val) = .empty;
            switch (value) {
                .object => |obj| {
                    var it = obj.iterator();
                    while (it.next()) |e| {
                        const row = try a.create(Object);
                        row.* = .empty;
                        try row.put(a, "key", .{ .string = e.key_ptr.* });
                        try row.put(a, "value", e.value_ptr.*);
                        try entries.append(a, .{ .object = row });
                    }
                },
                .array => |arr| {
                    for (arr, 0..) |item, i| {
                        const row = try a.create(Object);
                        row.* = .empty;
                        try row.put(a, "key", .{ .int = @intCast(i) });
                        try row.put(a, "value", item);
                        try entries.append(a, .{ .object = row });
                    }
                },
                else => {
                    message.* = "to_entries requires an array or object";
                    return error.Raised;
                },
            }
            break :blk .{ .array = entries.items };
        },
        .index => |ix| blk: {
            const obj = try evaluate(a, ix.base, value, message);
            break :blk switch (ix.key) {
                .number => |n| switch (obj) {
                    .array => |arr| if (n >= 0 and n < arr.len) arr[@intCast(n)] else .null,
                    else => {
                        message.* = "index requires an array index or object key";
                        return error.Raised;
                    },
                },
                .string => |k| switch (obj) {
                    .object => |o| o.get(k) orelse .null,
                    else => {
                        message.* = "index requires an array index or object key";
                        return error.Raised;
                    },
                },
            };
        },
        .eq, .ne => |bin| blk: {
            const left = try evaluate(a, bin.left, value, message);
            const right = try evaluate(a, bin.right, value, message);
            const equal = typedEql(left, right);
            break :blk .{ .bool = if (expr.* == .eq) equal else !equal };
        },
        .@"and" => |bin| blk: {
            const left = truth(try evaluate(a, bin.left, value, message));
            break :blk .{ .bool = left and truth(try evaluate(a, bin.right, value, message)) };
        },
        .@"or" => |bin| blk: {
            const left = truth(try evaluate(a, bin.left, value, message));
            break :blk .{ .bool = left or truth(try evaluate(a, bin.right, value, message)) };
        },
        .has => |arg_expr| blk: {
            const arg = try evaluate(a, arg_expr, value, message);
            break :blk switch (value) {
                .object => |obj| if (arg == .string) .{ .bool = obj.contains(arg.string) } else {
                    message.* = "has requires an object key or array index";
                    return error.Raised;
                },
                .array => |arr| if (arg == .int) .{ .bool = arg.int >= 0 and arg.int < arr.len } else {
                    message.* = "has requires an object key or array index";
                    return error.Raised;
                },
                else => {
                    message.* = "has requires an object key or array index";
                    return error.Raised;
                },
            };
        },
        .contains, .split => |arg_expr| blk: {
            const arg = try evaluate(a, arg_expr, value, message);
            if (value != .string or arg != .string) {
                message.* = if (expr.* == .contains) "contains requires string input and argument" else "split requires string input and argument";
                return error.Raised;
            }
            if (expr.* == .contains) break :blk .{ .bool = std.mem.indexOf(u8, value.string, arg.string) != null };
            if (arg.string.len == 0) {
                var chars: std.ArrayList(Val) = .empty;
                var i: usize = 0;
                while (i < value.string.len) {
                    const len = std.unicode.utf8ByteSequenceLength(value.string[i]) catch 1;
                    try chars.append(a, .{ .string = value.string[i .. i + len] });
                    i += len;
                }
                break :blk .{ .array = chars.items };
            }
            var parts: std.ArrayList(Val) = .empty;
            var it = std.mem.splitSequence(u8, value.string, arg.string);
            while (it.next()) |part| try parts.append(a, .{ .string = part });
            break :blk .{ .array = parts.items };
        },
    };
}

fn isInvocation(stmt: *const Statement, name: []const u8) bool {
    if (stmt.kind() != .extension_invocation) return false;
    const inv = stmt.data.extension_invocation;
    return std.mem.eql(u8, inv.resolved_module, TRANSFORM_MODULE) and std.mem.eql(u8, inv.resolved_extension.name, name);
}

fn clauseExpression(a: Allocator, invocation: *const Statement, message: *[]const u8) Error!*Expr {
    const inv = invocation.data.extension_invocation;
    if (inv.argument == null or invocation.statements.items.len != 0) {
        message.* = "xt:if and xt:apply each require an expression and no body";
        return error.Raised;
    }
    return compile(a, inv.argument.?, message);
}

const Rule = struct { condition: *Expr, action: *Expr };

fn normalizationRule(a: Allocator, invocation: *const Statement, message: *[]const u8) Error!?Rule {
    if (!isInvocation(invocation, "normalize")) return null;
    if (invocation.data.extension_invocation.argument != null) {
        message.* = "xt:normalize does not take an argument";
        return error.Raised;
    }
    const parts = invocation.statements.items;
    if (parts.len == 1 and isInvocation(parts[0], "apply")) {
        const always = try a.create(Expr);
        always.* = .{ .literal = .{ .bool = true } };
        return .{ .condition = always, .action = try clauseExpression(a, parts[0], message) };
    }
    if (parts.len == 2 and isInvocation(parts[0], "if") and isInvocation(parts[1], "apply")) {
        return .{
            .condition = try clauseExpression(a, parts[0], message),
            .action = try clauseExpression(a, parts[1], message),
        };
    }
    message.* = "xt:normalize requires xt:apply, optionally preceded by xt:if";
    return error.Raised;
}

fn moduleOption(invocation: *const Statement, message: *[]const u8) Error!?struct { []const u8, bool } {
    if (!isInvocation(invocation, "expand-dotted-keys")) return null;
    const inv = invocation.data.extension_invocation;
    const arg = inv.argument orelse {
        message.* = "xt:expand-dotted-keys requires true or false and no body";
        return error.Raised;
    };
    if ((!std.mem.eql(u8, arg, "true") and !std.mem.eql(u8, arg, "false")) or invocation.statements.items.len != 0) {
        message.* = "xt:expand-dotted-keys requires true or false and no body";
        return error.Raised;
    }
    return .{ "expand_dotted_keys", std.mem.eql(u8, arg, "true") };
}

pub const ExpandedObject = struct {
    object: *Object,
    pointers: std.StringHashMapUnmanaged([]const u8) = .empty,
};

fn joinPointer(a: Allocator, prefix: []const u8, token: []const u8) error{OutOfMemory}![]const u8 {
    const escaped = if (std.mem.findAny(u8, token, "~/") == null) token else blk: {
        const t1 = try std.mem.replaceOwned(u8, a, token, "~", "~0");
        break :blk try std.mem.replaceOwned(u8, a, t1, "/", "~1");
    };
    return a.print("{s}/{s}", .{ prefix, escaped });
}

pub fn expandDottedObject(
    a: Allocator,
    data: *const Object,
    prefix: []const u8,
    wrappers: *std.AutoHashMapUnmanaged(*Object, *ExpandedObject),
) Error!struct { ExpandedObject, ?struct { []const u8, []const u8 } } {
    const wrap = struct {
        fn call(allocator: Allocator, map: *std.AutoHashMapUnmanaged(*Object, *ExpandedObject), obj: *Object, seed: []const u8) error{OutOfMemory}!*ExpandedObject {
            if (map.get(obj)) |w| return w;
            const w = try allocator.create(ExpandedObject);
            w.* = .{ .object = obj };
            for (obj.keys()) |k| try w.pointers.put(allocator, k, try joinPointer(allocator, seed, k));
            try map.put(allocator, obj, w);
            return w;
        }
    }.call;

    // Reuse an already-expanded object so nested walks keep original dotted pointers.
    if (wrappers.get(@constCast(data))) |existing| return .{ existing.*, null };

    const root_obj = try a.create(Object);
    root_obj.* = .empty;
    var it = data.iterator();
    while (it.next()) |e| try root_obj.put(a, e.key_ptr.*, e.value_ptr.*);
    const root = try wrap(a, wrappers, root_obj, prefix);

    var dotted: std.ArrayList([]const u8) = .empty;
    for (root.object.keys()) |key| if (std.mem.indexOfScalar(u8, key, '.') != null) try dotted.append(a, key);
    for (dotted.items) |key| {
        const value = root.object.fetchSwapRemove(key).?.value;
        const pointer = root.pointers.fetchRemove(key).?.value;
        var parts_it = std.mem.splitScalar(u8, key, '.');
        var parts: std.ArrayList([]const u8) = .empty;
        while (parts_it.next()) |part| {
            if (part.len == 0) return .{ root.*, .{ pointer, try a.print("invalid dotted key {f}", .{repr(key)}) } };
            try parts.append(a, part);
        }
        var current = root;
        for (parts.items[0 .. parts.items.len - 1]) |part| {
            if (current.object.get(part)) |existing| {
                if (existing != .object) {
                    return .{ root.*, .{ pointer, try a.print("dotted key {f} conflicts with {f}", .{ repr(key), repr(part) }) } };
                }
                const prior = if (wrappers.get(existing.object)) |w| w else try wrap(a, wrappers, existing.object, pointer);
                const copy = try a.create(Object);
                copy.* = .empty;
                var cit = prior.object.iterator();
                while (cit.next()) |ce| try copy.put(a, ce.key_ptr.*, ce.value_ptr.*);
                const child = try a.create(ExpandedObject);
                child.* = .{ .object = copy };
                var pit = prior.pointers.iterator();
                while (pit.next()) |pe| try child.pointers.put(a, pe.key_ptr.*, pe.value_ptr.*);
                try wrappers.put(a, copy, child);
                try current.object.put(a, part, .{ .object = copy });
                current = child;
            } else {
                const child_obj = try a.create(Object);
                child_obj.* = .empty;
                try current.object.put(a, part, .{ .object = child_obj });
                try current.pointers.put(a, part, pointer);
                current = try wrap(a, wrappers, child_obj, pointer);
                current.pointers.clearRetainingCapacity();
            }
        }
        const final = parts.items[parts.items.len - 1];
        if (current.object.contains(final)) {
            return .{ root.*, .{ pointer, try a.print("dotted key {f} conflicts with an existing member", .{repr(key)}) } };
        }
        try current.object.put(a, final, value);
        try current.pointers.put(a, final, pointer);
    }
    return .{ root.*, null };
}

pub fn memberPointer(expanded: ?*const ExpandedObject, key: []const u8, prefix: []const u8, a: Allocator) error{OutOfMemory}![]const u8 {
    if (expanded) |e| if (e.pointers.get(key)) |p| return p;
    return joinPointer(a, prefix, key);
}

pub const Normalization = struct {
    a: Allocator,
    expand_dotted_keys: bool = false,
    compiled: std.AutoHashMapUnmanaged(*const Statement, []const Rule) = .empty,
    module_rules: ?[]const Rule = null,
    message: []const u8 = "",

    pub fn init(a: Allocator, module: *Module, message: *[]const u8) Error!Normalization {
        var self: Normalization = .{ .a = a };
        var seen: std.StringHashMapUnmanaged(void) = .empty;
        for (module.statements.items) |statement| {
            if (try moduleOption(statement, message)) |option| {
                const name, const value = option;
                if (seen.contains(name)) {
                    message.* = try a.print("duplicate module option {f}", .{repr(name)});
                    return error.Raised;
                }
                try seen.put(a, name, {});
                if (std.mem.eql(u8, name, "expand_dotted_keys")) self.expand_dotted_keys = value;
            }
        }
        self.message = message.*;
        return self;
    }

    pub fn rules(self: *Normalization, schema: ?*const Statement, statements: []const *Statement) Error![]const Rule {
        if (schema) |s| {
            if (self.compiled.get(s)) |found| return found;
            var out: std.ArrayList(Rule) = .empty;
            for (statements) |statement| {
                if (try normalizationRule(self.a, statement, &self.message)) |rule| try out.append(self.a, rule);
            }
            try self.compiled.put(self.a, s, out.items);
            return out.items;
        }
        if (self.module_rules) |found| return found;
        var out: std.ArrayList(Rule) = .empty;
        for (statements) |statement| {
            if (try normalizationRule(self.a, statement, &self.message)) |rule| try out.append(self.a, rule);
        }
        self.module_rules = out.items;
        return out.items;
    }

    pub fn prepareModule(self: *Normalization, module: *Module, child_fn: anytype, walk: anytype) Error!void {
        _ = try self.rules(null, module.statements.items);
        for (try child_fn(walk, null)) |child| try self.prepareStmt(child, child_fn, walk);
    }

    pub fn prepareStmt(self: *Normalization, schema: *const Statement, child_fn: anytype, walk: anytype) Error!void {
        for (schema.statements.items) |statement| {
            if (try moduleOption(statement, &self.message) != null) {
                self.message = "xt:expand-dotted-keys is allowed only at module level";
                return error.Raised;
            }
        }
        _ = try self.rules(schema, schema.statements.items);
        for (try child_fn(walk, schema)) |child| try self.prepareStmt(child, child_fn, walk);
    }

    pub fn visit(self: *Normalization, schema: ?*const Statement, statements: []const *Statement, value: Val) Error!struct { Val, ?[]const u8 } {
        var current = value;
        for (try self.rules(schema, statements)) |rule| {
            const cond = evaluate(self.a, rule.condition, current, &self.message) catch |err| switch (err) {
                error.Raised => return .{ current, self.message },
                else => return err,
            };
            if (!truth(cond)) continue;
            current = evaluate(self.a, rule.action, current, &self.message) catch |err| switch (err) {
                error.Raised => return .{ current, self.message },
                else => return err,
            };
        }
        return .{ current, null };
    }
};

test "compile and evaluate split pipe object" {
    var arena_state: std.heap.ArenaAllocator = .init(std.testing.allocator);
    defer arena_state.deinit();
    const a = arena_state.allocator();
    var message: []const u8 = "";
    const expr = try compile(a, "split(\"-\") | {left: .[0], right: .[1]}", &message);
    const got = try evaluate(a, expr, .{ .string = "a-b" }, &message);
    try std.testing.expect(got == .object);
    try std.testing.expectEqualStrings("a", got.object.get("left").?.string);
    try std.testing.expectEqualStrings("b", got.object.get("right").?.string);
}

test "length equals integer literal" {
    var arena_state: std.heap.ArenaAllocator = .init(std.testing.allocator);
    defer arena_state.deinit();
    const a = arena_state.allocator();
    var message: []const u8 = "";
    const expr = try compile(a, "length == 2", &message);
    const obj = try a.create(Object);
    obj.* = .empty;
    try obj.put(a, "a", .null);
    try obj.put(a, "b", .null);
    const got = try evaluate(a, expr, .{ .object = obj }, &message);
    try std.testing.expect(got == .bool and got.bool);
}

test "dotted expansion keeps the original member pointer" {
    var arena_state: std.heap.ArenaAllocator = .init(std.testing.allocator);
    defer arena_state.deinit();
    const a = arena_state.allocator();
    const root = try a.create(Object);
    root.* = .empty;
    try root.put(a, "bgp.as", .{ .int = 65000 });
    var wrappers: std.AutoHashMapUnmanaged(*Object, *ExpandedObject) = .empty;
    const expanded, const err = try expandDottedObject(a, root, "", &wrappers);
    try std.testing.expect(err == null);
    try std.testing.expect(expanded.object.get("bgp") != null);
    const nested = expanded.object.get("bgp").?.object;
    const nested_wrap = wrappers.get(nested).?;
    try std.testing.expectEqualStrings("/bgp.as", nested_wrap.pointers.get("as").?);
}

test "to_entries then key index" {
    var arena_state: std.heap.ArenaAllocator = .init(std.testing.allocator);
    defer arena_state.deinit();
    const a = arena_state.allocator();
    var message: []const u8 = "";
    const expr = try compile(a, "to_entries | .[0][\"key\"]", &message);
    const obj = try a.create(Object);
    obj.* = .empty;
    try obj.put(a, "left", .null);
    try obj.put(a, "right", .null);
    const got = try evaluate(a, expr, .{ .object = obj }, &message);
    try std.testing.expectEqualStrings("left", got.string);
}
