//! One frozen table for how a YANG built-in maps to JSON (mirrors
//! `src/xyang/types/registry.py`). An entry records `json_encoding`, `bounds`, `pattern`,
//! the schema export (`to_schema`), the schema import (`from_schema`) and the strict
//! RFC 7951 value check. The native JSON generator and parser, the type checker and the
//! instance encoder call this table.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const pyfmt = @import("../pyfmt.zig");
const gen = @import("../json/generator.zig");
const jparse = @import("../json/parser.zig");
const K = @import("../json/schema_keys.zig");
const module_mod = @import("../module.zig");
const xutils = @import("../xpath/utils.zig");

const Allocator = std.mem.Allocator;
const Val = jv.Val;
const Object = jv.Object;

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

/// The JSON Schema fragment for one `type` (`to_schema`).
pub const ToSchemaFn = *const fn (e: gen.Emit, b: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object;

/// A JSON Schema piece plus the `x-yang` object and `$defs` (`SchemaFragment`).
pub const Fragment = struct {
    schema: *const Object,
    xyang: *const Object,
    defs: *const Object,
};

/// The `type` a JSON Schema fragment encodes, or null when it is not this built-in.
pub const FromSchemaFn = *const fn (p: *jparse.Parse, b: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt;

pub const Builtin = struct {
    name: []const u8,
    json_encoding: JsonEncoding,
    bounds: ?[2]i128,
    pattern: ?[]const u8,
    family: Family,
    to_schema: ToSchemaFn,
    from_schema: FromSchemaFn,
    check: CheckFn,

    pub fn checkValue(self: *const Builtin, a: Allocator, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
        return self.check(a, self, value, t);
    }

    pub fn toSchema(self: *const Builtin, e: gen.Emit, t: *const ast.TypeStmt) gen.Error!*Object {
        return self.to_schema(e, self, t);
    }

    pub fn fromSchema(self: *const Builtin, p: *jparse.Parse, f: Fragment) jparse.Error!?*ast.TypeStmt {
        return self.from_schema(p, self, f);
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
    if (t.enums().len == 0) {
        return issue(a, "enum", "enumeration type has no enum definitions in schema; cannot validate instance data", .{});
    }
    const text = try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(value)});
    for (t.enums()) |e| if (std.mem.eql(u8, e, text)) return null;
    const allowed = try std.mem.join(a, ", ", t.enums());
    return issue(a, "enum", "Value {f} is not one of the allowed enum values: {s}", .{ jv.pyRepr(value), allowed });
}

fn bitsCheck(a: Allocator, _: *const Builtin, value: Val, t: *const ast.TypeStmt) error{OutOfMemory}!?Issue {
    const s = switch (value) {
        .string => |s| s,
        else => return issue(a, "bits", "bits value must be a string (space-sep bit names), got {s}", .{jv.typeName(value)}),
    };
    if (t.bits().len == 0) return issue(a, "bits", "bits type has no bit definitions", .{});
    var seen: std.StringHashMapUnmanaged(void) = .empty;
    var it = pyWhitespaceSplit(s);
    while (it.next()) |token| {
        if (seen.contains(token)) return issue(a, "bits", "Duplicate bit {f} in bits value", .{pyfmt.repr(token)});
        try seen.put(a, token, {});
        const known = for (t.bits()) |b| {
            if (std.mem.eql(u8, b.name, token)) break true;
        } else false;
        if (!known) {
            var names: std.ArrayList([]const u8) = .empty;
            for (t.bits()) |b| {
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

fn entry(name: []const u8, enc: JsonEncoding, bounds: ?[2]i128, pattern: ?[]const u8, family: Family, to: ToSchemaFn, from: FromSchemaFn, check: CheckFn) Builtin {
    return .{ .name = name, .json_encoding = enc, .bounds = bounds, .pattern = pattern, .family = family, .to_schema = to, .from_schema = from, .check = check };
}

pub const BUILTINS = [_]Builtin{
    entry(INT8, .number, .{ -128, 127 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(INT16, .number, .{ -32768, 32767 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(INT32, .number, .{ -2147483648, 2147483647 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(INT64, .@"string-number", .{ -9223372036854775808, 9223372036854775807 }, "^-?[0-9]+$", .integer, toInteger, fromQuotedInteger, integerJsonError),
    entry(UINT8, .number, .{ 0, 255 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(UINT16, .number, .{ 0, 65535 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(UINT32, .number, .{ 0, 4294967295 }, null, .integer, toInteger, fromNumberInteger, integerJsonError),
    entry(UINT64, .@"string-number", .{ 0, 18446744073709551615 }, "^[0-9]+$", .integer, toInteger, fromQuotedInteger, integerJsonError),
    entry(DECIMAL64, .@"string-number", null, "^-?[0-9]+(\\.[0-9]+)?$", .decimal, toDecimal, fromDecimal, decimalJsonError),
    entry(STRING, .string, null, null, .string, toString, fromString, stringJsonError),
    entry(BOOLEAN, .boolean, null, null, .boolean, toBoolean, fromBoolean, booleanCheck),
    entry(EMPTY, .empty, null, null, .empty, toEmpty, fromEmpty, emptyCheck),
    entry(ENUMERATION, .string, null, null, .enumeration, toEnumeration, fromEnumeration, enumerationCheck),
    entry(BITS, .string, null, null, .bits, toBits, fromBits, bitsCheck),
    entry(BINARY, .string, null, null, .binary, plainString, unused, binaryJsonError),
    entry(UNION, .string, null, null, .@"union", toUnion, fromUnion, accept),
    entry(LEAFREF, .string, null, null, .leafref, toLeafref, fromLeafref, accept),
    entry(IDENTITYREF, .string, null, null, .identityref, toIdentityref, fromIdentityref, identityrefJsonError),
    entry(INSTANCE_IDENTIFIER, .string, null, null, .@"instance-identifier", toInstanceIdentifier, fromInstanceIdentifier, instanceIdentifierJsonError),
};

// ---------------------------------------------------------------------------
// Schema export (`to_schema`)

fn obj(a: Allocator) error{OutOfMemory}!*Object {
    return gen.newObject(a);
}

fn typeOnly(a: Allocator, t: []const u8) error{OutOfMemory}!*Object {
    const o = try obj(a);
    try o.put(a, K.TYPE, gen.str(t));
    return o;
}

fn plainString(e: gen.Emit, _: *const Builtin, _: *const ast.TypeStmt) gen.Error!*Object {
    return typeOnly(e.g.a, "string");
}

fn anchored(a: Allocator, p: []const u8) error{OutOfMemory}![]const u8 {
    if (std.mem.startsWith(u8, p, "^") and std.mem.endsWith(u8, p, "$")) return p;
    return std.fmt.allocPrint(a, "^{s}$", .{p});
}

fn toString(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const out = try typeOnly(a, "string");
    const specs = t.patterns();
    if (specs.len == 1 and !specs[0].invert_match) {
        if (specs[0].pattern.len > 0) try out.put(a, K.PATTERN, gen.str(try anchored(a, specs[0].pattern)));
    } else if (specs.len > 0) {
        var all_of: std.ArrayList(Val) = .empty;
        for (specs) |spec| {
            if (spec.pattern.len == 0) continue;
            const pat = try anchored(a, spec.pattern);
            const item = try obj(a);
            if (spec.invert_match) {
                const inner = try typeOnly(a, "string");
                try inner.put(a, K.PATTERN, gen.str(pat));
                try item.put(a, K.NOT, gen.objVal(inner));
            } else {
                try item.put(a, K.PATTERN, gen.str(pat));
            }
            try all_of.append(a, gen.objVal(item));
        }
        if (all_of.items.len > 0) try out.put(a, K.ALL_OF, .{ .array = all_of.items });
    }
    if (t.lengthRestriction().expression) |length| if (length.len > 0) {
        var parts = std.mem.splitSequence(u8, length, "..");
        const first = gen.pyStrip(parts.first());
        const second = if (parts.next()) |p| gen.pyStrip(p) else null;
        if (first.len > 0) if (xutils.pyInt(first)) |n| try out.put(a, K.MIN_LENGTH, .{ .int = n });
        if (second) |s| if (s.len > 0 and !std.ascii.eqlIgnoreCase(s, "max")) {
            if (xutils.pyInt(s)) |n| try out.put(a, K.MAX_LENGTH, .{ .int = n });
        };
    };
    if (specs.len > 0) {
        const entries = try a.alloc(Val, specs.len);
        for (specs, 0..) |spec, i| {
            const item = try obj(a);
            try item.put(a, K.PATTERN, gen.str(spec.pattern));
            try item.put(a, K.xy.INVERT_MATCH, .{ .bool = spec.invert_match });
            if (spec.error_message) |m| try item.put(a, K.xy.PATTERN_ERROR_MESSAGE, gen.str(m));
            if (spec.error_app_tag) |tag| try item.put(a, K.xy.PATTERN_ERROR_APP_TAG, gen.str(tag));
            entries[i] = gen.objVal(item);
        }
        const xy = try obj(a);
        try xy.put(a, K.xy.STRING_PATTERNS, .{ .array = entries });
        const last = entries[entries.len - 1].object;
        if (last.get(K.xy.PATTERN_ERROR_MESSAGE)) |m| try xy.put(a, K.xy.PATTERN_ERROR_MESSAGE, m);
        if (last.get(K.xy.PATTERN_ERROR_APP_TAG)) |tag| try xy.put(a, K.xy.PATTERN_ERROR_APP_TAG, tag);
        try out.put(a, K.X_YANG, gen.objVal(xy));
    }
    return out;
}

fn toEnumeration(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const out = try typeOnly(a, "string");
    if (t.enums().len > 0) try out.put(a, K.ENUM, try gen.strList(a, t.enums()));
    return out;
}

/// `re.escape` (Python 3.7+ escapes only the regex metacharacters).
fn reEscape(a: Allocator, s: []const u8) error{OutOfMemory}![]const u8 {
    var out: std.ArrayList(u8) = .empty;
    for (s) |c| {
        if (std.mem.indexOfScalar(u8, "()[]{}?*+-|^$\\.&~# \t\n\r\x0b\x0c", c) != null) try out.append(a, '\\');
        try out.append(a, c);
    }
    return out.items;
}

fn byLenDesc(_: void, x: []const u8, y: []const u8) bool {
    return x.len > y.len;
}

/// `_bits_space_separated_pattern`: space-separated bit names in any order.
fn bitsPattern(a: Allocator, names: []const []const u8) error{OutOfMemory}![]const u8 {
    if (names.len == 0) return "^$";
    const escaped = try a.alloc([]const u8, names.len);
    for (names, 0..) |n, i| escaped[i] = try reEscape(a, n);
    std.mem.sort([]const u8, escaped, {}, byLenDesc);
    const alt = try std.mem.join(a, "|", escaped);
    return std.fmt.allocPrint(a, "^$|^(?:{s})(?:\\s+(?:{s}))*$", .{ alt, alt });
}

fn bitLess(_: void, x: ast.BitStmt, y: ast.BitStmt) bool {
    const px = x.position orelse 0;
    const py = y.position orelse 0;
    if (px != py) return px < py;
    return std.mem.order(u8, x.name, y.name) == .lt;
}

fn toBits(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    if (t.bits().len == 0) return typeOnly(a, "string");
    const ordered = try a.dupe(ast.BitStmt, t.bits());
    std.mem.sort(ast.BitStmt, ordered, {}, bitLess);
    const bits_obj = try obj(a);
    const names = try a.alloc([]const u8, ordered.len);
    for (ordered, 0..) |bit, i| {
        try bits_obj.put(a, bit.name, .{ .int = bit.position orelse 0 });
        names[i] = bit.name;
    }
    const desc = try std.fmt.allocPrint(a, "YANG bits (RFC 7950): space-separated subset of these names (order irrelevant; no duplicate names in instance data). Positions: see x-yang.bits. Names: {s}.", .{try std.mem.join(a, ", ", names)});
    var examples: std.ArrayList(Val) = .empty;
    try examples.append(a, gen.str(""));
    try examples.append(a, gen.str(names[0]));
    if (names.len > 1) try examples.append(a, gen.str(try std.mem.join(a, " ", names)));
    const out = try typeOnly(a, "string");
    try gen.withDescription(a, out, desc);
    try out.put(a, K.PATTERN, gen.str(try bitsPattern(a, names)));
    try out.put(a, K.EXAMPLES, .{ .array = examples.items });
    const xy = try obj(a);
    try xy.put(a, K.xy.TYPE, gen.str(K.types.BITS));
    try xy.put(a, K.xy.BITS, gen.objVal(bits_obj));
    try out.put(a, K.X_YANG, gen.objVal(xy));
    return out;
}

fn toBoolean(e: gen.Emit, _: *const Builtin, _: *const ast.TypeStmt) gen.Error!*Object {
    return typeOnly(e.g.a, "boolean");
}

fn toInteger(e: gen.Emit, b: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    if (b.json_encoding == .@"string-number") {
        const out = try typeOnly(a, "string");
        try out.put(a, K.PATTERN, gen.str(b.pattern.?));
        const xy = try obj(a);
        try xy.put(a, K.xy.TYPE, gen.str(b.name));
        if (t.rangeRestriction().expression) |r| if (r.len > 0) try xy.put(a, K.xy.RANGE, gen.str(r));
        try out.put(a, K.X_YANG, gen.objVal(xy));
        return out;
    }
    const out = try typeOnly(a, "integer");
    const bounds = jsonIntegerBounds(b.name, t.rangeRestriction().expression);
    if (bounds[0]) |lo| try out.put(a, K.MINIMUM, .{ .int = lo });
    if (bounds[1]) |hi| try out.put(a, K.MAXIMUM, .{ .int = hi });
    return out;
}

fn toDecimal(e: gen.Emit, b: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const out = try typeOnly(a, "string");
    try out.put(a, K.PATTERN, gen.str(b.pattern.?));
    const xy = try obj(a);
    try xy.put(a, K.xy.TYPE, gen.str(DECIMAL64));
    if (t.fractionDigits()) |fd| try xy.put(a, K.xy.FRACTION_DIGITS, .{ .int = fd });
    if (t.rangeRestriction().expression) |r| if (r.len > 0) try xy.put(a, K.xy.RANGE, gen.str(r));
    try out.put(a, K.X_YANG, gen.objVal(xy));
    return out;
}

fn toEmpty(e: gen.Emit, _: *const Builtin, _: *const ast.TypeStmt) gen.Error!*Object {
    const out = try typeOnly(e.g.a, "object");
    try out.put(e.g.a, K.MAX_PROPERTIES, .{ .int = 0 });
    return out;
}

fn toUnion(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    if (t.members().len == 0) return typeOnly(a, "string");
    const members = try a.alloc(Val, t.members().len);
    for (t.members(), 0..) |m, i| members[i] = gen.objVal(try gen.typeToSchema(e.g, m, e.typedef_names, e.module, e.anchor));
    const out = try obj(a);
    try out.put(a, K.ONE_OF, .{ .array = members });
    return out;
}

fn toIdentityref(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const scope = t.scope orelse e.module;
    const bases = t.identityBases();
    if (bases.len == 0) return typeOnly(a, "string");
    const exported = try a.alloc([2][]const u8, bases.len);
    for (bases, 0..) |base, i| exported[i] = try gen.identityBaseForJson(e.g, base, scope, e.module);
    const xy = try obj(a);
    try xy.put(a, K.xy.TYPE, gen.str(K.types.IDENTITYREF));
    const names = try a.alloc(Val, exported.len);
    for (exported, 0..) |x, i| names[i] = gen.str(x[0]);
    try xy.put(a, K.xy.BASES, .{ .array = names });
    const out = try obj(a);
    if (exported.len == 1) {
        try out.put(a, K.REF, gen.str(exported[0][1]));
    } else {
        const refs = try a.alloc(Val, exported.len);
        for (exported, 0..) |x, i| {
            const r = try obj(a);
            try r.put(a, K.REF, gen.str(x[1]));
            refs[i] = gen.objVal(r);
        }
        try out.put(a, K.ALL_OF, .{ .array = refs });
    }
    try out.put(a, K.X_YANG, gen.objVal(xy));
    return out;
}

fn toLeafref(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const path = try gen.leafrefPathString(a, t);
    const target = gen.resolveLeafrefTargetLeaf(e.module, t, e.anchor);
    const target_type: ?*const ast.TypeStmt = if (target) |leaf| leaf.data.leaf.type else null;
    const inner = if (target_type) |tt| try gen.typeToSchema(e.g, tt, e.typedef_names, e.module, .none) else try typeOnly(a, "string");
    const out = try obj(a);
    for (inner.keys(), inner.values()) |k, v| {
        if (!std.mem.eql(u8, k, K.X_YANG)) try out.put(a, k, v);
    }
    const xy = try obj(a);
    try xy.put(a, K.xy.TYPE, gen.str(LEAFREF));
    try xy.put(a, K.xy.PATH, gen.str(path));
    try xy.put(a, K.xy.REQUIRE_INSTANCE, .{ .bool = t.requireInstance() });
    try gen.withXpathPrefixes(a, xy, t.pathAst());
    try out.put(a, K.X_YANG, gen.objVal(xy));
    return out;
}

fn toInstanceIdentifier(e: gen.Emit, _: *const Builtin, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const out = try typeOnly(a, "string");
    const xy = try obj(a);
    try xy.put(a, K.xy.TYPE, gen.str(K.types.INSTANCE_IDENTIFIER));
    try xy.put(a, K.xy.REQUIRE_INSTANCE, .{ .bool = t.requireInstance() });
    try out.put(a, K.X_YANG, gen.objVal(xy));
    return out;
}

/// `type_to_schema`: a typedef name becomes `$ref`; a built-in is encoded by its entry;
/// anything else is a typedef of another module, inlined.
pub fn typeToSchema(e: gen.Emit, t: *const ast.TypeStmt) gen.Error!*Object {
    if (try gen.scopedTypeSchema(e, t)) |schema| return schema;
    const prefixed = if (t.prefix) |p| p.len > 0 else false;
    const resolved = module_mod.resolveTypedef(t, e.module);
    const local = e.module.typedefs.get(t.name);
    if (!prefixed and e.typedef_names.contains(t.name) and resolved != null and local != null and resolved.?.typedef == local.?) {
        const o = try obj(e.g.a);
        try o.put(e.g.a, K.REF, gen.str(try @import("../typedef_scope.zig").defsUri(e.g.a, t.name)));
        return o;
    }
    const spec = get(t.name);
    if (spec == null or prefixed) return importedTypedefSchema(e, t);
    return spec.?.toSchema(e, t);
}

/// `_imported_typedef_schema`: the JSON form's `$defs` hold only this module's typedefs.
fn importedTypedefSchema(e: gen.Emit, t: *const ast.TypeStmt) gen.Error!*Object {
    const a = e.g.a;
    const label = if (t.prefix) |p| (if (p.len > 0) try std.fmt.allocPrint(a, "{s}:{s}", .{ p, t.name }) else t.name) else t.name;
    const resolved = module_mod.resolveTypedef(t, e.module);
    const td_type: ?*ast.TypeStmt = if (resolved) |r| r.typedef.data.typedef.type else null;
    if (resolved == null or td_type == null) return e.g.fail("cannot export type {f}: its typedef is not found where the type is written", .{pyfmt.repr(label)});
    const restricted = (if (t.rangeRestriction().expression) |r| r.len > 0 else false) or (if (t.lengthRestriction().expression) |l| l.len > 0 else false) or t.patterns().len > 0;
    if (restricted) return e.g.fail("cannot export restrictions on the imported typedef {f} in the native JSON form", .{pyfmt.repr(label)});
    const none: gen.Names = .empty;
    return typeToSchema(.{ .g = e.g, .typedef_names = &none, .module = resolved.?.module, .anchor = e.anchor }, td_type.?);
}

/// `_parse_range`: the integer bounds of a `range` (null where not an integer).
fn parseRange(range: []const u8) [2]?i128 {
    var parts = std.mem.splitSequence(u8, range, "..");
    const lo_s = gen.pyStrip(parts.first());
    const rest = parts.rest();
    const has_hi = std.mem.indexOf(u8, range, "..") != null;
    const hi_s = gen.pyStrip(rest);
    var out: [2]?i128 = .{ null, null };
    if (lo_s.len > 0 and !std.ascii.eqlIgnoreCase(lo_s, "min")) out[0] = xutils.pyInt(lo_s);
    if (has_hi and hi_s.len > 0 and !std.ascii.eqlIgnoreCase(hi_s, "max")) out[1] = xutils.pyInt(hi_s);
    return out;
}

/// `json_integer_bounds_for_builtin`: JSON Schema `minimum` / `maximum`.
fn jsonIntegerBounds(name: []const u8, range: ?[]const u8) [2]?i128 {
    const b = (get(name) orelse return .{ null, null }).bounds orelse return .{ null, null };
    const r = range orelse return .{ b[0], b[1] };
    if (r.len == 0) return .{ b[0], b[1] };
    var out = parseRange(r);
    var parts = std.mem.splitSequence(u8, r, "..");
    const lo_s = gen.pyStrip(parts.first());
    const hi_s = gen.pyStrip(parts.rest());
    if (std.ascii.eqlIgnoreCase(lo_s, "min")) out[0] = b[0];
    if (std.mem.indexOf(u8, r, "..") != null and std.ascii.eqlIgnoreCase(hi_s, "max")) out[1] = b[1];
    return out;
}

// ---------------------------------------------------------------------------
// Schema import (`from_schema`)

fn isStr(v: ?Val, s: []const u8) bool {
    const value = v orelse return false;
    return value == .string and std.mem.eql(u8, value.string, s);
}

fn newType(p: *jparse.Parse, name: []const u8) error{OutOfMemory}!*ast.TypeStmt {
    const t = try p.a.create(ast.TypeStmt);
    t.* = ast.TypeStmt.init(name, null);
    return t;
}

fn unused(_: *jparse.Parse, _: *const Builtin, _: Fragment) jparse.Error!?*ast.TypeStmt {
    return null;
}

/// `_coerce_int`.
fn coerceInt(v: ?Val) ?i128 {
    const value = v orelse return null;
    return switch (value) {
        .bool => |b| @intFromBool(b),
        .int => |i| i,
        .float => |f| if (std.math.isFinite(f) and @floor(f) == f and @abs(f) < 1e38) @as(i128, @intFromFloat(f)) else null,
        else => null,
    };
}

/// `_narrowest_integer_builtin`: unsigned preferred when the lower bound is not negative.
fn narrowestInteger(lo: ?i128, hi: ?i128) []const u8 {
    const signed = [_][]const u8{ INT8, INT16, INT32, INT64 };
    const unsigned = [_][]const u8{ UINT8, UINT16, UINT32, UINT64 };
    const order: []const []const u8 = if (lo != null and lo.? < 0) &signed else &(unsigned ++ signed);
    const eff_lo = lo orelse get(order[0]).?.bounds.?[0];
    const eff_hi = hi orelse get(order[order.len - 1]).?.bounds.?[1];
    for (order) |n| {
        const b = get(n).?.bounds.?;
        if (eff_lo >= b[0] and eff_hi <= b[1]) return n;
    }
    return INT64;
}

/// `yang_integer_from_json_bounds`: the built-in and `range` JSON Schema bounds encode.
fn integerFromBounds(a: Allocator, min: ?Val, max: ?Val) error{OutOfMemory}!struct { name: []const u8, range: ?[]const u8 } {
    const lo = coerceInt(min);
    const hi = coerceInt(max);
    if (lo == null and hi == null) return .{ .name = "integer", .range = null };
    if (lo != null and hi != null) {
        for (BUILTINS) |b| if (b.bounds) |bb| if (lo.? == bb[0] and hi.? == bb[1]) return .{ .name = b.name, .range = null };
    }
    if (lo != null and lo.? == 0 and hi != null) {
        for ([_][]const u8{ INT8, INT16, INT32, INT64 }) |n| if (hi.? == get(n).?.bounds.?[1]) return .{ .name = n, .range = "0..max" };
    }
    const lo_s = if (lo) |v| try std.fmt.allocPrint(a, "{d}", .{v}) else "min";
    const hi_s = if (hi) |v| try std.fmt.allocPrint(a, "{d}", .{v}) else "max";
    return .{ .name = narrowestInteger(lo, hi), .range = try std.fmt.allocPrint(a, "{s}..{s}", .{ lo_s, hi_s }) };
}

fn integerFromFragment(p: *jparse.Parse, f: Fragment) jparse.Error!*ast.TypeStmt {
    const r = try integerFromBounds(p.a, f.schema.get(K.MINIMUM), f.schema.get(K.MAXIMUM));
    const t = try newType(p, r.name);
    if (r.range) |range| (try t.ensureRange(p.a)).expression = range;
    return t;
}

fn fromNumberInteger(p: *jparse.Parse, b: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.schema.get(K.TYPE), "integer")) return null;
    const t = try integerFromFragment(p, f);
    return if (std.mem.eql(u8, t.name, b.name)) t else null;
}

fn fromQuotedInteger(p: *jparse.Parse, b: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.schema.get(K.TYPE), "string")) return null;
    if (!isStr(f.xyang.get(K.xy.TYPE), b.name)) return null;
    const t = try newType(p, b.name);
    if (f.xyang.get(K.xy.RANGE)) |r| if (r == .string and r.string.len > 0) {
        (try t.ensureRange(p.a)).expression = r.string;
    };
    return t;
}

fn fromDecimal(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    const kind = f.schema.get(K.TYPE);
    if (isStr(kind, "string") and isStr(f.xyang.get(K.xy.TYPE), DECIMAL64)) {
        const t = try newType(p, DECIMAL64);
        if (f.xyang.get(K.xy.RANGE)) |r| if (r == .string and r.string.len > 0) {
            (try t.ensureRange(p.a)).expression = r.string;
        };
        if (f.xyang.get(K.xy.FRACTION_DIGITS)) |fd| if (fd == .int) {
            (try t.ensure(.decimal, p.a)).fraction_digits = std.math.cast(i64, fd.int) orelse return p.fail("fraction-digits {d} is out of range", .{fd.int});
        };
        return t;
    }
    if (!isStr(kind, "number")) return null;
    const t = try newType(p, DECIMAL64);
    const legacy: ?i128 = if (f.schema.get(K.X_FRACTION_DIGITS)) |l| switch (l) {
        .int => |i| i,
        .bool => |b| @intFromBool(b),
        else => null,
    } else null;
    if (legacy != null and legacy.? > 0) {
        (try t.ensure(.decimal, p.a)).fraction_digits = std.math.cast(i64, legacy.?) orelse return p.fail("x-fraction-digits {d} is out of range", .{legacy.?});
    } else if (try jparse.fractionDigitsFromMultipleOf(p.a, f.schema.get(K.MULTIPLE_OF))) |fd| {
        (try t.ensure(.decimal, p.a)).fraction_digits = fd;
    }
    const min = f.schema.get(K.MINIMUM);
    const max = f.schema.get(K.MAXIMUM);
    if ((min != null and min.? != .null) or (max != null and max.? != .null)) {
        const lo = if (min == null or min.? == .null) "min" else try jparse.formatDecimal64Bound(p.a, min.?, t.fractionDigits());
        const hi = if (max == null or max.? == .null) "max" else try jparse.formatDecimal64Bound(p.a, max.?, t.fractionDigits());
        (try t.ensureRange(p.a)).expression = try std.fmt.allocPrint(p.a, "{s}..{s}", .{ lo, hi });
    }
    return t;
}

fn fromBoolean(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (isStr(f.schema.get(K.TYPE), "boolean")) return try newType(p, BOOLEAN);
    return null;
}

fn fromEmpty(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    const mp = f.schema.get(K.MAX_PROPERTIES) orelse return null;
    if (isStr(f.schema.get(K.TYPE), "object") and jv.pyEql(mp, .{ .int = 0 })) return try newType(p, EMPTY);
    return null;
}

fn enumStrings(p: *jparse.Parse, items: []const Val) jparse.Error!ast.StringList {
    var out: ast.StringList = .empty;
    for (items) |item| {
        if (item != .string) return p.fail("enum value {f} is not a string; the YANG enumeration names are strings", .{jv.pyRepr(item)});
        try out.append(p.a, item.string);
    }
    return out;
}

fn fromEnumeration(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    const raw = f.schema.get(K.ENUM) orelse return null;
    const items: []const Val = if (raw == .array) raw.array else &.{};
    if (items.len <= 1) return null;
    const t = try newType(p, ENUMERATION);
    (try t.ensureEnums(p.a)).* = try enumStrings(p, items);
    return t;
}

fn pyIntOf(v: Val) ?i128 {
    return switch (v) {
        .int => |i| i,
        .bool => |b| @intFromBool(b),
        .float => |x| if (std.math.isFinite(x) and @abs(x) < 1e38) @as(i128, @intFromFloat(@trunc(x))) else null,
        .string => |s| xutils.pyInt(s),
        else => null,
    };
}

fn fromBits(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.xyang.get(K.xy.TYPE), K.types.BITS)) return null;
    var bits: std.ArrayList(ast.BitStmt) = .empty;
    const raw = f.xyang.get(K.xy.BITS) orelse .null;
    switch (raw) {
        .object => |o| {
            for (o.keys(), o.values()) |name, pos| {
                if (name.len == 0) continue;
                const position = pyIntOf(pos) orelse continue;
                try bits.append(p.a, .{ .name = name, .position = std.math.cast(i64, position) orelse return p.fail("bit {f} position {d} is out of range", .{ pyfmt.repr(name), position }) });
            }
            std.mem.sort(ast.BitStmt, bits.items, {}, bitLess);
        },
        .array => |items| for (items, 0..) |item, index| {
            switch (item) {
                .object => |o| {
                    const name = o.get("name") orelse continue;
                    if (name != .string or name.string.len == 0) continue;
                    const pos = o.get("position") orelse Val{ .int = @intCast(index) };
                    const position = pyIntOf(pos) orelse @as(i128, @intCast(index));
                    try bits.append(p.a, .{ .name = name.string, .position = std.math.cast(i64, position) orelse return p.fail("bit {f} position {d} is out of range", .{ pyfmt.repr(name.string), position }) });
                },
                .string => |s| if (s.len > 0) try bits.append(p.a, .{ .name = s, .position = @intCast(index) }),
                else => {},
            }
        },
        else => {},
    }
    if (bits.items.len == 0) return null;
    const t = try newType(p, BITS);
    (try t.ensureBits(p.a)).* = bits;
    return t;
}

fn fromLeafref(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.xyang.get(K.xy.TYPE), LEAFREF)) return null;
    const t = try newType(p, LEAFREF);
    (try t.ensure(.leafref, p.a)).require_instance = if (f.xyang.get(K.xy.REQUIRE_INSTANCE)) |r| xutils.valBool(r) else true;
    if (f.xyang.get(K.xy.PATH)) |pv| if (pv == .string and gen.pyStrip(pv.string).len > 0) {
        const text = gen.pyStrip(pv.string);
        (try t.ensure(.leafref, p.a)).path = text;
        (try t.ensure(.leafref, p.a)).path_ast = try p.leafrefPath(text, f.xyang.get(K.xy.XPATH_PREFIXES));
    };
    return t;
}

fn fromIdentityref(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.xyang.get(K.xy.TYPE), K.types.IDENTITYREF)) return null;
    const t = try newType(p, IDENTITYREF);
    (try t.ensureIdentityBases(p.a)).* = try jparse.basesFromJson(p.a, f.xyang.get(K.xy.BASES));
    if (t.identityBases().len == 0) {
        if (f.xyang.get(K.xy.BASE)) |b| if (b == .string) if (jparse.coerceIdentifierRef(b)) |ref| try (try t.ensureIdentityBases(p.a)).append(p.a, ref);
    }
    return t;
}

fn fromInstanceIdentifier(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.xyang.get(K.xy.TYPE), K.types.INSTANCE_IDENTIFIER)) return null;
    const t = try newType(p, INSTANCE_IDENTIFIER);
    (try t.ensure(.instance_identifier, p.a)).require_instance = if (f.xyang.get(K.xy.REQUIRE_INSTANCE)) |r| xutils.valBool(r) else true;
    return t;
}

fn fromUnion(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    const raw = f.schema.get(K.ONE_OF) orelse return null;
    var members: std.ArrayList(*ast.TypeStmt) = .empty;
    if (raw == .array) for (raw.array) |branch| {
        if (branch != .object) continue;
        const bxy = try jparse.xyangOf(p, branch.object);
        if (try jparse.typeFromSchema(p, f.defs, branch.object, bxy)) |m| try members.append(p.a, m);
    };
    if (members.items.len == 0) return null;
    const t = try newType(p, UNION);
    (try t.ensureMembers(p.a)).* = members;
    return t;
}

fn fromString(p: *jparse.Parse, _: *const Builtin, f: Fragment) jparse.Error!?*ast.TypeStmt {
    if (!isStr(f.schema.get(K.TYPE), "string")) return null;
    if (f.xyang.get(K.xy.TYPE)) |n| if (n == .string and isStringNumber(n.string)) return null;
    const t = try newType(p, STRING);
    var raw_pat: ?[]const u8 = null;
    if (f.schema.get(K.PATTERN)) |pv| if (pv == .string) {
        var pat = pv.string;
        if (std.mem.startsWith(u8, pat, "^") and std.mem.endsWith(u8, pat, "$")) pat = if (pat.len >= 2) pat[1 .. pat.len - 1] else "";
        raw_pat = pat;
    };
    const min_len = f.schema.get(K.MIN_LENGTH);
    const max_len = f.schema.get(K.MAX_LENGTH);
    const has_min = min_len != null and min_len.? != .null;
    const has_max = max_len != null and max_len.? != .null;
    if (has_min and has_max) {
        (try t.ensureLength(p.a)).expression = try std.fmt.allocPrint(p.a, "{f}..{f}", .{ jv.pyStr(min_len.?), jv.pyStr(max_len.?) });
    } else if (has_max) {
        (try t.ensureLength(p.a)).expression = try std.fmt.allocPrint(p.a, "0..{f}", .{jv.pyStr(max_len.?)});
    } else if (has_min) {
        (try t.ensureLength(p.a)).expression = try std.fmt.allocPrint(p.a, "{f}..", .{jv.pyStr(min_len.?)});
    }
    const merged = try jparse.mergeSchemaXyang(p.a, f.schema, f.xyang);
    const meta = jparse.patternMetadata(merged);
    try jparse.applyStringPatternEntries(p, t, merged);
    if (t.patterns().len == 0) if (raw_pat) |pat| try (try t.ensurePatterns(p.a)).append(p.a, try p.patternSpec(pat, false, meta[0], meta[1]));
    return t;
}

/// `_singleton_enum_string`: a one-value `enum` is a string with that pattern.
fn singletonEnumString(p: *jparse.Parse, f: Fragment) jparse.Error!?*ast.TypeStmt {
    const raw = f.schema.get(K.ENUM) orelse return null;
    const items: []const Val = if (raw == .array) raw.array else &.{};
    if (items.len != 1 or !isStr(f.schema.get(K.TYPE), "string") or items[0] != .string) return null;
    const t = try newType(p, STRING);
    const pattern = if (std.mem.eql(u8, items[0].string, "*")) "\\*" else items[0].string;
    const merged = try jparse.mergeSchemaXyang(p.a, f.schema, f.xyang);
    const meta = jparse.patternMetadata(merged);
    try jparse.applyStringPatternEntries(p, t, merged);
    if (t.patterns().len == 0) try (try t.ensurePatterns(p.a)).append(p.a, try p.patternSpec(pattern, false, meta[0], meta[1]));
    return t;
}

/// `type_stmt_from_schema`: rebuild a `type` from a JSON Schema fragment.
pub fn typeStmtFromSchema(p: *jparse.Parse, defs: *const Object, schema: *const Object, xyang: *const Object) jparse.Error!?*ast.TypeStmt {
    const f: Fragment = .{ .schema = schema, .xyang = xyang, .defs = defs };
    for ([_][]const u8{ IDENTITYREF, INSTANCE_IDENTIFIER, BITS, LEAFREF }) |n| {
        if (try get(n).?.fromSchema(p, f)) |t| return t;
    }
    if (schema.get(K.REF)) |ref| if (ref == .string and ref.string.len > 0) {
        if (try jparse.refToTypedefName(p, ref.string)) |name| if (name.len > 0) return try newType(p, name);
    };
    if (try get(ENUMERATION).?.fromSchema(p, f)) |t| return t;
    if (try singletonEnumString(p, f)) |t| return t;
    const kind = schema.get(K.TYPE);
    if (isStr(kind, "string")) {
        for ([_][]const u8{ INT64, UINT64, DECIMAL64 }) |n| {
            if (try get(n).?.fromSchema(p, f)) |t| return t;
        }
        return get(STRING).?.fromSchema(p, f);
    }
    if (isStr(kind, "integer")) return try integerFromFragment(p, f);
    if (try get(DECIMAL64).?.fromSchema(p, f)) |t| return t;
    for ([_][]const u8{ BOOLEAN, EMPTY, UNION }) |n| {
        if (try get(n).?.fromSchema(p, f)) |t| return t;
    }
    return null;
}

/// `is_string_number`.
pub fn isStringNumber(name: []const u8) bool {
    const b = get(name) orelse return false;
    return b.json_encoding == .@"string-number";
}

/// AST family selection shares the built-in registry with validation and JSON conversion.
pub fn typeKind(name: []const u8, prefix: ?[]const u8) ast.TypeKind {
    if (prefix != null) return .derived;
    if (std.mem.eql(u8, name, "integer")) return .numeric;
    if (std.mem.eql(u8, name, "number")) return .decimal;
    const builtin = get(name) orelse return .derived;
    return switch (builtin.family) {
        .integer => .numeric,
        .boolean, .empty => .plain,
        .@"instance-identifier" => .instance_identifier,
        inline else => |family| @field(ast.TypeKind, @tagName(family)),
    };
}

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
    const t = ast.TypeStmt.init(INT32, null);
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
