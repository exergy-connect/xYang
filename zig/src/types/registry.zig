//! One frozen table for how a YANG built-in maps to JSON (mirrors
//! `src/xyang/types/registry.py`). An entry records `json_encoding`, `bounds`, `pattern`
//! and the strict RFC 7951 value check. The type checker and the instance encoder call
//! this table; schema export and import (phase 6 of #165) will add their columns here.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Val = jv.Val;

pub const INT8 = "int8";
pub const INT16 = "int16";
pub const INT32 = "int32";
pub const INT64 = "int64";
pub const UINT8 = "uint8";
pub const UINT16 = "uint16";
pub const UINT32 = "uint32";
pub const UINT64 = "uint64";
pub const DECIMAL64 = "decimal64";
pub const STRING = "string";
pub const BOOLEAN = "boolean";
pub const EMPTY = "empty";
pub const ENUMERATION = "enumeration";
pub const BITS = "bits";
pub const BINARY = "binary";
pub const UNION = "union";
pub const LEAFREF = "leafref";
pub const IDENTITYREF = "identityref";
pub const INSTANCE_IDENTIFIER = "instance-identifier";

/// `(code, message)`.
pub const Issue = struct { code: []const u8, message: []const u8 };

pub const JsonEncoding = enum { number, @"string-number", string, boolean, empty };

pub const Family = enum { integer, decimal, string, boolean, empty, enumeration, bits, binary, @"union", leafref, identityref, @"instance-identifier" };

pub const CheckFn = *const fn (a: Allocator, b: *const Builtin, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue;

pub const Builtin = struct {
    name: []const u8,
    json_encoding: JsonEncoding,
    bounds: ?[2]i128,
    pattern: ?[]const u8,
    family: Family,
    check: CheckFn,

    pub fn checkValue(self: *const Builtin, a: Allocator, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
        return self.check(a, self, value, t);
    }
};

fn issue(a: Allocator, code: []const u8, comptime fmt: []const u8, args: anytype) error{OutOfMemory}!?Issue {
    return .{ .code = code, .message = try std.fmt.allocPrint(a, fmt, args) };
}

fn integerJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    return switch (value) {
        .int => null,
        .float => |f| if (std.math.isFinite(f) and @floor(f) == f) null else issue(a, "type", "Expected integer, got {s}", .{jv.jsonTypeName(value)}),
        .decimal => null,
        else => issue(a, "type", "Expected integer, got {s}", .{jv.jsonTypeName(value)}),
    };
}

fn decimalJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    return switch (value) {
        .bool, .string => issue(a, "type", "Expected number, got {s}", .{jv.jsonTypeName(value)}),
        .int, .float, .decimal => null,
        else => issue(a, "type", "Value {f} is not a valid number", .{jv.pyRepr(value)}),
    };
}

fn stringJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (value == .string) return null;
    return issue(a, "type", "Expected string, got {s}", .{jv.jsonTypeName(value)});
}

/// `value not in (True, False, "true", "false")`: Python's `==` lets `1` and `0.0` in.
fn booleanCheck(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    const ok = switch (value) {
        .string => |s| std.mem.eql(u8, s, "true") or std.mem.eql(u8, s, "false"),
        else => jv.pyEql(value, .{ .bool = true }) or jv.pyEql(value, .{ .bool = false }),
    };
    if (ok) return null;
    return issue(a, "type", "Value {f} is not a valid boolean (expected true or false)", .{jv.pyRepr(value)});
}

fn emptyCheck(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (value == .null) return null;
    return issue(a, "type", "Empty type leaf should have no value, got {f}", .{jv.pyRepr(value)});
}

fn enumerationCheck(a: Allocator, _: *const Builtin, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (t.enums.items.len == 0) {
        return issue(a, "enum", "enumeration type has no enum definitions in schema; cannot validate instance data", .{});
    }
    const text = try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(value)});
    for (t.enums.items) |e| if (std.mem.eql(u8, e, text)) return null;
    const allowed = try std.mem.join(a, ", ", t.enums.items);
    return issue(a, "enum", "Value {f} is not one of the allowed enum values: {s}", .{ jv.pyRepr(value), allowed });
}

fn bitsCheck(a: Allocator, _: *const Builtin, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    const s = switch (value) {
        .string => |s| s,
        else => return issue(a, "bits", "bits value must be a string (space-sep bit names), got {s}", .{jv.typeName(value)}),
    };
    if (t.bits.items.len == 0) return issue(a, "bits", "bits type has no bit definitions", .{});
    var seen: std.StringHashMapUnmanaged(void) = .empty;
    var it = pyWhitespaceSplit(s);
    while (it.next()) |token| {
        if (seen.contains(token)) return issue(a, "bits", "Duplicate bit {f} in bits value", .{pyfmt.repr(token)});
        try seen.put(a, token, {});
        const known = for (t.bits.items) |b| {
            if (std.mem.eql(u8, b.name, token)) break true;
        } else false;
        if (!known) {
            var names: std.ArrayList([]const u8) = .empty;
            for (t.bits.items) |b| {
                const dup = for (names.items) |n| {
                    if (std.mem.eql(u8, n, b.name)) break true;
                } else false;
                if (!dup) try names.append(a, b.name);
            }
            std.mem.sort([]const u8, names.items, {}, lessString);
            return issue(a, "bits", "Unknown bit {f}; allowed: {s}", .{ pyfmt.repr(token), try std.mem.join(a, ", ", names.items) });
        }
    }
    return null;
}

fn lessString(_: void, x: []const u8, y: []const u8) bool {
    return std.mem.order(u8, x, y) == .lt;
}

/// `str.split()` on ASCII whitespace (instance bit names are ASCII identifiers).
pub fn pyWhitespaceSplit(s: []const u8) std.mem.TokenIterator(u8, .any) {
    return std.mem.tokenizeAny(u8, s, " \t\n\r\x0b\x0c\x1c\x1d\x1e\x1f");
}

fn binaryJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (value == .string) return null;
    return issue(a, "type", "binary value must be a base64-encoded string, got {s}", .{jv.typeName(value)});
}

fn identityrefJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (value == .string) return null;
    return issue(a, "identityref", "identityref value must be a string, got {s}", .{jv.typeName(value)});
}

fn instanceIdentifierJsonError(a: Allocator, _: *const Builtin, value: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    if (value == .string) return null;
    return issue(a, "instance-identifier", "instance-identifier value must be a string, got {s}", .{jv.typeName(value)});
}

fn accept(_: Allocator, _: *const Builtin, _: Val, _: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    return null;
}

fn entry(name: []const u8, enc: JsonEncoding, bounds: ?[2]i128, pattern: ?[]const u8, family: Family, check: CheckFn) Builtin {
    return .{ .name = name, .json_encoding = enc, .bounds = bounds, .pattern = pattern, .family = family, .check = check };
}

pub const BUILTINS = [_]Builtin{
    entry(INT8, .number, .{ -128, 127 }, null, .integer, integerJsonError),
    entry(INT16, .number, .{ -32768, 32767 }, null, .integer, integerJsonError),
    entry(INT32, .number, .{ -2147483648, 2147483647 }, null, .integer, integerJsonError),
    entry(INT64, .@"string-number", .{ -9223372036854775808, 9223372036854775807 }, "^-?[0-9]+$", .integer, integerJsonError),
    entry(UINT8, .number, .{ 0, 255 }, null, .integer, integerJsonError),
    entry(UINT16, .number, .{ 0, 65535 }, null, .integer, integerJsonError),
    entry(UINT32, .number, .{ 0, 4294967295 }, null, .integer, integerJsonError),
    entry(UINT64, .@"string-number", .{ 0, 18446744073709551615 }, "^[0-9]+$", .integer, integerJsonError),
    entry(DECIMAL64, .@"string-number", null, "^-?[0-9]+(\\.[0-9]+)?$", .decimal, decimalJsonError),
    entry(STRING, .string, null, null, .string, stringJsonError),
    entry(BOOLEAN, .boolean, null, null, .boolean, booleanCheck),
    entry(EMPTY, .empty, null, null, .empty, emptyCheck),
    entry(ENUMERATION, .string, null, null, .enumeration, enumerationCheck),
    entry(BITS, .string, null, null, .bits, bitsCheck),
    entry(BINARY, .string, null, null, .binary, binaryJsonError),
    entry(UNION, .string, null, null, .@"union", accept),
    entry(LEAFREF, .string, null, null, .leafref, accept),
    entry(IDENTITYREF, .string, null, null, .identityref, identityrefJsonError),
    entry(INSTANCE_IDENTIFIER, .string, null, null, .@"instance-identifier", instanceIdentifierJsonError),
};

pub fn get(name: []const u8) ?*const Builtin {
    for (&BUILTINS) |*b| if (std.mem.eql(u8, b.name, name)) return b;
    return null;
}

fn inList(name: []const u8, comptime names: []const []const u8) bool {
    inline for (names) |n| if (std.mem.eql(u8, n, name)) return true;
    return false;
}

/// `INTEGER_TYPE_NAMES`: the integer built-ins and the legacy `integer`.
pub fn isIntegerName(name: []const u8) bool {
    if (std.mem.eql(u8, name, "integer")) return true;
    const b = get(name) orelse return false;
    return b.bounds != null;
}

/// `DECIMAL_TYPE_NAMES`.
pub fn isDecimalName(name: []const u8) bool {
    return inList(name, &.{ DECIMAL64, "number" });
}

/// `QUOTED_INTEGER_NAMES`: integers RFC 7951 encodes as strings (int64, uint64).
pub fn isQuotedIntegerName(name: []const u8) bool {
    const b = get(name) orelse return false;
    return b.json_encoding == .@"string-number" and b.bounds != null;
}

/// `STRINGISH_NAMES`: string-encoded built-ins other than `union`.
pub fn isStringishName(name: []const u8) bool {
    const b = get(name) orelse return false;
    return b.json_encoding == .string and !std.mem.eql(u8, name, UNION);
}

/// `_BUILTINS` of the encoder: the table plus the legacy `number` and `integer`.
pub fn isBuiltinOrLegacyName(name: []const u8) bool {
    return get(name) != null or inList(name, &.{ "number", "integer" });
}

/// `integer_json_error`: the JSON type gate shared by every integer type.
pub fn integerGate(a: Allocator, value: Val) error{OutOfMemory}!?Issue {
    const t: ast.TypeStmt = .{ .name = INT32 };
    return integerJsonError(a, get(INT32).?, value, &t);
}

test "registry entries" {
    try std.testing.expect(get(INT64).?.json_encoding == .@"string-number");
    try std.testing.expect(isQuotedIntegerName(UINT64));
    try std.testing.expect(!isQuotedIntegerName(DECIMAL64));
    try std.testing.expect(isIntegerName("integer"));
    try std.testing.expect(isStringishName(LEAFREF));
    try std.testing.expect(!isStringishName(UNION));
    try std.testing.expectEqual(@as(i128, 18446744073709551615), get(UINT64).?.bounds.?[1]);
}
