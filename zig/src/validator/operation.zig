//! rpc and action input and output instances (RFC 7950 7.14, 7.15, accessible tree 6.4.1;
//! mirrors `src/xyang/validator/operation.py`).
//!
//! The module and the caller's data are never modified. The accessible tree is built from
//! a shallow copy of the module. For an rpc, its top level holds the server data nodes plus
//! one operation node named after the rpc. For an action, the operation node is a child of
//! the container or list instance the action is invoked on; the statements on the way there
//! are copied so the module keeps its own. The operation node carries the `input` or
//! `output` body as its children.
//!
//! An action is named by the RFC 8040 3.5.3 data resource identifier of its node, the path
//! a RESTCONF client POSTs to under `{+restconf}/data`: `/module:container/list=k1,k2/action`.
//!
//! Every rejected call returns `error.Usage` with the message in `Usage.message`, where
//! Python raises `ValueError`.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const Module = module_mod.Module;
const Val = jv.Val;
const repr = pyfmt.repr;

pub const Error = error{ OutOfMemory, Usage };

/// Where a usage error's message is written.
pub const Usage = struct {
    a: Allocator,
    message: []const u8 = "",

    pub fn fail(self: *Usage, comptime fmt: []const u8, args: anytype) Error {
        self.message = try std.fmt.allocPrint(self.a, fmt, args);
        return error.Usage;
    }
};

pub const DIRECTIONS = [_][]const u8{ "input", "output" };

/// One container or list on the way to an action's parent instance. `wrappers` are the
/// `choice` / `case` statements between the previous data node and `stmt`; `keys` are the
/// decoded key values of a list instance.
pub const ParentStep = struct {
    stmt: *Statement,
    keys: ?[]const []const u8 = null,
    wrappers: []const *Statement = &.{},
};

/// The rpc or action an instance belongs to and, for an action, its parent instance.
pub const OperationTarget = struct {
    operation: *Statement,
    module_name: []const u8,
    label: []const u8,
    parents: []const ParentStep = &.{},
};

/// `check_operation_options`: reject option combinations that make no sense.
pub fn checkOptions(u: *Usage, rpc: ?[]const u8, action: ?[]const u8, direction: []const u8, context: ?Val) Error!void {
    const known = for (DIRECTIONS) |d| {
        if (std.mem.eql(u8, d, direction)) break true;
    } else false;
    if (!known) return u.fail("direction must be 'input' or 'output', got {f}", .{repr(direction)});
    if (rpc != null and action != null) return u.fail("rpc and action are mutually exclusive", .{});
    if (rpc == null and action == null) {
        if (!std.mem.eql(u8, direction, "input")) return u.fail("direction applies only together with rpc or action", .{});
        if (context != null) return u.fail("context applies only together with rpc or action", .{});
    }
    if (rpc) |r| if (r.len == 0) return u.fail("rpc must be a non-empty rpc name", .{});
    if (action) |p| {
        if (p.len == 0) return u.fail("action must be the data resource identifier of an action (RFC 8040 \u{a7}3.5.3)", .{});
        if (context == null) return u.fail("action needs context: the instance it is invoked on must be in the server data (RFC 7950 \u{a7}7.15)", .{});
    }
    if (context) |c| if (c != .object) return u.fail("context must be a JSON object", .{});
}

fn lessThan(_: void, x: []const u8, y: []const u8) bool {
    return std.mem.order(u8, x, y) == .lt;
}

/// `find_rpc`: a top-level rpc (not an action) by name.
pub fn findRpc(u: *Usage, module: *Module, name: []const u8) Error!OperationTarget {
    for (module.statements.items) |s| {
        if (s.kind() == .rpc and std.mem.eql(u8, s.name, name)) {
            return .{ .operation = s, .module_name = module.name, .label = try std.fmt.allocPrint(u.a, "rpc '{s}'", .{name}) };
        }
    }
    var known: std.ArrayList([]const u8) = .empty;
    for (module.statements.items) |s| if (s.kind() == .rpc and s.name.len > 0) try known.append(u.a, s.name);
    std.mem.sort([]const u8, known.items, {}, lessThan);
    const listing = if (known.items.len > 0) try std.mem.join(u.a, ", ", known.items) else "none";
    return u.fail("module '{s}' has no rpc '{s}' (rpcs: {s})", .{ module.name, name, listing });
}

/// `_IDENTIFIER.fullmatch`: `[A-Za-z_][A-Za-z0-9_.-]*`.
fn isIdentifier(s: []const u8) bool {
    if (s.len == 0) return false;
    if (!(std.ascii.isAlphabetic(s[0]) or s[0] == '_')) return false;
    for (s[1..]) |c| {
        if (!(std.ascii.isAlphanumeric(c) or c == '_' or c == '.' or c == '-')) return false;
    }
    return true;
}

/// `urllib.parse.unquote`: `%XX` escapes as UTF-8 bytes, invalid UTF-8 replaced by U+FFFD.
pub fn unquote(a: Allocator, s: []const u8) error{OutOfMemory}![]const u8 {
    if (std.mem.indexOfScalar(u8, s, '%') == null) return s;
    var bytes: std.ArrayList(u8) = .empty;
    var i: usize = 0;
    while (i < s.len) {
        if (s[i] == '%' and i + 2 < s.len and std.ascii.isHex(s[i + 1]) and std.ascii.isHex(s[i + 2])) {
            try bytes.append(a, std.fmt.parseInt(u8, s[i + 1 .. i + 3], 16) catch unreachable);
            i += 3;
        } else {
            try bytes.append(a, s[i]);
            i += 1;
        }
    }
    if (std.unicode.utf8ValidateSlice(bytes.items)) return bytes.items;
    var out: std.ArrayList(u8) = .empty;
    var j: usize = 0;
    while (j < bytes.items.len) {
        const len = std.unicode.utf8ByteSequenceLength(bytes.items[j]) catch 0;
        if (len > 0 and j + len <= bytes.items.len) {
            if (std.unicode.utf8Decode(bytes.items[j .. j + len])) |_| {
                try out.appendSlice(a, bytes.items[j .. j + len]);
                j += len;
                continue;
            } else |_| {}
        }
        try out.appendSlice(a, "\u{fffd}");
        j += 1;
    }
    return out.items;
}

const Segment = struct { module: ?[]const u8, name: []const u8, keys: ?[]const []const u8 };

/// `_parse_api_path`: `[(module, identifier, keys)]` for an RFC 8040 3.5.3 api-path.
fn parseApiPath(u: *Usage, text: []const u8) Error![]const Segment {
    if (!std.mem.startsWith(u8, text, "/") or std.mem.eql(u8, text, "/")) {
        return u.fail("action {f} must be a data resource identifier such as /module:list=key/action", .{repr(text)});
    }
    var out: std.ArrayList(Segment) = .empty;
    var it = std.mem.splitScalar(u8, text[1..], '/');
    while (it.next()) |raw| {
        const eq = std.mem.indexOfScalar(u8, raw, '=');
        const ident = if (eq) |e| raw[0..e] else raw;
        const colon = std.mem.lastIndexOfScalar(u8, ident, ':');
        const module_name = if (colon) |c| ident[0..c] else "";
        const name = if (colon) |c| ident[c + 1 ..] else ident;
        if ((colon != null and !isIdentifier(module_name)) or !isIdentifier(name)) {
            return u.fail("action {f}: {f} is not an api-identifier (RFC 8040 \u{a7}3.5.3)", .{ repr(text), repr(raw) });
        }
        var keys: ?[]const []const u8 = null;
        if (eq) |e| {
            var values: std.ArrayList([]const u8) = .empty;
            var kit = std.mem.splitScalar(u8, raw[e + 1 ..], ',');
            while (kit.next()) |v| try values.append(u.a, try unquote(u.a, v));
            keys = values.items;
        }
        try out.append(u.a, .{ .module = if (module_name.len > 0) module_name else null, .name = name, .keys = keys });
    }
    if (out.items[0].module == null) {
        return u.fail("action {f}: the first segment must be module-qualified (RFC 8040 \u{a7}3.5.3)", .{repr(text)});
    }
    return out.items;
}

const Found = struct { stmt: ?*Statement = null, wrappers: []const *Statement = &.{} };

/// `_find_data_child`: the data-node child of `statements` named `name` in `module_name`,
/// through choice and case.
fn findDataChild(a: Allocator, parent: []const *Statement, name: []const u8, module_name: []const u8, host: []const u8) error{OutOfMemory}!Found {
    for (parent) |s| {
        if (s.kind() == .rpc or s.kind() == .action) continue;
        if (s.kind() == .choice or s.kind() == .case) {
            var branches: std.ArrayList(*Statement) = .empty;
            if (s.kind() == .choice) {
                try branches.appendSlice(a, s.data.choice.cases.items);
                for (s.statements.items) |c| {
                    if (c.kind() == .case and std.mem.indexOfScalar(*Statement, branches.items, c) == null) try branches.append(a, c);
                }
            } else {
                try branches.append(a, s);
            }
            for (branches.items) |branch| {
                const found = try findDataChild(a, branch.statements.items, name, module_name, host);
                if (found.stmt != null) {
                    var wrappers: std.ArrayList(*Statement) = .empty;
                    try wrappers.append(a, s);
                    if (branch != s) try wrappers.append(a, branch);
                    try wrappers.appendSlice(a, found.wrappers);
                    return .{ .stmt = found.stmt, .wrappers = wrappers.items };
                }
            }
            continue;
        }
        if (std.mem.eql(u8, s.name, name) and std.mem.eql(u8, rfc7951.definingModuleName(s, host), module_name)) return .{ .stmt = s };
    }
    return .{};
}

fn isContainerClass(s: *const Statement) bool {
    return switch (s.kind()) {
        .container, .notification, .input, .output => true,
        else => false,
    };
}

/// `resolve_action`: an action's data resource identifier to its target; anything that
/// does not name one is a usage error.
pub fn resolveAction(u: *Usage, module: *Module, path: []const u8) Error!OperationTarget {
    const a = u.a;
    const segments = try parseApiPath(u, path);
    if (!std.mem.eql(u8, segments[0].module.?, module.name)) {
        return u.fail("action {f}: the first segment must be in module '{s}'", .{ repr(path), module.name });
    }
    if (segments.len < 2) return u.fail("action {f} names no container or list instance to invoke the action on", .{repr(path)});
    var parents: std.ArrayList(ParentStep) = .empty;
    var statements: []const *Statement = module.statements.items;
    var schema_name: []const u8 = module.name;
    var namespace: []const u8 = module.name;
    for (segments[0 .. segments.len - 1]) |seg| {
        namespace = seg.module orelse namespace;
        const found = try findDataChild(a, statements, seg.name, namespace, module.name);
        const stmt = found.stmt orelse {
            var names: std.ArrayList([]const u8) = .empty;
            for (parents.items) |p| try names.append(a, p.stmt.name);
            return u.fail("action {f}: no container or list '{s}:{s}' under /{s}", .{ repr(path), namespace, seg.name, try std.mem.join(a, "/", names.items) });
        };
        if (stmt.kind() == .list) {
            var key_names: std.ArrayList([]const u8) = .empty;
            if (stmt.data.list.key) |k| {
                var kit = std.mem.tokenizeAny(u8, k, &std.ascii.whitespace);
                while (kit.next()) |n| try key_names.append(a, n);
            }
            if (seg.keys == null or seg.keys.?.len != key_names.items.len) {
                return u.fail("action {f}: list '{s}' needs its {d} key value(s) ({s}) as {s}=value (RFC 8040 \u{a7}3.5.3)", .{ repr(path), seg.name, key_names.items.len, try std.mem.join(a, ", ", key_names.items), seg.name });
            }
        } else if (isContainerClass(stmt)) {
            if (seg.keys != null) return u.fail("action {f}: container '{s}' takes no key values", .{ repr(path), seg.name });
        } else {
            return u.fail("action {f}: '{s}' is not a container or list", .{ repr(path), seg.name });
        }
        try parents.append(a, .{ .stmt = stmt, .keys = seg.keys, .wrappers = found.wrappers });
        statements = stmt.statements.items;
        schema_name = stmt.name;
    }
    const last = segments[segments.len - 1];
    namespace = last.module orelse namespace;
    if (last.keys != null) return u.fail("action {f}: the action segment takes no key values", .{repr(path)});
    for (statements) |s| {
        if (s.kind() == .action and std.mem.eql(u8, s.name, last.name) and std.mem.eql(u8, rfc7951.definingModuleName(s, module.name), namespace)) {
            return .{ .operation = s, .module_name = namespace, .label = try std.fmt.allocPrint(a, "action {f}", .{repr(path)}), .parents = parents.items };
        }
    }
    var known: std.ArrayList([]const u8) = .empty;
    for (statements) |s| if (s.kind() == .action and s.name.len > 0) try known.append(a, s.name);
    std.mem.sort([]const u8, known.items, {}, lessThan);
    const listing = if (known.items.len > 0) try std.mem.join(a, ", ", known.items) else "none";
    return u.fail("action {f}: '{s}' has no action '{s}:{s}' (actions: {s})", .{ repr(path), schema_name, namespace, last.name, listing });
}

/// `find_body`: the operation's `input` or `output`, or null.
pub fn findBody(operation: *const Statement, direction: []const u8) ?*Statement {
    const wanted: ast.Kind = if (std.mem.eql(u8, direction, "input")) .input else .output;
    for (operation.statements.items) |s| if (s.kind() == wanted) return s;
    return null;
}

/// `operation_node`: the operation node of RFC 7950 6.4.1, named after the rpc or action,
/// with the parameters as children. A plain container, not the `input` / `output` kind,
/// which data-node walks skip.
pub fn operationNode(a: Allocator, operation: *const Statement, body: ?*const Statement) error{OutOfMemory}!*Statement {
    const node = try a.create(Statement);
    if (body) |b| {
        node.* = b.*;
        node.data = .{ .container = switch (b.data) {
            .input, .output => |c| c,
            else => unreachable,
        } };
    } else {
        node.* = .{ .data = .{ .container = .{} } };
    }
    node.name = operation.name;
    node.defining_module = operation.defining_module;
    return node;
}

/// `accessible_module`: a copy of `module` with the operation node in place, and the copies
/// of the parent steps. rpc: the top level is the data nodes plus `operation`; other
/// operations are left out. action: each statement from the top level down to the parent
/// is copied, and the parent's copy has `operation` in place of the action.
pub const Accessible = struct { module: *Module, parent_copies: []const *Statement };

pub fn accessibleModule(a: Allocator, module: *const Module, target: OperationTarget, operation: *Statement) error{OutOfMemory}!Accessible {
    const accessible = try module.cowCopy(a);
    if (target.parents.len == 0) {
        var kept: std.ArrayList(*Statement) = .empty;
        for (module.statements.items) |s| if (s.kind() != .rpc) try kept.append(a, s);
        try kept.append(a, operation);
        accessible.statements = kept;
        return .{ .module = accessible, .parent_copies = &.{} };
    }
    var chain: std.ArrayList(*Statement) = .empty;
    for (target.parents) |step| {
        try chain.appendSlice(a, step.wrappers);
        try chain.append(a, step.stmt);
    }
    var originals: std.ArrayList(*Statement) = .empty;
    var copies: std.ArrayList(*Statement) = .empty;
    var list: *std.ArrayList(*Statement) = &accessible.statements;
    var cases: ?*std.ArrayList(*Statement) = null;
    for (chain.items) |original| {
        const child = try a.create(Statement);
        child.* = original.*;
        child.statements = try original.statements.clone(a);
        if (child.kind() == .choice) child.data.choice.cases = try original.data.choice.cases.clone(a);
        for (list.items) |*s| if (s.* == original) {
            s.* = child;
        };
        if (cases) |cs| for (cs.items) |*c| if (c.* == original) {
            c.* = child;
        };
        try originals.append(a, original);
        try copies.append(a, child);
        list = &child.statements;
        cases = if (child.kind() == .choice) &child.data.choice.cases else null;
    }
    for (list.items) |*s| if (s.* == target.operation) {
        s.* = operation;
    };
    var parent_copies: std.ArrayList(*Statement) = .empty;
    for (target.parents) |step| {
        const i = std.mem.indexOfScalar(*Statement, originals.items, step.stmt).?;
        try parent_copies.append(a, copies.items[i]);
    }
    return .{ .module = accessible, .parent_copies = parent_copies.items };
}

/// `lexical`: canonical text of a decoded leaf value, as an RFC 8040 key value is written.
pub fn lexical(a: Allocator, v: Val) error{OutOfMemory}![]const u8 {
    return switch (v) {
        .bool => |b| if (b) "true" else "false",
        .decimal => |d| fixedDecimal(a, d),
        else => std.fmt.allocPrint(a, "{f}", .{jv.pyStr(v)}),
    };
}

/// `format(Decimal, "f")`: fixed-point notation.
fn fixedDecimal(a: Allocator, d: jv.Decimal) error{OutOfMemory}![]const u8 {
    var out: std.ArrayList(u8) = .empty;
    if (d.negative) try out.append(a, '-');
    if (d.exponent >= 0) {
        try out.appendSlice(a, d.digits);
        if (!std.mem.eql(u8, d.digits, "0")) try out.appendNTimes(a, '0', @intCast(d.exponent));
        return out.items;
    }
    const frac: usize = @intCast(-d.exponent);
    if (d.digits.len > frac) {
        try out.appendSlice(a, d.digits[0 .. d.digits.len - frac]);
        try out.append(a, '.');
        try out.appendSlice(a, d.digits[d.digits.len - frac ..]);
    } else {
        try out.appendSlice(a, "0.");
        try out.appendNTimes(a, '0', frac - d.digits.len);
        try out.appendSlice(a, d.digits);
    }
    return out.items;
}

/// `wrapper_member`: RFC 8040 3.6 member name of the operation body.
pub fn wrapperMember(a: Allocator, module_name: []const u8, direction: []const u8) error{OutOfMemory}![]const u8 {
    return std.fmt.allocPrint(a, "{s}:{s}", .{ module_name, direction });
}

test "api-path parsing and percent-decoding" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var u: Usage = .{ .a = arena.allocator() };
    const segs = try parseApiPath(&u, "/m:pair=x,2/a:swap");
    try std.testing.expectEqual(@as(usize, 2), segs.len);
    try std.testing.expectEqualStrings("m", segs[0].module.?);
    try std.testing.expectEqualStrings("2", segs[0].keys.?[1]);
    try std.testing.expectEqualStrings("a", segs[1].module.?);
    try std.testing.expectEqualStrings("eth/0", try unquote(u.a, "eth%2F0"));
    try std.testing.expectEqualStrings("100%", try unquote(u.a, "100%"));
    try std.testing.expectError(error.Usage, parseApiPath(&u, "/x/y"));
    try std.testing.expectEqualStrings("action '/x/y': the first segment must be module-qualified (RFC 8040 \u{a7}3.5.3)", u.message);
}

test "fixed-point decimal text" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    try std.testing.expectEqualStrings("1.50", try lexical(a, .{ .decimal = try jv.Decimal.parse(a, "1.50") }));
    try std.testing.expectEqualStrings("0.05", try lexical(a, .{ .decimal = try jv.Decimal.parse(a, "0.05") }));
    try std.testing.expectEqualStrings("-3", try lexical(a, .{ .decimal = try jv.Decimal.parse(a, "-3") }));
}
