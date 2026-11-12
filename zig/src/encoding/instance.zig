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
    if (std.mem.indexOfAny(u8, token, "~/") == null) return token;
    const t1 = try std.mem.replaceOwned(u8, a, token, "~", "~0");
    return std.mem.replaceOwned(u8, a, t1, "/", "~1");
}

fn join(a: Allocator, prefix: []const u8, token: []const u8) error{OutOfMemory}![]const u8 {
    return std.fmt.allocPrint(a, "{s}/{s}", .{ prefix, try pointerToken(a, token) });
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
    const dot = std.mem.indexOfScalar(u8, body, '.');
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

pub const Walk = struct {
    a: Allocator,
    module: *Module,
    native: bool,
    keys: *rfc7951.MemberKeys,
    checker: *type_checker.TypeChecker,
    data_nodes_cache: std.AutoHashMapUnmanaged(*const Statement, []const *const Statement) = .empty,

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

    fn accepts(self: *Walk, value: Val, t: *const TypeStmt) Error!bool {
        return (try self.checker.check(value, t)).len == 0;
    }

    /// `decode`: the decoded value, or null when this JSON type is not the encoding of
    /// that type (`_NO`).
    pub fn decode(self: *Walk, value: Val, t: *const TypeStmt) Error!?Val {
        const eff = self.unwrap(t);
        const name = eff.name;
        if (std.mem.eql(u8, name, registry.UNION)) {
            for (eff.types.items) |member| {
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
                        const text = try std.fmt.allocPrint(self.a, "{f}", .{jv.floatRepr(f)});
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
        const parent = self.keys.parent_module;
        if (self.native) {
            if (std.mem.indexOfScalar(u8, key, ':')) |colon| {
                const mod = key[0..colon];
                const local = key[colon + 1 ..];
                if (mod.len == 0 or local.len == 0) return &.{};
                for (children) |c| {
                    if (std.mem.eql(u8, c.name, local) and std.mem.eql(u8, rfc7951.definingModuleName(c, parent), mod)) try hits.append(self.a, c);
                }
                return hits.items;
            }
            for (children) |c| if (std.mem.eql(u8, c.name, key)) try hits.append(self.a, c);
            return hits.items;
        }
        for (children) |c| {
            if (try self.keys.key(c)) |k| if (std.mem.eql(u8, k, key)) try hits.append(self.a, c);
        }
        if (hits.items.len > 0 or !at_root) return hits.items;
        const colon = std.mem.indexOfScalar(u8, key, ':') orelse return hits.items;
        const mod = key[0..colon];
        const local = key[colon + 1 ..];
        if (mod.len == 0 or local.len == 0) return &.{};
        for (children) |c| {
            if (std.mem.eql(u8, c.name, local) and std.mem.eql(u8, rfc7951.definingModuleName(c, parent), mod)) try hits.append(self.a, c);
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
        var nodes: std.ArrayList(*Node) = .empty;
        var claimed: std.AutoHashMapUnmanaged(*const Statement, void) = .empty;
        var it = data.iterator();
        while (it.next()) |e| {
            const key = e.key_ptr.*;
            const raw = e.value_ptr.*;
            const here = try join(self.a, prefix, key);
            const hits = try self.resolve(key, schema, at_root);
            if (hits.len == 0) {
                try nodes.append(self.a, try self.newNode(.{ .stmt = null, .value = raw, .pointer = here, .kind = .unknown, .input_key = key }));
                continue;
            }
            if (hits.len > 1) {
                try nodes.append(self.a, try self.errNode(null, here, .ambiguous, "ambiguous-name", try std.fmt.allocPrint(self.a, "member name '{s}' matches more than one node", .{key})));
                continue;
            }
            const stmt = hits[0];
            if (claimed.contains(stmt)) continue;
            try claimed.put(self.a, stmt, {});
            try nodes.append(self.a, try self.walkNode(raw, stmt, here));
        }
        return nodes;
    }

    fn walkNode(self: *Walk, raw: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
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
            n.children = try self.walkObject(raw.object, stmt, pointer, false);
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
        if (self.native) return std.fmt.allocPrint(self.a, "{s} is a JSON number in native mode; the default is RFC 7951", .{kind});
        return std.fmt.allocPrint(self.a, "{s} is a string in RFC 7951; pass --native-json for a JSON number", .{kind});
    }

    fn walkLeafList(self: *Walk, raw: Val, stmt: *const Statement, pointer: []const u8) Error!*Node {
        if (raw != .array) return self.errNode(stmt, pointer, .leaf_list, "type", "leaf-list must be an array");
        const n = try self.newNode(.{ .stmt = stmt, .pointer = pointer, .kind = .leaf_list });
        for (raw.array, 0..) |item, i| {
            const child = try self.walkLeaf(item, stmt, try std.fmt.allocPrint(self.a, "{s}/{d}", .{ pointer, i }));
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
            if (std.mem.indexOfScalar(u8, text, '.') != null) return .{ .float = std.fmt.parseFloat(f64, text) catch return .{ .string = text } };
            if (std.fmt.parseInt(i128, text, 10)) |i| return .{ .int = i } else |_| return .{ .string = text };
        }
        if (std.mem.eql(u8, eff.name, registry.BOOLEAN) and (std.mem.eql(u8, text, "true") or std.mem.eql(u8, text, "false"))) {
            return .{ .bool = std.mem.eql(u8, text, "true") };
        }
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
        if (std.mem.eql(u8, eff.name, registry.BOOLEAN) and (std.mem.eql(u8, text, "true") or std.mem.eql(u8, text, "false"))) {
            return .{ .bool = std.mem.eql(u8, text, "true") };
        }
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
            for (raw.array, 0..) |item, i| try entries.append(self.a, .{ .token = try std.fmt.allocPrint(self.a, "{d}", .{i}), .item = item });
        } else if (self.native and raw == .object and keys.len == 1 and allObjects(raw.object)) {
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
            if (entry.item != .object) {
                try n.children.append(self.a, try self.errNode(stmt, entry_pointer, .entry, "type", "list item must be an object"));
                continue;
            }
            var body = try self.walkObject(entry.item.object, stmt, entry_pointer, false);
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
                    try n.errors.append(self.a, .{ .code = "type", .message = try std.fmt.allocPrint(self.a, "dict key '{s}' cannot be converted to the key type", .{entry.token}) });
                } else if (present == null) {
                    try body.insert(self.a, 0, try self.newNode(.{ .stmt = kl, .value = converted.?, .pointer = key_pointer, .kind = .leaf }));
                } else if (!same(present.?.value, converted.?)) {
                    try present.?.errors.append(self.a, .{ .code = "key-mismatch", .message = try std.fmt.allocPrint(self.a, "key leaf does not match dict key '{s}'", .{entry.token}) });
                }
            };
            const e = try self.newNode(.{ .stmt = stmt, .pointer = entry_pointer, .kind = .entry });
            e.children = body;
            try n.children.append(self.a, e);
        }
        return n;
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
            continue;
        }
        if (!n.include) continue;
        const stmt = n.stmt orelse continue;
        const key = (try keys.key(stmt)) orelse stmt.name;
        const canon = try join(a, prefix, key);
        try map.put(a, canon, n.pointer);
        switch (n.kind) {
            .leaf, .anydata => try out.put(a, key, n.value),
            .container => try out.put(a, key, .{ .object = try projectLevel(a, keys, n.children.items, canon, map) }),
            .list => {
                var rows: std.ArrayList(Val) = .empty;
                for (n.children.items) |entry| {
                    if (!entry.include) continue;
                    const entry_canon = try std.fmt.allocPrint(a, "{s}/{d}", .{ canon, rows.items.len });
                    try map.put(a, entry_canon, entry.pointer);
                    try rows.append(a, .{ .object = try projectLevel(a, keys, entry.children.items, entry_canon, map) });
                }
                try out.put(a, key, .{ .array = rows.items });
            },
            .leaf_list => {
                var values: std.ArrayList(Val) = .empty;
                for (n.children.items) |item| {
                    if (!item.include) continue;
                    try map.put(a, try std.fmt.allocPrint(a, "{s}/{d}", .{ canon, values.items.len }), item.pointer);
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
            return if (rest.len > 0) std.fmt.allocPrint(a, "{s}/{s}", .{ base, rest }) else base;
        }
    }
    return pointer;
}
