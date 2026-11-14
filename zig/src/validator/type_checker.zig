//! Checks a data value against a `type` statement (mirrors
//! `src/xyang/validator/type_checker.py`). Returns `(code, message)` issues; empty means
//! valid. Built-ins dispatch through `types/registry.zig`.
//!
//! `leafref` and `instance-identifier` with `require-instance true` resolve through the
//! XPath evaluator from `ctx`: the leaf or leaf-list item being checked is `current()`
//! (RFC 7950 9.9.2).

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const pyfmt = @import("../pyfmt.zig");
const module_mod = @import("../module.zig");
const registry = @import("../types/registry.zig");
const identity_graph = @import("../identity_graph.zig");
const xpath = @import("../xpath/xpath.zig");
const pychars = @import("../xpath/pychars.zig");

const Allocator = std.mem.Allocator;
const Module = module_mod.Module;
const TypeStmt = ast.TypeStmt;
const Val = jv.Val;
const repr = pyfmt.repr;
pub const Issue = registry.Issue;

/// `Unsupported`: a construct this port cannot check yet. `Raised`: Python raises a
/// `ValueError` out of validation (the CLI prints it as `Error: ...`). Both set the
/// checker's `unsupported` message.
pub const Error = error{ OutOfMemory, Unsupported, Raised };

/// Integer or float operand of a range comparison (Python `int` / `float`).
pub const Num = union(enum) {
    int: i128,
    float: f64,

    fn asFloat(n: Num) f64 {
        return switch (n) {
            .int => |i| @floatFromInt(i),
            .float => |f| f,
        };
    }

    fn lt(x: Num, y: Num) bool {
        if (x == .int and y == .int) return x.int < y.int;
        return x.asFloat() < y.asFloat();
    }

    pub fn format(n: Num, w: *std.Io.Writer) std.Io.Writer.Error!void {
        switch (n) {
            .int => |i| try w.print("{d}", .{i}),
            .float => |f| try jv.floatRepr(f).format(w),
        }
    }
};

const Band = struct { lo: ?Num, hi: ?Num };

pub const TypeChecker = struct {
    a: Allocator,
    /// `root_schema`: the host module the validator runs against.
    root: *Module,
    /// False when the validator's root schema is an RFC 8791 structure, not a module:
    /// Python then cannot check an identityref.
    module_schema: bool = true,
    /// Set with `error.Unsupported` / `error.Raised`: the message.
    unsupported: ?[]const u8 = null,
    /// XPath context of the value being checked; null is a value outside the instance
    /// tree (`Node(None, module)`, as `encoding.instance._accepts` checks one).
    ctx: ?xpath.Context = null,

    fn fail(self: *TypeChecker, err: Error, comptime fmt: []const u8, args: anytype) Error {
        self.unsupported = try std.fmt.allocPrint(self.a, fmt, args);
        return err;
    }

    /// `check` with `ctx` as the XPath context.
    pub fn checkIn(self: *TypeChecker, value: Val, t: *const TypeStmt, ctx: xpath.Context) Error![]const Issue {
        const saved = self.ctx;
        self.ctx = ctx;
        defer self.ctx = saved;
        return self.check(value, t);
    }

    fn context(self: *TypeChecker) Error!xpath.Context {
        if (self.ctx) |c| return c;
        const root = try xpath.node.newNode(self.a, .null, .{ .module = self.root }, null);
        return .{ .current = root, .root = root };
    }

    fn evaluator(self: *TypeChecker) xpath.Evaluator {
        return .{ .a = self.a };
    }

    fn one(self: *TypeChecker, i: ?Issue) Error![]const Issue {
        const it = i orelse return &.{};
        const out = try self.a.alloc(Issue, 1);
        out[0] = it;
        return out;
    }

    fn issue(self: *TypeChecker, code: []const u8, comptime fmt: []const u8, args: anytype) Error![]const Issue {
        return self.one(.{ .code = code, .message = try std.fmt.allocPrint(self.a, fmt, args) });
    }

    pub fn check(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        const name = t.name;
        if (t.prefix) |prefix| {
            const scope = (t.scope orelse self.root).definingModule();
            if (scope.resolvePrefixedModule(prefix) == null) {
                return self.issue("type", "unknown type prefix {f} in type {f}", .{ repr(prefix), repr(name) });
            }
            if (module_mod.resolveTypedef(t, self.root)) |r| {
                if (r.typedef.data.typedef.type) |inner| return self.checkTypedefReference(value, t, inner);
            }
            return self.issue("type", "unknown typedef {f} in imported module {f}", .{ repr(name), repr(prefix) });
        }
        if (registry.get(name)) |spec| return self.checkBuiltin(spec, value, t);
        if (registry.isIntegerName(name)) return self.checkInteger(value, t);
        if (registry.isDecimalName(name)) return self.checkDecimal(value, t);
        if (module_mod.resolveTypedef(t, self.root)) |r| {
            if (r.typedef.data.typedef.type) |inner| return self.checkTypedefReference(value, t, inner);
        }
        return &.{};
    }

    fn checkBuiltin(self: *TypeChecker, spec: *const registry.Builtin, value: Val, t: *const TypeStmt) Error![]const Issue {
        return switch (spec.family) {
            .@"union" => self.checkUnion(value, t),
            .leafref => self.checkLeafref(value, t),
            .identityref => self.checkIdentityref(value, t),
            .@"instance-identifier" => self.checkInstanceIdentifier(value, t),
            .string => self.checkString(value, t),
            .integer => self.checkInteger(value, t),
            .decimal => self.checkDecimal(value, t),
            .binary => self.checkBinary(value, t),
            .boolean, .enumeration, .bits, .empty => self.one(try spec.checkValue(self.a, value, t)),
        };
    }

    /// The typedef chain first, then the restrictions written on the referring `type`
    /// (RFC 7950 9.2.4).
    fn checkTypedefReference(self: *TypeChecker, value: Val, t: *const TypeStmt, typedef_type: *const TypeStmt) Error![]const Issue {
        const errors = try self.check(value, typedef_type);
        if (errors.len > 0 or !hasRestrictions(t)) return errors;
        return self.checkRestrictionsOnBuiltin(value, t);
    }

    /// `_builtin_name`: follow typedefs to the underlying built-in name.
    fn builtinName(self: *TypeChecker, t: *const TypeStmt) []const u8 {
        var current = t;
        var schema: *Module = self.root;
        var seen: [64]*const TypeStmt = undefined;
        for (0..64) |i| {
            for (seen[0..i]) |s| {
                if (std.mem.eql(u8, s.name, current.name) and optEql(s.prefix, current.prefix)) return current.name;
            }
            seen[i] = current;
            const r = module_mod.resolveTypedef(current, schema) orelse return current.name;
            const inner = r.typedef.data.typedef.type orelse return current.name;
            schema = r.module;
            current = inner;
        }
        return current.name;
    }

    fn checkRestrictionsOnBuiltin(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        const builtin = self.builtinName(t);
        if (registry.isIntegerName(builtin)) return self.checkInteger(value, t);
        if (registry.isDecimalName(builtin)) return self.checkDecimal(value, t);
        if (std.mem.eql(u8, builtin, registry.BINARY)) return self.checkBinary(value, t);
        if (std.mem.eql(u8, builtin, registry.STRING)) return self.checkString(value, t);
        return &.{};
    }

    fn checkIdentityref(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (try registry.get(registry.IDENTITYREF).?.checkValue(self.a, value, t)) |gate| return self.one(gate);
        if (!self.module_schema) return self.issue("identityref", "identityref validation requires module schema", .{});
        const s = value.string;
        const bases = t.identityBases();
        if (bases.len == 0) return self.issue("identityref", "identityref type has no base identities", .{});
        if (identity_graph.resolveValue(self.root, s) == null) {
            return self.issue("identityref", "identityref value {f} does not resolve to a known identity", .{repr(s)});
        }
        var scope = t.scope;
        if (scope) |sc| if (std.mem.eql(u8, sc.name, self.root.name)) {
            scope = null;
        };
        if (!try identity_graph.identityrefValueValid(self.a, self.root, s, bases, scope)) {
            var list: std.Io.Writer.Allocating = .init(self.a);
            const w = &list.writer;
            w.writeByte('[') catch return error.OutOfMemory;
            for (bases, 0..) |b, i| {
                if (i > 0) w.writeAll(", ") catch return error.OutOfMemory;
                const text = if (b.prefix) |p| try std.fmt.allocPrint(self.a, "{s}:{s}", .{ p, b.name }) else b.name;
                repr(text).format(w) catch return error.OutOfMemory;
            }
            w.writeByte(']') catch return error.OutOfMemory;
            return self.issue("identityref", "identityref value {f} is not derived from all bases {s}", .{ repr(s), list.written() });
        }
        return &.{};
    }

    fn checkInstanceIdentifier(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (try registry.get(registry.INSTANCE_IDENTIFIER).?.checkValue(self.a, value, t)) |gate| return self.one(gate);
        if (!t.requireInstance()) return &.{};
        const s = pychars.strip(value.string);
        if (s.len == 0) {
            return self.issue("instance-identifier", "instance-identifier path must not be empty when require-instance is true", .{});
        }
        var p = try xpath.Parser.init(self.a, s);
        const parsed = p.parse() catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.XPathSyntax => return self.issue("instance-identifier", "instance-identifier: invalid path expression ({s})", .{p.message}),
            error.UnknownFunction => return self.fail(error.Raised, "{s}", .{p.message}),
            error.UnsupportedNumber => return self.fail(error.Unsupported, "{s}", .{p.message}),
        };
        if (parsed.* != .path) {
            return self.issue("instance-identifier", "instance-identifier: value must be a path expression (e.g. /top/leaf)", .{});
        }
        if (!parsed.path.is_absolute) {
            return self.issue("instance-identifier", "instance-identifier: only absolute paths are supported (path must start with '/')", .{});
        }
        const ctx = try self.context();
        var ev = self.evaluator();
        const nodes = ev.evalPath(&parsed.path, ctx, ctx.root) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.XPathEval => return self.fail(error.Raised, "{s}", .{ev.message}),
        };
        if (nodes.len == 0) {
            return self.issue("instance-identifier", "instance-identifier: no instance at path {f} (require-instance is true)", .{repr(value.string)});
        }
        return &.{};
    }

    fn checkUnion(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        for (t.members()) |member| {
            if ((try self.check(value, member)).len == 0) return &.{};
        }
        var names: std.ArrayList([]const u8) = .empty;
        for (t.members()) |m| try names.append(self.a, m.name);
        return self.issue("union", "Value {f} does not match any union member type ({s})", .{ jv.pyRepr(value), try std.mem.join(self.a, ", ", names.items) });
    }

    /// require-instance: the value is the data of a node the `path` selects. A relative
    /// path starts at the leaf or leaf-list item (`ctx.current`).
    fn checkLeafref(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (!t.requireInstance()) return &.{};
        const expr = t.pathAst() orelse return &.{};
        const path = &expr.path;
        const path_str = try path.toString(self.a);
        const ctx = try self.context();
        const start = if (path.is_absolute) ctx.root else ctx.current orelse
            return self.issue("leafref", "Leafref relative path {f} requires context node", .{repr(path_str)});
        var ev = self.evaluator();
        const targets = ev.evalPath(path, ctx, start) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.XPathEval => return self.fail(error.Raised, "{s}", .{ev.message}),
        };
        for (targets) |n| if (jv.pyEql(value, n.data)) return &.{};
        return self.issue("leafref", "Leafref value {f} not found via path {f} (require-instance is true)", .{ jv.pyRepr(value), repr(path_str) });
    }

    fn checkString(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (try registry.get(registry.STRING).?.checkValue(self.a, value, t)) |gate| return self.one(gate);
        const s = value.string;
        var errors: std.ArrayList(Issue) = .empty;
        if (t.lengthRestriction().expression) |length| {
            const n: i128 = @intCast(std.unicode.utf8CountCodepoints(s) catch s.len);
            if (try self.lengthIssue(n, length, false, t.lengthRestriction().error_message, t.lengthRestriction().error_app_tag)) |i| try errors.append(self.a, i);
        }
        for (t.patterns()) |*p| {
            if (p.pattern.len == 0) continue;
            const matched = try p.compiled.?.matches(self.a, s);
            if (matched == p.invert_match) {
                const default = if (!p.invert_match)
                    try std.fmt.allocPrint(self.a, "Value {f} does not match pattern {f}", .{ repr(s), repr(p.pattern) })
                else
                    try std.fmt.allocPrint(self.a, "Value {f} matches forbidden pattern {f} (invert-match)", .{ repr(s), repr(p.pattern) });
                try errors.append(self.a, .{ .code = "pattern", .message = try violationMessage(self.a, default, p.error_message, p.error_app_tag) });
            }
        }
        if (t.enums().len > 0) {
            const known = for (t.enums()) |e| {
                if (std.mem.eql(u8, e, s)) break true;
            } else false;
            if (!known) {
                try errors.append(self.a, .{ .code = "enum", .message = try std.fmt.allocPrint(self.a, "Value {f} is not one of: {s}", .{ repr(s), try std.mem.join(self.a, ", ", t.enums()) }) });
            }
        }
        return errors.items;
    }

    fn checkInteger(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        const spec = registry.get(t.name);
        const gate = if (spec != null and spec.?.family == .integer)
            try spec.?.checkValue(self.a, value, t)
        else
            try registry.integerGate(self.a, value);
        if (gate) |g| return self.one(g);
        const n: i128 = switch (value) {
            .int => |i| i,
            .float => |f| std.math.lossyCast(i128, f),
            .decimal => |d| truncDecimal(d),
            else => unreachable,
        };
        if (t.rangeRestriction().expression) |range| {
            if (try self.rangeIssue(.{ .int = n }, range, t.rangeRestriction().error_message, t.rangeRestriction().error_app_tag)) |i| return self.one(i);
        }
        if (spec) |sp| if (sp.bounds) |b| {
            if (n < b[0]) return self.issue("range", "Value {d} is less than minimum {d}", .{ n, b[0] });
            if (n > b[1]) return self.issue("range", "Value {d} exceeds maximum {d}", .{ n, b[1] });
        };
        return &.{};
    }

    fn checkDecimal(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (try registry.get(registry.DECIMAL64).?.checkValue(self.a, value, t)) |gate| return self.one(gate);
        const n: f64 = switch (value) {
            .int => |i| @floatFromInt(i),
            .float => |f| f,
            .decimal => |d| d.toFloat(),
            else => unreachable,
        };
        if (t.rangeRestriction().expression) |range| {
            if (try self.rangeIssue(.{ .float = n }, range, t.rangeRestriction().error_message, t.rangeRestriction().error_app_tag)) |i| return self.one(i);
        }
        if (t.fractionDigits()) |fd| if (fd >= 0) {
            const text = try std.fmt.allocPrint(self.a, "{f}", .{jv.pyStr(value)});
            const s = std.mem.trim(u8, text, &std.ascii.whitespace);
            if (std.mem.indexOfScalar(u8, s, '.')) |dot| {
                if (s.len - dot - 1 > fd) {
                    return self.issue("fraction-digits", "Value has more than {d} fraction digits (decimal64 fraction-digits)", .{fd});
                }
            }
        };
        return &.{};
    }

    fn checkBinary(self: *TypeChecker, value: Val, t: *const TypeStmt) Error![]const Issue {
        if (try registry.get(registry.BINARY).?.checkValue(self.a, value, t)) |gate| return self.one(gate);
        const s = std.mem.trim(u8, value.string, &pyWhitespace);
        const decoded_len = base64DecodedLen(s) orelse return self.issue("type", "binary value is not valid base64", .{});
        if (t.lengthRestriction().expression) |length| {
            if (try self.lengthIssue(@intCast(decoded_len), length, true, t.lengthRestriction().error_message, t.lengthRestriction().error_app_tag)) |i| return self.one(i);
        }
        for (t.patterns()) |*p| {
            if (p.pattern.len == 0) continue;
            const matched = try p.compiled.?.matches(self.a, s);
            if (matched == p.invert_match) {
                const default = if (!p.invert_match)
                    try std.fmt.allocPrint(self.a, "binary value {f} does not match pattern {f}", .{ repr(s), repr(p.pattern) })
                else
                    try std.fmt.allocPrint(self.a, "binary value {f} matches forbidden pattern {f} (invert-match)", .{ repr(s), repr(p.pattern) });
                return self.one(.{ .code = "pattern", .message = try violationMessage(self.a, default, p.error_message, p.error_app_tag) });
            }
        }
        return &.{};
    }

    /// `_parse_ranges`: split on `|`, then each part on `..`; `min` / `max` are open ends.
    fn parseRanges(self: *TypeChecker, text: []const u8) Error![]const Band {
        var bands: std.ArrayList(Band) = .empty;
        var parts = std.mem.splitScalar(u8, text, '|');
        while (parts.next()) |raw| {
            const part = std.mem.trim(u8, raw, &pyWhitespace);
            if (part.len == 0) continue;
            if (std.mem.indexOf(u8, part, "..")) |dots| {
                const lo_s = std.mem.trim(u8, part[0..dots], &pyWhitespace);
                const hi_s = std.mem.trim(u8, part[dots + 2 ..], &pyWhitespace);
                try bands.append(self.a, .{
                    .lo = if (std.mem.eql(u8, lo_s, "min")) null else toNum(lo_s),
                    .hi = if (std.mem.eql(u8, hi_s, "max")) null else toNum(hi_s),
                });
            } else {
                const n = toNum(part);
                try bands.append(self.a, .{ .lo = n, .hi = n });
            }
        }
        return bands.items;
    }

    const Miss = struct { min: bool, bound: Num };

    /// `_range_miss`: below the first band's lower bound is a minimum violation; any
    /// other miss reports the greatest upper bound the value exceeds.
    fn rangeMiss(n: Num, bands: []const Band) ?Miss {
        if (bands.len == 0) return null;
        for (bands) |b| {
            const lo_ok = if (b.lo) |lo| !n.lt(lo) else true;
            const hi_ok = if (b.hi) |hi| !hi.lt(n) else true;
            if (lo_ok and hi_ok) return null;
        }
        if (bands[0].lo) |first_lo| if (n.lt(first_lo)) return .{ .min = true, .bound = first_lo };
        var exceeded: ?Num = null;
        for (bands) |b| if (b.hi) |hi| if (hi.lt(n)) {
            if (exceeded == null or exceeded.?.lt(hi)) exceeded = hi;
        };
        if (exceeded) |e| return .{ .min = false, .bound = e };
        for (bands) |b| if (b.hi) |hi| return .{ .min = false, .bound = hi };
        return .{ .min = false, .bound = n };
    }

    fn rangeIssue(self: *TypeChecker, n: Num, text: []const u8, em: ?[]const u8, tag: ?[]const u8) Error!?Issue {
        const miss = rangeMiss(n, try self.parseRanges(text)) orelse return null;
        const default = if (miss.min)
            try std.fmt.allocPrint(self.a, "Value {f} is less than minimum {f}", .{ n, miss.bound })
        else
            try std.fmt.allocPrint(self.a, "Value {f} exceeds maximum {f}", .{ n, miss.bound });
        return .{ .code = "range", .message = try violationMessage(self.a, default, em, tag) };
    }

    fn lengthIssue(self: *TypeChecker, n: i128, text: []const u8, binary: bool, em: ?[]const u8, tag: ?[]const u8) Error!?Issue {
        const miss = rangeMiss(.{ .int = n }, try self.parseRanges(text)) orelse return null;
        const default = if (binary) blk: {
            const shown: i128 = switch (miss.bound) {
                .int => |i| i,
                .float => |f| std.math.lossyCast(i128, f),
            };
            break :blk if (miss.min)
                try std.fmt.allocPrint(self.a, "binary decoded length {d} octets is less than minimum {d}", .{ n, shown })
            else
                try std.fmt.allocPrint(self.a, "binary decoded length {d} octets exceeds maximum {d}", .{ n, shown });
        } else if (miss.min)
            try std.fmt.allocPrint(self.a, "String length {d} is less than minimum {f}", .{ n, miss.bound })
        else
            try std.fmt.allocPrint(self.a, "String length {d} exceeds maximum {f}", .{ n, miss.bound });
        return .{ .code = "length", .message = try violationMessage(self.a, default, em, tag) };
    }
};

const pyWhitespace = [_]u8{ ' ', '\t', '\n', '\r', 0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x1f };

fn optEql(x: ?[]const u8, y: ?[]const u8) bool {
    if (x == null or y == null) return x == null and y == null;
    return std.mem.eql(u8, x.?, y.?);
}

/// `_type_has_restrictions`.
fn hasRestrictions(t: *const TypeStmt) bool {
    return t.rangeRestriction().expression != null or t.lengthRestriction().expression != null or t.patterns().len > 0;
}

/// `_pattern_entry_violation_message`.
fn violationMessage(a: Allocator, default: []const u8, em: ?[]const u8, tag: ?[]const u8) error{OutOfMemory}![]const u8 {
    const msg = if (em) |m| (if (m.len > 0) m else default) else default;
    if (tag) |t| if (t.len > 0) return std.fmt.allocPrint(a, "{s} (error-app-tag: {s})", .{ msg, t });
    return msg;
}

/// `_to_num`: `int(s)`, else `float(s)`, else null (an open end).
fn toNum(s: []const u8) ?Num {
    const t = std.mem.trim(u8, s, &pyWhitespace);
    if (std.fmt.parseInt(i128, t, 10)) |i| return .{ .int = i } else |_| {}
    if (std.fmt.parseFloat(f64, t)) |f| return .{ .float = f } else |_| {}
    return null;
}

/// `int(Decimal)`: truncation toward zero.
fn truncDecimal(d: jv.Decimal) i128 {
    var digits = d.digits;
    var e = d.exponent;
    if (e < 0) {
        const drop: usize = @intCast(-e);
        digits = if (drop >= digits.len) "0" else digits[0 .. digits.len - drop];
        e = 0;
    }
    var v: i128 = std.fmt.parseInt(i128, digits, 10) catch std.math.maxInt(i128);
    while (e > 0) : (e -= 1) v = std.math.mul(i128, v, 10) catch std.math.maxInt(i128);
    return if (d.negative) -v else v;
}

/// `base64.b64decode(s, validate=True)` (CPython strict `a2b_base64`): decoded length, or
/// null when Python raises `binascii.Error`.
pub fn base64DecodedLen(s: []const u8) ?usize {
    if (s.len > 0 and s[0] == '=') return null;
    var quad_pos: u8 = 0;
    var pads: u8 = 0;
    var padding_started = false;
    var out: usize = 0;
    for (s, 0..) |c, i| {
        if (c == '=') {
            padding_started = true;
            if (quad_pos >= 2) {
                pads += 1;
                if (quad_pos + pads >= 4) {
                    if (i + 1 < s.len) return null;
                    return out;
                }
            }
            continue;
        }
        const valid = std.ascii.isAlphanumeric(c) or c == '+' or c == '/';
        if (!valid) return null;
        if (padding_started) return null;
        pads = 0;
        switch (quad_pos) {
            0 => quad_pos = 1,
            1 => {
                quad_pos = 2;
                out += 1;
            },
            2 => {
                quad_pos = 3;
                out += 1;
            },
            else => {
                quad_pos = 0;
                out += 1;
            },
        }
    }
    if (quad_pos != 0) return null;
    return out;
}

test "base64 strictness follows CPython" {
    try std.testing.expectEqual(@as(?usize, 2), base64DecodedLen("abc="));
    try std.testing.expectEqual(@as(?usize, 1), base64DecodedLen("ab=="));
    try std.testing.expectEqual(@as(?usize, 3), base64DecodedLen("abcd=="));
    try std.testing.expectEqual(@as(?usize, 3), base64DecodedLen("abcd==="));
    try std.testing.expectEqual(@as(?usize, 0), base64DecodedLen(""));
    for ([_][]const u8{ "ab", "ab=", "abc", "a===", "abc==", "ab===", "=abc", "ab=c", "abcd=e", "ab =" }) |bad| {
        try std.testing.expectEqual(@as(?usize, null), base64DecodedLen(bad));
    }
}
