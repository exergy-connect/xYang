//! Walk instance JSON as written and build one node per schema instance node (mirrors
//! `src/xyang/encoding/instance.py`).
//!
//! The input is never modified. RFC 7951 is the default; native JSON is opt-in. Encoding
//! failures stay on their node (`include = false` drops the node from the projection);
//! `project` builds the canonical tree the document validator walks, plus the map from
//! canonical JSON Pointers back to the input.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const registry = @import("../types/registry.zig");
const rfc7951 = @import("rfc7951.zig");
const type_checker = @import("../validator/type_checker.zig");
const normalize = @import("normalize.zig");
const transform_expr = @import("../ext/transform.zig");
const xpath = @import("../xpath/xpath.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const TypeStmt = ast.TypeStmt;
const Module = module_mod.Module;
const Val = jv.Val;

pub const Error = type_checker.Error;

pub const Kind = enum { unknown, ambiguous, leaf, anydata, container, list, leaf_list, leaf_list_item, entry, opaque_node };

pub const Issue = registry.Issue;

pub const Node = struct {
    stmt: ?*const Statement,
    value: Val = .null,
    pointer: []const u8,
    children: std.ArrayList(*Node) = .empty,
    kind: Kind,
    errors: std.ArrayList(Issue) = .empty,
    include: bool = true,
    input_key: []const u8 = "",
};

/// RFC 6901 reference token.
pub fn pointerToken(a: Allocator, token: []const u8) error{OutOfMemory}![]const u8 {
    if (std.mem.findAny(u8, token, "~/") == null) return token;
    const t1 = try std.mem.replaceOwned(u8, a, token, "~", "~0");
    return std.mem.replaceOwned(u8, a, t1, "/", "~1");
}

fn join(a: Allocator, prefix: []const u8, token: []const u8) error{OutOfMemory}![]const u8 {
    return a.print("{s}/{s}", .{ prefix, try pointerToken(a, token) });
}

fn isContainerKind(s: *const Statement) bool {
    return switch (s.kind()) {
        .container, .notification, .input, .output => true,
        else => false,
    };
}

fn isDataStmt(s: *const Statement) bool {
    return switch (s.kind()) {
        .leaf, .leaf_list, .list, .anydata, .anyxml, .container, .notification => true,
        else => false,
    };
}

/// `-?\d+` after `strip()`.
fn intText(s: []const u8) ?[]const u8 {
    const t = std.mem.trim(u8, s, &std.ascii.whitespace);
    const body = if (t.len > 0 and t[0] == '-') t[1..] else t;
    if (body.len == 0) return null;
    for (body) |c| if (!std.ascii.isDigit(c)) return null;
    return t;
}

/// `-?\d+(\.\d+)?` after `strip()`.
fn decText(s: []const u8) ?[]const u8 {
    const t = std.mem.trim(u8, s, &std.ascii.whitespace);
    return if (isDecText(t)) t else null;
}

pub fn isDecText(t: []const u8) bool {
    const body = if (t.len > 0 and t[0] == '-') t[1..] else t;
    const dot = std.mem.findScalar(u8, body, '.');
    const int_part = if (dot) |d| body[0..d] else body;
    if (int_part.len == 0) return false;
    for (int_part) |c| if (!std.ascii.isDigit(c)) return false;
    if (dot) |d| {
        const frac = body[d + 1 ..];
        if (frac.len == 0) return false;
        for (frac) |c| if (!std.ascii.isDigit(c)) return false;
    }
    return true;
}

/// `-?\d+` (no strip), the dict-key form.
pub fn isIntText(t: []const u8) bool {
    return intText(t) != null and std.mem.eql(u8, intText(t).?, t);
}

/// `true` / `false` exactly, as a YANG boolean key.
fn boolFromText(t: []const u8) ?bool {
    if (std.mem.eql(u8, t, "true")) return true;
    if (std.mem.eql(u8, t, "false")) return false;
    return null;
}

pub const Walk = struct {
    a: Allocator,
    module: *Module,
    native: bool,
    keys: *rfc7951.MemberKeys,
    checker: *type_checker.TypeChecker,
    data_nodes_cache: std.AutoHashMapUnmanaged(*const Statement, []const *const Statement) = .empty,
    dotted_pointers: std.AutoHashMapUnmanaged(*const jv.Object, std.StringHashMapUnmanaged([]const u8)) = .empty,
    root_input: ?*const jv.Object = null,
    root_schema: ?*const Statement = null,
    root_at_root: bool = true,
    root_canonical: ?*jv.Object = null,
    skip_projection: bool = false,
    prepared: bool = false,

    const Transform = struct { value: Val, message: ?[]const u8 = null };

    fn isTransform(stmt: *const Statement, name: []const u8) bool {
        if (stmt.kind() != .extension_invocation) return false;
        const inv = stmt.data.extension_invocation;
        return std.mem.eql(u8, inv.resolved_module, "xyang-transform") and std.mem.eql(u8, inv.resolved_extension.name, name);
    }

    fn hasNormalize(stmt: *const Statement) bool {
        for (stmt.statements.items) |child| if (isTransform(child, "normalize")) return true;
        return false;
    }

    fn applyRule(self: *Walk, value: Val, condition: *const Statement, action: *const Statement) error{OutOfMemory}!Transform {
        const test_expr = condition.data.extension_invocation.argument orelse return .{ .value = value, .message = "xt:if requires an expression" };
        const apply = action.data.extension_invocation.argument orelse return .{ .value = value, .message = "xt:apply requires an expression" };
        const tested = try self.evalExpression(test_expr, value);
        if (tested.message != null) return tested;
        const decision = tested.value;
        const selected = switch (decision) {
            .null => false,
            .bool => |b| b,
            else => true,
        };
        if (!selected) return .{ .value = value };
        return self.evaluateAction(value, apply);
    }

    fn evaluateAction(self: *Walk, value: Val, apply: []const u8) error{OutOfMemory}!Transform {
        if (try normalize.stringMapping(self.a, apply)) |mapping| {
            if (value != .string) return .{ .value = value, .message = "split requires string input and argument" };
            var rows: std.ArrayList(Val) = .empty;
            if (mapping.delimiter.len == 0) {
                var offset: usize = 0;
                while (offset < value.string.len) {
                    const width = std.unicode.utf8ByteSequenceLength(value.string[offset]) catch 1;
                    const end = @min(offset + width, value.string.len);
                    const row = try self.a.create(jv.Object);
                    row.* = .empty;
                    try row.put(self.a, mapping.field, .{ .string = value.string[offset..end] });
                    try rows.append(self.a, .{ .object = row });
                    offset = end;
                }
            } else {
                var parts = std.mem.splitSequence(u8, value.string, mapping.delimiter);
                while (parts.next()) |part| {
                    const row = try self.a.create(jv.Object);
                    row.* = .empty;
                    try row.put(self.a, mapping.field, .{ .string = part });
                    try rows.append(self.a, .{ .object = row });
                }
            }
            const result = try self.a.create(jv.Object);
            result.* = .empty;
            try result.put(self.a, mapping.target, .{ .array = rows.items });
            return .{ .value = .{ .object = result } };
        }
        if (normalize.projection(apply)) |projection| {
            if (self.skip_projection) return .{ .value = value };
            return self.projectKeys(value, projection);
        }
        return self.evalExpression(apply, value);
    }

    fn evalExpression(self: *Walk, text: []const u8, value: Val) error{OutOfMemory}!Transform {
        var message: []const u8 = "";
        const expr = transform_expr.compile(self.a, text, &message) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return .{ .value = value, .message = message },
        };
        const result = transform_expr.evaluate(self.a, expr, value, &message) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return .{ .value = value, .message = message },
        };
        return .{ .value = result };
    }

    fn projectKeys(self: *Walk, value: Val, spec: normalize.Projection) error{OutOfMemory}!Transform {
        if (value != .object) return .{ .value = value, .message = "key projection requires an object" };
        const raw_root = self.root_input orelse return .{ .value = value, .message = "key projection requires an instance root" };
        if (self.root_canonical == null) {
            var snapshot: Walk = .{ .a = self.a, .module = self.module, .native = self.native, .keys = self.keys, .checker = self.checker, .skip_projection = true };
            const nodes = snapshot.walkObject(raw_root, self.root_schema, "", self.root_at_root) catch |err| switch (err) {
                error.OutOfMemory => return error.OutOfMemory,
                else => return .{ .value = value, .message = "failed to build XPath snapshot" },
            };
            self.root_canonical = (try project(self.a, self.keys, nodes.items)).data;
        }
        var parser = try xpath.Parser.init(self.a, spec.path);
        const expression = parser.parse() catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return .{ .value = value, .message = "invalid key projection XPath" },
        };
        const root: xpath.Node = .{ .data = .{ .object = self.root_canonical.? }, .schema = if (self.root_schema) |schema| .{ .stmt = @constCast(schema) } else .{ .module = self.module } };
        var evaluator: xpath.Evaluator = .{ .a = self.a };
        const result = evaluator.eval(expression, .{ .current = &root, .root = &root }, &root) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return .{ .value = value, .message = "key projection XPath failed" },
        };
        if (result != .nodes) return .{ .value = value, .message = "keys XPath must select string nodes" };
        var names: std.StringHashMapUnmanaged(void) = .empty;
        for (result.nodes) |node| {
            if (node.data != .string) return .{ .value = value, .message = "keys XPath must select string nodes" };
            try names.put(self.a, node.data.string, {});
        }
        var has_match = false;
        for (value.object.keys()) |key| if (names.contains(key)) {
            has_match = true;
            break;
        };
        if (!has_match) return .{ .value = value };
        if (value.object.contains(spec.target)) return .{ .value = value, .message = "projection target already exists" };
        const out = try self.a.create(jv.Object);
        out.* = .empty;
        var rows: std.ArrayList(Val) = .empty;
        var it = value.object.iterator();
        while (it.next()) |entry| {
            const key = entry.key_ptr.*;
            const item = entry.value_ptr.*;
            if (!names.contains(key)) {
                try out.put(self.a, key, item);
                continue;
            }
            if (item != .null and item != .object) return .{ .value = value, .message = "projected member must be an object or null" };
            if (item == .object and item.object.contains(spec.key)) return .{ .value = value, .message = "projected key field already exists" };
            const row = try self.a.create(jv.Object);
            row.* = .empty;
            try row.put(self.a, spec.key, .{ .string = key });
            if (item == .object) {
                var fields = item.object.iterator();
                while (fields.next()) |field| try row.put(self.a, field.key_ptr.*, field.value_ptr.*);
            }
            try rows.append(self.a, .{ .object = row });
        }
        try out.put(self.a, spec.target, .{ .array = rows.items });
        return .{ .value = .{ .object = out } };
    }

    fn transform(self: *Walk, input: Val, stmt: *const Statement) error{OutOfMemory}!Transform {
        return self.transformStatements(input, stmt.statements.items);
    }

    fn transformStatements(self: *Walk, input: Val, statements: []const *Statement) error{OutOfMemory}!Transform {
        var value = input;
        for (statements) |rule| {
            if (!isTransform(rule, "normalize")) continue;
            const parts = rule.statements.items;
            if (parts.len == 1 and isTransform(parts[0], "apply")) {
                const result = try self.evaluateAction(value, parts[0].data.extension_invocation.argument orelse "");
                if (result.message != null) return result;
                value = result.value;
            } else if (parts.len == 2 and isTransform(parts[0], "if") and isTransform(parts[1], "apply")) {
                const result = try self.applyRule(value, parts[0], parts[1]);
                if (result.message != null) return result;
                value = result.value;
            } else for (parts) |condition| {
                if (!isTransform(condition, "if") or condition.statements.items.len != 1 or !isTransform(condition.statements.items[0], "apply")) return .{ .value = value, .message = "nested xt:if requires exactly one xt:apply" };
                const result = try self.applyRule(value, condition, condition.statements.items[0]);
                if (result.message != null) return result;
                value = result.value;
            }
        }
        return .{ .value = value };
    }

    fn checkExpression(self: *Walk, text: []const u8) Error!void {
        if (try normalize.stringMapping(self.a, text) != null) return;
        if (normalize.projection(text)) |spec| {
            var parser = try xpath.Parser.init(self.a, spec.path);
            _ = parser.parse() catch |err| switch (err) {
                error.OutOfMemory => return error.OutOfMemory,
                else => {
                    self.checker.unsupported = "invalid key projection XPath";
                    return error.Raised;
                },
            };
            return;
        }
        var message: []const u8 = "";
        _ = transform_expr.compile(self.a, text, &message) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => {
                self.checker.unsupported = message;
                return error.Raised;
            },
        };
    }

    fn prepareStatements(self: *Walk, statements: []const *Statement, module_level: bool) Error!void {
        var dotted_count: usize = 0;
        for (statements) |stmt| {
            if (isTransform(stmt, "expand-dotted-keys")) {
                dotted_count += 1;
                const arg = stmt.data.extension_invocation.argument orelse "";
                if (!module_level or dotted_count > 1 or stmt.statements.items.len != 0 or
                    (!std.mem.eql(u8, arg, "true") and !std.mem.eql(u8, arg, "false")))
                {
                    self.checker.unsupported = "invalid xt:expand-dotted-keys";
                    return error.Raised;
                }
            }
            if (isTransform(stmt, "normalize")) {
                const parts = stmt.statements.items;
                if (stmt.data.extension_invocation.argument != null or parts.len == 0) {
                    self.checker.unsupported = "invalid xt:normalize";
                    return error.Raised;
                }
                if (parts.len == 1 and isTransform(parts[0], "apply") and parts[0].statements.items.len == 0) {
                    try self.checkExpression(parts[0].data.extension_invocation.argument orelse "");
                } else if (parts.len == 2 and isTransform(parts[0], "if") and isTransform(parts[1], "apply")) {
                    if (parts[0].statements.items.len != 0 or parts[1].statements.items.len != 0) {
                        self.checker.unsupported = "invalid xt:normalize clauses";
                        return error.Raised;
                    }
                    try self.checkExpression(parts[0].data.extension_invocation.argument orelse "");
                    try self.checkExpression(parts[1].data.extension_invocation.argument orelse "");
                } else for (parts) |condition| {
                    if (!isTransform(condition, "if") or condition.statements.items.len != 1 or !isTransform(condition.statements.items[0], "apply") or condition.statements.items[0].statements.items.len != 0) {
                        self.checker.unsupported = "invalid nested xt:if";
                        return error.Raised;
                    }
                    try self.checkExpression(condition.data.extension_invocation.argument orelse "");
                    try self.checkExpression(condition.statements.items[0].data.extension_invocation.argument orelse "");
                }
            }
            if (stmt.kind() != .extension_invocation and stmt.statements.items.len > 0)
                try self.prepareStatements(stmt.statements.items, false);
        }
    }

    fn dottedEnabled(self: *Walk) bool {
        for (self.module.statements.items) |stmt| {
            if (stmt.kind() != .extension_invocation) continue;
            const inv = stmt.data.extension_invocation;
            if (std.mem.eql(u8, inv.resolved_module, "xyang-transform") and
                std.mem.eql(u8, inv.resolved_extension.name, "expand-dotted-keys") and
                std.mem.eql(u8, inv.argument orelse "", "true")) return true;
        }
        return false;
    }

    const Expanded = struct { object: *jv.Object, error_pointer: ?[]const u8 = null };

    fn cloneObject(self: *Walk, obj: *const jv.Object, prefix: []const u8) error{OutOfMemory}!*jv.Object {
        const result = try self.a.create(jv.Object);
        result.* = .empty;
        var pointers: std.StringHashMapUnmanaged([]const u8) = .empty;
        var it = obj.iterator();
        while (it.next()) |e| {
            try result.put(self.a, e.key_ptr.*, e.value_ptr.*);
            const pointer = if (self.dotted_pointers.get(obj)) |old| old.get(e.key_ptr.*) orelse try join(self.a, prefix, e.key_ptr.*) else try join(self.a, prefix, e.key_ptr.*);
            try pointers.put(self.a, e.key_ptr.*, pointer);
        }
        try self.dotted_pointers.put(self.a, result, pointers);
        return result;
    }

    fn expandObject(self: *Walk, obj: *const jv.Object, prefix: []const u8) error{OutOfMemory}!Expanded {
        const result = try self.cloneObject(obj, prefix);
        for (obj.keys()) |key| {
            if (std.mem.indexOfScalar(u8, key, '.') == null) continue;
            const source_map = self.dotted_pointers.getPtr(result).?;
            const pointer = source_map.get(key).?;
            const value = result.get(key).?;
            _ = result.swapRemove(key);
            _ = source_map.remove(key);
            var parts = std.mem.splitScalar(u8, key, '.');
            var part = parts.next().?;
            if (part.len == 0) return .{ .object = result, .error_pointer = pointer };
            var current = result;
            while (parts.next()) |next| {
                if (next.len == 0) return .{ .object = result, .error_pointer = pointer };
                if (parts.rest().len == 0) {
                    if (current.contains(part)) {
                        const old = current.get(part).?;
                        if (old != .object) return .{ .object = result, .error_pointer = pointer };
                        const copy = try self.cloneObject(old.object, self.dotted_pointers.get(current).?.get(part) orelse pointer);
                        try current.put(self.a, part, .{ .object = copy });
                        current = copy;
                    } else {
                        const copy = try self.a.create(jv.Object);
                        copy.* = .empty;
                        try self.dotted_pointers.put(self.a, copy, .empty);
                        try current.put(self.a, part, .{ .object = copy });
                        try self.dotted_pointers.getPtr(current).?.put(self.a, part, pointer);
                        current = copy;
                    }
                    if (current.contains(next)) return .{ .object = result, .error_pointer = pointer };
                    try current.put(self.a, next, value);
                    try self.dotted_pointers.getPtr(current).?.put(self.a, next, pointer);
                    break;
                }
                if (current.get(part)) |old| {
                    if (old != .object) return .{ .object = result, .error_pointer = pointer };
                    const copy = try self.cloneObject(old.object, self.dotted_pointers.get(current).?.get(part) orelse pointer);
                    try current.put(self.a, part, .{ .object = copy });
                    current = copy;
                } else {
                    const copy = try self.a.create(jv.Object);
                    copy.* = .empty;
                    try self.dotted_pointers.put(self.a, copy, .empty);
                    try current.put(self.a, part, .{ .object = copy });
                    try self.dotted_pointers.getPtr(current).?.put(self.a, part, pointer);
                    current = copy;
                }
                part = next;
            }
        }
        return .{ .object = result };
    }

    /// Normalize the root and build the instance tree for document validation.
    pub fn iterDocument(self: *Walk, data: Val, schema: ?*const Statement, at_root: bool) Error!std.ArrayList(*Node) {
        if (!self.prepared) {
            self.prepared = true;
            try self.prepareStatements(self.module.statements.items, true);
        }
        const statements = if (schema) |s| s.statements.items else self.module.statements.items;
        const transformed = try self.transformStatements(data, statements);
        if (transformed.message) |message| {
            var out: std.ArrayList(*Node) = .empty;
            try out.append(self.a, try self.errNode(null, "", .opaque_node, "normalize", message));
            return out;
        }
        if (transformed.value != .object) {
            var out: std.ArrayList(*Node) = .empty;
            if (data == .object) try out.append(self.a, try self.errNode(null, "", .opaque_node, "normalize", "root normalization must produce an object"));
            return out;
        }
        return self.walkObject(transformed.value.object, schema, "", at_root);
    }

    /// `_data_nodes`: data children, through `choice` and `case`.
    fn dataNodesOf(self: *Walk, out: *std.ArrayList(*const Statement), statements: []const *Statement) error{OutOfMemory}!void {
        for (statements) |s| {
            switch (s.kind()) {
                .rpc, .action, .input, .output => continue,
                .choice => {
                    for (s.data.choice.cases.items) |case| try self.dataNodesOf(out, case.statements.items);
                    for (s.statements.items) |c| if (c.kind() == .case) {
                        const dup = for (s.data.choice.cases.items) |known| {
                            if (known == c) break true;
                        } else false;
                        if (!dup) try self.dataNodesOf(out, c.statements.items);
                    };
                },
                .case => try self.dataNodesOf(out, s.statements.items),
                else => if (isDataStmt(s)) try out.append(self.a, s),
            }
        }
    }

    fn dataNodes(self: *Walk, schema: ?*const Statement) error{OutOfMemory}![]const *const Statement {
        const key = schema orelse {
            var out: std.ArrayList(*const Statement) = .empty;
            try self.dataNodesOf(&out, self.module.statements.items);
            return out.items;
        };
        if (self.data_nodes_cache.get(key)) |found| return found;
        var out: std.ArrayList(*const Statement) = .empty;
        try self.dataNodesOf(&out, key.statements.items);
        try self.data_nodes_cache.put(self.a, key, out.items);
        return out.items;
    }

    /// `_unwrap`: follow typedefs to the built-in (or the unresolved name).
    pub fn unwrap(self: *Walk, t: *const TypeStmt) *const TypeStmt {
        var current = t;
        var module: ?*Module = self.module;
        var seen: [64]*const TypeStmt = undefined;
        var n: usize = 0;
        while (n < seen.len) {
            for (seen[0..n]) |s| if (s == current) return current;
            seen[n] = current;
            n += 1;
            if (current.prefix == null and registry.isBuiltinOrLegacyName(current.name)) return current;
            const r = module_mod.resolveTypedef(current, module) orelse return current;
            current = r.typedef.data.typedef.type orelse return current;
            module = r.module;
        }
        return current;
    }

    /// `_accepts`: checked outside the instance tree; a raised error is a rejection.
    fn accepts(self: *Walk, value: Val, t: *const TypeStmt) Error!bool {
        const issues = self.checker.check(value, t) catch |err| switch (err) {
            error.Raised => return false,
            else => return err,
        };
        return issues.len == 0;
    }

    /// `decode`: the decoded value, or null when this JSON type is not the encoding of
    /// that type (`_NO`).
    pub fn decode(self: *Walk, value: Val, t: *const TypeStmt) Error!?Val {
        const eff = self.unwrap(t);
        const name = eff.name;
        if (std.mem.eql(u8, name, registry.UNION)) {
            for (eff.members()) |member| {
                const decoded = (try self.decode(value, member)) orelse continue;
                if (try self.accepts(decoded, member)) return decoded;
            }
            return value;
        }
        if (std.mem.eql(u8, name, registry.EMPTY)) {
            const is_list_null = value == .array and value.array.len == 1 and value.array[0] == .null;
            if (self.native and value == .null) return .null;
            if (!self.native and is_list_null) return .null;
            if ((self.native and is_list_null) or (!self.native and value == .null)) return null;
            return value;
        }
        if (registry.isQuotedIntegerName(name)) {
            if (self.native) {
                return switch (value) {
                    .int => value,
                    .float => |f| if (std.math.isFinite(f) and @floor(f) == f and @abs(f) < 1.7e38) Val{ .int = @intFromFloat(f) } else null,
                    else => null,
                };
            }
            if (value == .string) if (intText(value.string)) |text| {
                return Val{ .int = std.fmt.parseInt(i128, text, 10) catch return null };
            };
            return null;
        }
        if (registry.isDecimalName(name)) {
            if (self.native) {
                return switch (value) {
                    .int => |i| Val{ .decimal = try jv.Decimal.fromInt(self.a, i) },
                    .float => |f| blk: {
                        if (!std.math.isFinite(f)) break :blk null;
                        const text = try self.a.print("{f}", .{jv.floatRepr(f)});
                        break :blk Val{ .decimal = jv.Decimal.parse(self.a, text) catch break :blk null };
                    },
                    else => null,
                };
            }
            if (value == .string) if (decText(value.string)) |text| {
                return Val{ .decimal = jv.Decimal.parse(self.a, text) catch return null };
            };
            return null;
        }
        if (std.mem.eql(u8, name, registry.LEAFREF) or registry.isStringishName(name)) return value;
        if (std.mem.eql(u8, name, registry.BOOLEAN)) {
            if (value == .bool) return value;
            if (value == .string and (std.mem.eql(u8, value.string, "true") or std.mem.eql(u8, value.string, "false"))) return value;
            return null;
        }
        return value;
    }

    fn resolve(self: *Walk, key: []const u8, schema: ?*const Statement, at_root: bool) Error![]const *const Statement {
        const children = try self.dataNodes(schema);
        var hits: std.ArrayList(*const Statement) = .empty;
        if (self.native) {
            if (std.mem.findScalar(u8, key, ':')) |colon| return self.byQualifiedName(key, colon, children);
            for (children) |c| if (std.mem.eql(u8, c.name, key)) try hits.append(self.a, c);
            return hits.items;
        }
        for (children) |c| {
            if (try self.keys.key(c)) |k| if (std.mem.eql(u8, k, key)) try hits.append(self.a, c);
        }
        if (hits.items.len > 0 or !at_root) return hits.items;
        const colon = std.mem.findScalar(u8, key, ':') orelse return hits.items;
        return self.byQualifiedName(key, colon, children);
    }

    /// The `children` named `key[colon + 1 ..]` whose defining module is `key[0..colon]`.
    fn byQualifiedName(self: *Walk, key: []const u8, colon: usize, children: []const *const Statement) Error![]const *const Statement {
        const mod = key[0..colon];
        const local = key[colon + 1 ..];
        if (mod.len == 0 or local.len == 0) return &.{};
        var hits: std.ArrayList(*const Statement) = .empty;
        for (children) |c| {
            if (std.mem.eql(u8, c.name, local) and std.mem.eql(u8, rfc7951.definingModuleName(c, self.keys.parent_module), mod)) try hits.append(self.a, c);
        }
        return hits.items;
    }

    fn newNode(self: *Walk, n: Node) error{OutOfMemory}!*Node {
        const out = try self.a.create(Node);
        out.* = n;
        return out;
    }

    fn errNode(self: *Walk, stmt: ?*const Statement, pointer: []const u8, kind: Kind, code: []const u8, message: []const u8) error{OutOfMemory}!*Node {
        const n = try self.newNode(.{ .stmt = stmt, .pointer = pointer, .kind = kind, .include = false });
        try n.errors.append(self.a, .{ .code = code, .message = message });
        return n;
    }

    pub fn walkObject(self: *Walk, data: *const jv.Object, schema: ?*const Statement, prefix: []const u8, at_root: bool) Error!std.ArrayList(*Node) {
        if (!self.prepared) {
            self.prepared = true;
            try self.prepareStatements(self.module.statements.items, true);
        }
        if (self.root_input == null) {
            self.root_input = data;
            self.root_schema = schema;
            self.root_at_root = at_root;
        }
        var nodes: std.ArrayList(*Node) = .empty;
        var claimed: std.AutoHashMapUnmanaged(*const Statement, void) = .empty;
        const expanded = if (self.dottedEnabled()) try self.expandObject(data, prefix) else Expanded{ .object = @constCast(data) };
        if (expanded.error_pointer) |bad| {
            try nodes.append(self.a, try self.errNode(null, bad, .opaque_node, "normalize", "invalid or conflicting dotted key"));
            return nodes;
        }
        var it = expanded.object.iterator();
        while (it.next()) |e| {
            const key = e.key_ptr.*;
            const raw = e.value_ptr.*;
            const here = if (self.dotted_pointers.get(expanded.object)) |pointers| pointers.get(key) orelse try join(self.a, prefix, key) else try join(self.a, prefix, key);
            const hits = try self.resolve(key, schema, at_root);
            if (hits.len == 0) {
                try nodes.append(self.a, try self.newNode(.{ .stmt = null, .value = raw, .pointer = here, .kind = .unknown, .input_key = key }));
                continue;
            }
            if (hits.len > 1) {
                try nodes.append(self.a, try self.errNode(null, here, .ambiguous, "ambiguous-name", try self.a.print("member name '{s}' matches more than one node", .{key})));
                continue;
            }
            const stmt = hits[0];
            if (claimed.contains(stmt)) {
                if (self.dottedEnabled()) try nodes.append(self.a, try self.errNode(null, here, .ambiguous, "normalize", "member conflicts with another spelling of the same node"));
                continue;
            }
            try claimed.put(self.a, stmt, {});
            try nodes.append(self.a, try self.walkNode(raw, stmt, here));
        }
        return nodes;
    }

    fn walkNode(self: *Walk, input: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
        var raw = input;
        if (stmt.kind() == .list or stmt.kind() == .leaf_list) {
            if (raw == .null and hasNormalize(stmt)) raw = .{ .array = &.{} };
        } else {
            const converted = try self.transform(raw, stmt);
            if (converted.message) |message| return self.errNode(stmt, pointer, .opaque_node, "normalize", message);
            raw = converted.value;
        }
        switch (stmt.kind()) {
            .leaf => return self.walkLeaf(raw, stmt, pointer),
            .anydata, .anyxml => return self.newNode(.{ .stmt = stmt, .value = raw, .pointer = pointer, .kind = .anydata }),
            .list => return self.walkList(raw, stmt, pointer),
            .leaf_list => return self.walkLeafList(raw, stmt, pointer),
            else => {},
        }
        if (isContainerKind(stmt)) {
            if (raw != .object) return self.errNode(stmt, pointer, .container, "type", "container must be an object");
            const n = try self.newNode(.{ .stmt = stmt, .pointer = pointer, .kind = .container });
            n.children = try self.walkChildren(stmt, raw.object, pointer);
            return n;
        }
        return self.newNode(.{ .stmt = stmt, .value = raw, .pointer = pointer, .kind = .opaque_node });
    }

    fn leafType(stmt: *const Statement) ?*const TypeStmt {
        return switch (stmt.data) {
            .leaf => |d| d.type,
            .leaf_list => |d| d.type,
            else => null,
        };
    }

    fn walkLeaf(self: *Walk, raw: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
        const t = leafType(stmt) orelse return self.newNode(.{ .stmt = stmt, .value = raw, .pointer = pointer, .kind = .leaf });
        const eff = self.unwrap(t);
        const decoded = try self.decode(raw, t);
        if (decoded == null and isEncoded(eff.name)) {
            const message = if (std.mem.eql(u8, eff.name, registry.EMPTY))
                (if (self.native) "empty is null in native mode; RFC 7951 encodes empty as [null]" else "empty is [null] in RFC 7951; pass --native-json for null")
            else
                try self.hint(eff.name);
            return self.errNode(stmt, pointer, .leaf, "type", message);
        }
        return self.newNode(.{ .stmt = stmt, .value = decoded orelse raw, .pointer = pointer, .kind = .leaf });
    }

    fn isEncoded(name: []const u8) bool {
        return registry.isQuotedIntegerName(name) or registry.isDecimalName(name) or std.mem.eql(u8, name, registry.EMPTY);
    }

    fn hint(self: *Walk, kind: []const u8) error{OutOfMemory}![]const u8 {
        if (self.native) return self.a.print("{s} is a JSON number in native mode; the default is RFC 7951", .{kind});
        return self.a.print("{s} is a string in RFC 7951; pass --native-json for a JSON number", .{kind});
    }

    fn walkLeafList(self: *Walk, raw: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
        if (raw != .array) return self.errNode(stmt, pointer, .leaf_list, "type", "leaf-list must be an array");
        const n = try self.newNode(.{ .stmt = stmt, .pointer = pointer, .kind = .leaf_list });
        for (raw.array, 0..) |item, i| {
            const here = try self.a.print("{s}/{d}", .{ pointer, i });
            const converted = try self.transform(item, stmt);
            if (converted.message) |message| {
                try n.children.append(self.a, try self.errNode(stmt, here, .leaf_list_item, "normalize", message));
                continue;
            }
            const child = try self.walkLeaf(converted.value, stmt, here);
            child.kind = .leaf_list_item;
            try n.children.append(self.a, child);
        }
        return n;
    }

    fn keyNames(self: *Walk, stmt: *const Statement) error{OutOfMemory}![]const []const u8 {
        var out: std.ArrayList([]const u8) = .empty;
        const key = stmt.data.list.key orelse return out.items;
        var it = std.mem.tokenizeAny(u8, key, &std.ascii.whitespace);
        while (it.next()) |k| try out.append(self.a, k);
        return out.items;
    }

    fn keyAsNative(self: *Walk, text: []const u8, leaf: *const Statement) error{OutOfMemory}!Val {
        const t = leafType(leaf) orelse return .{ .string = text };
        const eff = self.unwrap(t);
        if (registry.isIntegerName(eff.name)) {
            if (isIntText(text)) if (std.fmt.parseInt(i128, text, 10)) |i| return .{ .int = i } else |_| {};
            return .{ .string = text };
        }
        if (registry.isDecimalName(eff.name) and isDecText(text)) {
            if (std.mem.findScalar(u8, text, '.') != null) return .{ .float = std.fmt.parseFloat(f64, text) catch return .{ .string = text } };
            if (std.fmt.parseInt(i128, text, 10)) |i| return .{ .int = i } else |_| return .{ .string = text };
        }
        if (std.mem.eql(u8, eff.name, registry.BOOLEAN)) if (boolFromText(text)) |b| return .{ .bool = b };
        return .{ .string = text };
    }

    fn convertKey(self: *Walk, text: []const u8, leaf: *const Statement) Error!?Val {
        const t = leafType(leaf) orelse return .{ .string = text };
        const input: Val = if (!self.native) .{ .string = text } else try self.keyAsNative(text, leaf);
        if (try self.decode(input, t)) |decoded| return decoded;
        const eff = self.unwrap(t);
        if (registry.isIntegerName(eff.name) and isIntText(text)) {
            if (std.fmt.parseInt(i128, text, 10)) |i| return .{ .int = i } else |_| {}
        }
        if (registry.isDecimalName(eff.name) and decText(text) != null) {
            return .{ .decimal = jv.Decimal.parse(self.a, text) catch return null };
        }
        if (std.mem.eql(u8, eff.name, registry.BOOLEAN)) if (boolFromText(text)) |b| return .{ .bool = b };
        if (registry.isStringishName(eff.name)) return .{ .string = text };
        return null;
    }

    fn findNamed(self: *Walk, schema: *const Statement, name: []const u8) error{OutOfMemory}!?*const Statement {
        for (try self.dataNodes(schema)) |c| if (std.mem.eql(u8, c.name, name)) return c;
        return null;
    }

    fn walkList(self: *Walk, raw: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
        const keys = try self.keyNames(stmt);
        const Entry = struct { token: []const u8, item: Val };
        var entries: std.ArrayList(Entry) = .empty;
        var keyed = false;
        if (raw == .array) {
            for (raw.array, 0..) |item, i| try entries.append(self.a, .{ .token = try self.a.print("{d}", .{i}), .item = item });
        } else if (self.native and raw == .object and keys.len == 1 and (allObjects(raw.object) or hasNormalize(stmt))) {
            var it = raw.object.iterator();
            while (it.next()) |e| try entries.append(self.a, .{ .token = e.key_ptr.*, .item = e.value_ptr.* });
            keyed = true;
        } else if (self.native and raw == .object and keys.len != 1) {
            return self.errNode(stmt, pointer, .list, "list-encoding", "a list with more than one key must be a JSON array (--native-json)");
        } else {
            return self.errNode(stmt, pointer, .list, "type", if (!self.native) "list must be an array" else "list must be an array or a single-key object");
        }
        const n = try self.newNode(.{ .stmt = stmt, .pointer = pointer, .kind = .list });
        const key_leaf: ?*const Statement = if (keys.len == 1) try self.findNamed(stmt, keys[0]) else null;
        for (entries.items) |entry| {
            const entry_pointer = try join(self.a, pointer, entry.token);
            const transformed = try self.transform(entry.item, stmt);
            if (transformed.message) |message| {
                try n.children.append(self.a, try self.errNode(stmt, entry_pointer, .entry, "normalize", message));
                continue;
            }
            if (transformed.value != .object) {
                try n.children.append(self.a, try self.errNode(stmt, entry_pointer, .entry, "type", "list item must be an object"));
                continue;
            }
            var body = try self.walkChildren(stmt, transformed.value.object, entry_pointer);
            if (keyed) if (key_leaf) |kl| if (kl.kind() == .leaf) {
                const converted = try self.convertKey(entry.token, kl);
                const key_token = if (kl.name.len > 0) kl.name else keys[0];
                var present: ?*Node = null;
                for (body.items) |child| {
                    if (child.stmt == kl and child.include) {
                        present = child;
                        break;
                    }
                }
                const key_pointer = if (present) |p| p.pointer else try join(self.a, entry_pointer, key_token);
                if (converted == null) {
                    try n.errors.append(self.a, .{ .code = "type", .message = try self.a.print("dict key '{s}' cannot be converted to the key type", .{entry.token}) });
                } else if (present == null) {
                    try body.insert(self.a, 0, try self.newNode(.{ .stmt = kl, .value = converted.?, .pointer = key_pointer, .kind = .leaf }));
                } else if (!same(present.?.value, converted.?)) {
                    try present.?.errors.append(self.a, .{ .code = "key-mismatch", .message = try self.a.print("key leaf does not match dict key '{s}'", .{entry.token}) });
                }
            };
            const e = try self.newNode(.{ .stmt = stmt, .pointer = entry_pointer, .kind = .entry });
            e.children = body;
            try n.children.append(self.a, e);
        }
        return n;
    }

    /// Children of a data node are named relative to the module that defines it (RFC 7951 §4).
    fn walkChildren(self: *Walk, stmt: *const Statement, data: *const jv.Object, pointer: []const u8) Error!std.ArrayList(*Node) {
        const saved = self.keys.parent_module;
        self.keys.parent_module = rfc7951.definingModuleName(stmt, saved);
        defer self.keys.parent_module = saved;
        return self.walkObject(data, stmt, pointer, false);
    }
};

fn allObjects(obj: *const jv.Object) bool {
    for (obj.values()) |v| if (v != .object) return false;
    return true;
}

/// `_same`: booleans only equal booleans; decimals compare numerically.
fn same(x: Val, y: Val) bool {
    if (x == .bool or y == .bool) return x == .bool and y == .bool and x.bool == y.bool;
    return jv.pyEql(x, y);
}

/// `encoding_errors`: `(pointer, code, message)` for encoding failures, depth first.
pub const EncodingIssue = struct { pointer: []const u8, code: []const u8, message: []const u8 };

pub fn encodingErrors(a: Allocator, nodes: []const *Node) error{OutOfMemory}![]const EncodingIssue {
    var out: std.ArrayList(EncodingIssue) = .empty;
    for (nodes) |n| try collect(a, n, &out);
    return out.items;
}

fn collect(a: Allocator, n: *const Node, out: *std.ArrayList(EncodingIssue)) error{OutOfMemory}!void {
    for (n.errors.items) |e| try out.append(a, .{ .pointer = n.pointer, .code = e.code, .message = e.message });
    for (n.children.items) |c| try collect(a, c, out);
}

pub const PointerMap = std.StringHashMapUnmanaged([]const u8);

pub const Projection = struct { data: *jv.Object, map: PointerMap };

/// `project_instance`: the canonical tree and the canonical-to-input pointer map.
pub fn project(a: Allocator, keys: *rfc7951.MemberKeys, nodes: []const *Node) error{OutOfMemory}!Projection {
    var map: PointerMap = .empty;
    const data = try projectLevel(a, keys, nodes, "", &map);
    return .{ .data = data, .map = map };
}

fn projectLevel(a: Allocator, keys: *rfc7951.MemberKeys, nodes: []const *Node, prefix: []const u8, map: *PointerMap) error{OutOfMemory}!*jv.Object {
    const out = try a.create(jv.Object);
    out.* = .empty;
    for (nodes) |n| {
        if (n.kind == .unknown) {
            try out.put(a, n.input_key, n.value);
            try map.put(a, try join(a, prefix, n.input_key), n.pointer);
            continue;
        }
        if (!n.include) continue;
        const stmt = n.stmt orelse continue;
        const key = (try keys.key(stmt)) orelse stmt.name;
        const canon = try join(a, prefix, key);
        try map.put(a, canon, n.pointer);
        switch (n.kind) {
            .leaf, .anydata => try out.put(a, key, n.value),
            .container, .list => {
                const saved = keys.parent_module;
                keys.parent_module = rfc7951.definingModuleName(stmt, saved);
                defer keys.parent_module = saved;
                if (n.kind == .container) {
                    try out.put(a, key, .{ .object = try projectLevel(a, keys, n.children.items, canon, map) });
                } else {
                    var rows: std.ArrayList(Val) = .empty;
                    for (n.children.items) |entry| {
                        if (!entry.include) continue;
                        const entry_canon = try a.print("{s}/{d}", .{ canon, rows.items.len });
                        try map.put(a, entry_canon, entry.pointer);
                        try rows.append(a, .{ .object = try projectLevel(a, keys, entry.children.items, entry_canon, map) });
                    }
                    try out.put(a, key, .{ .array = rows.items });
                }
            },
            .leaf_list => {
                var values: std.ArrayList(Val) = .empty;
                for (n.children.items) |item| {
                    if (!item.include) continue;
                    try map.put(a, try a.print("{s}/{d}", .{ canon, values.items.len }), item.pointer);
                    try values.append(a, item.value);
                }
                try out.put(a, key, .{ .array = values.items });
            },
            else => {},
        }
    }
    return out;
}

/// `remap_pointer`: rewrite a canonical walker pointer to the input pointer.
pub fn remapPointer(a: Allocator, pointer: []const u8, map: *const PointerMap) error{OutOfMemory}![]const u8 {
    if (map.count() == 0) return pointer;
    if (map.get(pointer)) |p| return p;
    var parts: std.ArrayList([]const u8) = .empty;
    var it = std.mem.splitScalar(u8, pointer, '/');
    while (it.next()) |p| try parts.append(a, p);
    var index = parts.items.len;
    while (index > 1) : (index -= 1) {
        const prefix = try std.mem.join(a, "/", parts.items[0..index]);
        if (map.get(prefix)) |base| {
            const rest = try std.mem.join(a, "/", parts.items[index..]);
            return if (rest.len > 0) a.print("{s}/{s}", .{ base, rest }) else base;
        }
    }
    return pointer;
}
