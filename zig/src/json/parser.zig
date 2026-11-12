//! Rebuild a module from its native JSON form (mirrors `src/xyang/json/parser.py`,
//! `parse_json_schema`).
//!
//! The form carries no `import`: `x-yang.imports` stubs become the module's import
//! prefixes, so identity bases and extension invocations resolve without files. `must`,
//! `when` and leafref `path` are parsed and bound to the prefixes recorded in
//! `xpath-prefixes`, else to this module's. Built-in types are read back by the
//! `from_schema` column of `types/registry.zig`. Errors carry Python's `ValueError` text.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const Module = @import("../module.zig").Module;
const K = @import("schema_keys.zig");
const registry = @import("../types/registry.zig");
const xpath_parser = @import("../xpath/parser.zig");
const xast = @import("../xpath/ast.zig");
const xutils = @import("../xpath/utils.zig");
const xsd_regex = @import("../xsd_regex.zig");
const pyfmt = @import("../pyfmt.zig");
const capabilities = @import("../ext/capabilities.zig");
const errors = @import("../errors.zig");
const gen = @import("generator.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const Val = jv.Val;
const Object = jv.Object;
const repr = pyfmt.repr;

pub const Error = error{ OutOfMemory, JsonForm };

const empty_object: Object = .empty;

/// One `parse_json_schema` call: the module being rebuilt, its `$defs`, and the failure.
pub const Parse = struct {
    a: Allocator,
    module: *Module,
    defs: *const Object = &empty_object,
    /// `_PARSING` is set: invocations resolve against the module.
    in_body: bool = false,
    message: []const u8 = "",

    pub fn fail(p: *Parse, comptime fmt: []const u8, args: anytype) Error {
        p.message = try std.fmt.allocPrint(p.a, fmt, args);
        return error.JsonForm;
    }

    /// A YANG pattern, translated now so instance checks have the compiled regex.
    pub fn patternSpec(p: *Parse, pattern: []const u8, invert: bool, message: ?[]const u8, tag: ?[]const u8) Error!ast.PatternSpec {
        var compiled: ?*const xsd_regex.Regex = null;
        if (pattern.len > 0) {
            var failure: xsd_regex.Failure = .{};
            compiled = xsd_regex.translate(p.a, pattern, &failure) catch |err| switch (err) {
                error.OutOfMemory => return error.OutOfMemory,
                error.InvalidPattern => return p.fail("{s}", .{failure.message}),
            };
        }
        return .{ .pattern = pattern, .invert_match = invert, .error_message = message, .error_app_tag = tag, .compiled = compiled };
    }

    /// A leafref `path`, bound to the recorded prefixes or else this module's.
    pub fn leafrefPath(p: *Parse, text: []const u8, recorded: ?Val) Error!*xast.Expr {
        var xp = try xpath_parser.Parser.init(p.a, text);
        const e = xp.parsePath(true) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return p.fail("{s}", .{xp.message}),
        };
        try p.bind(e, text, recorded);
        return e;
    }

    /// A `must` / `when` expression (null when empty), bound like `leafrefPath`.
    fn expression(p: *Parse, text: []const u8, recorded: ?Val) Error!?*xast.Expr {
        if (text.len == 0) return null;
        var xp = try xpath_parser.Parser.init(p.a, text);
        const e = xp.parse() catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            else => return p.fail("{s}", .{xp.message}),
        };
        try p.bind(e, text, recorded);
        return e;
    }

    fn bind(p: *Parse, e: *xast.Expr, text: []const u8, recorded: ?Val) Error!void {
        var message: []const u8 = "";
        const resolver: xpath_parser.Resolver = if (recorded) |r| .{ .ctx = try recordedPrefixes(p, r), .resolve = resolveRecorded } else .{ .ctx = p.module, .resolve = resolveModule };
        xpath_parser.bindPrefixes(p.a, e, resolver, text, &message) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.UnknownPrefix => return p.fail("{s}", .{message}),
        };
    }
};

fn resolveModule(ctx: *anyopaque, prefix: []const u8) ?[]const u8 {
    const m: *Module = @ptrCast(@alignCast(ctx));
    return m.resolvePrefixToModuleName(prefix);
}

fn resolveRecorded(ctx: *anyopaque, prefix: []const u8) ?[]const u8 {
    const o: *Object = @ptrCast(@alignCast(ctx));
    const v = o.get(prefix) orelse return null;
    return v.string;
}

/// `recorded_prefixes`: an `xpath-prefixes` map; anything else is a load error.
fn recordedPrefixes(p: *Parse, raw: Val) Error!*Object {
    if (raw == .object) {
        const ok = for (raw.object.values()) |v| {
            if (v != .string) break false;
        } else true;
        if (ok) return raw.object;
    }
    return p.fail("\"{s}\" must map prefixes to module names, got {f}", .{ K.xy.XPATH_PREFIXES, jv.pyRepr(raw) });
}

// ---------------------------------------------------------------------------
// Values

/// Python truthiness of a JSON value.
fn truthy(v: ?Val) bool {
    const value = v orelse return false;
    return switch (value) {
        .null => false,
        .bool => |b| b,
        .int => |i| i != 0,
        .float => |f| f != 0,
        .decimal => |d| !std.mem.eql(u8, d.digits, "0"),
        .string => |s| s.len > 0,
        .array => |items| items.len > 0,
        .object => |o| o.count() > 0,
    };
}

fn getObj(o: *const Object, key: []const u8) ?*Object {
    const v = o.get(key) orelse return null;
    return if (v == .object) v.object else null;
}

/// `schema.get(key) or {}` for a value that must be an object when set.
fn objectOr(p: *Parse, o: *const Object, key: []const u8) Error!*const Object {
    const v = o.get(key) orelse return &empty_object;
    if (!truthy(v)) return &empty_object;
    if (v != .object) return p.fail("\"{s}\" must be an object, got {f}", .{ key, jv.pyRepr(v) });
    return v.object;
}

/// `_get_xyang`.
pub fn xyangOf(p: *Parse, schema: *const Object) Error!*const Object {
    return objectOr(p, schema, K.X_YANG);
}

/// A text field: the string, `default` when absent or null; any other value fails.
fn textField(p: *Parse, o: *const Object, key: []const u8, default: []const u8) Error![]const u8 {
    const v = o.get(key) orelse return default;
    return switch (v) {
        .string => |s| s,
        .null => default,
        else => p.fail("\"{s}\" must be a string, got {f}", .{ key, jv.pyRepr(v) }),
    };
}

/// `x.get(key) or ""` for a text field.
fn textOrEmpty(p: *Parse, o: *const Object, key: []const u8) Error![]const u8 {
    const v = o.get(key) orelse return "";
    if (!truthy(v)) return "";
    if (v != .string) return p.fail("\"{s}\" must be a string, got {f}", .{ key, jv.pyRepr(v) });
    return v.string;
}

fn newObject(a: Allocator) error{OutOfMemory}!*Object {
    return gen.newObject(a);
}

/// `_merge_schema_xyang`: the caller's `x-yang` with the schema's own (schema wins).
pub fn mergeSchemaXyang(a: Allocator, schema: *const Object, xyang: *const Object) error{OutOfMemory}!*Object {
    const out = try newObject(a);
    for (xyang.keys(), xyang.values()) |k, v| try out.put(a, k, v);
    if (getObj(schema, K.X_YANG)) |inner| for (inner.keys(), inner.values()) |k, v| try out.put(a, k, v);
    return out;
}

/// `_pattern_metadata_from_xyang`: top-level pattern error message and app tag.
pub fn patternMetadata(merged: *const Object) [2]?[]const u8 {
    const m = merged.get(K.xy.PATTERN_ERROR_MESSAGE);
    const t = merged.get(K.xy.PATTERN_ERROR_APP_TAG);
    return .{
        if (m != null and m.? == .string) m.?.string else null,
        if (t != null and t.? == .string) t.?.string else null,
    };
}

/// `_apply_string_pattern_entries`: the full pattern list from `string-patterns`.
pub fn applyStringPatternEntries(p: *Parse, t: *ast.TypeStmt, merged: *const Object) Error!void {
    const raw = merged.get(K.xy.STRING_PATTERNS) orelse return;
    if (raw != .array) return;
    var out: std.ArrayList(ast.PatternSpec) = .empty;
    for (raw.array) |item| {
        if (item != .object) continue;
        const pat = item.object.get(K.PATTERN) orelse continue;
        if (pat != .string) continue;
        const em = item.object.get(K.xy.PATTERN_ERROR_MESSAGE);
        const et = item.object.get(K.xy.PATTERN_ERROR_APP_TAG);
        try out.append(p.a, try p.patternSpec(
            pat.string,
            truthy(item.object.get(K.xy.INVERT_MATCH) orelse Val{ .bool = false }),
            if (em != null and em.? == .string) em.?.string else null,
            if (et != null and et.? == .string) et.?.string else null,
        ));
    }
    if (out.items.len > 0) t.patterns = out;
}

/// `_if_features_from_xyang`: a string or a list of strings.
fn ifFeatures(p: *Parse, xy: *const Object) Error!ast.StringList {
    var out: ast.StringList = .empty;
    const raw = xy.get(K.xy.IF_FEATURES) orelse return out;
    switch (raw) {
        .string => |s| if (gen.pyStrip(s).len > 0) try out.append(p.a, s),
        .array => |items| for (items) |x| {
            if (x == .string and gen.pyStrip(x.string).len > 0) try out.append(p.a, x.string);
        },
        else => {},
    }
    return out;
}

fn setNodeAnnotations(p: *Parse, s: *Statement, xy: *const Object) Error!void {
    if (xy.get(K.xy.AUGMENT_STRUCTURE)) |path| {
        if (path == .string) s.augment_structure = path.string;
    }
    const feats = try ifFeatures(p, xy);
    if (feats.items.len > 0) s.if_features = feats;
}

fn unitsOf(xy: *const Object) []const u8 {
    const u = xy.get(K.xy.UNITS) orelse return "";
    return if (u == .string) u.string else "";
}

/// `_set_config_from_xyang`.
fn setConfig(s: *Statement, xy: *const Object) void {
    if (xy.get(K.xy.CONFIG)) |c| if (c == .bool) {
        s.config = c.bool;
    };
}

/// `_when_from_xyang`: `{condition, description?}`.
fn whenOf(p: *Parse, xy: *const Object) Error!?*ast.WhenStmt {
    const raw = xy.get(K.xy.WHEN) orelse return null;
    if (raw != .object) return null;
    const cond = raw.object.get(K.when_entry.CONDITION) orelse return null;
    if (cond != .string or cond.string.len == 0) return null;
    const d = raw.object.get(K.DESCRIPTION);
    const desc: []const u8 = if (!truthy(d)) "" else if (d.? == .string) d.?.string else try std.fmt.allocPrint(p.a, "{f}", .{jv.pyStr(d.?)});
    const w = try p.a.create(ast.WhenStmt);
    w.* = .{ .expression = cond.string, .description = desc };
    w.evaluate_with_parent_context = truthy(raw.object.get(K.when_entry.EVALUATE_WITH_PARENT_CONTEXT));
    w.ast = try p.expression(cond.string, raw.object.get(K.xy.XPATH_PREFIXES));
    return w;
}

/// `coerce_identifier_ref`: a `prefix:name` string or a `{name, prefix?}` object.
pub fn coerceIdentifierRef(v: Val) ?ast.IdentifierRef {
    switch (v) {
        .string => |s| {
            if (s.len == 0) return null;
            const idx = std.mem.indexOfScalar(u8, s, ':') orelse return .{ .name = s };
            if (idx == 0 or idx >= s.len - 1) return .{ .name = s };
            return .{ .prefix = s[0..idx], .name = s[idx + 1 ..] };
        },
        .object => |o| {
            const name = o.get("name") orelse return null;
            if (name != .string or name.string.len == 0) return null;
            if (o.get("prefix")) |pre| if (pre == .string and pre.string.len > 0) return .{ .prefix = pre.string, .name = name.string };
            return .{ .name = name.string };
        },
        else => return null,
    }
}

/// `_bases_from_json`.
pub fn basesFromJson(a: Allocator, raw: ?Val) error{OutOfMemory}!std.ArrayList(ast.IdentifierRef) {
    var out: std.ArrayList(ast.IdentifierRef) = .empty;
    const value = raw orelse return out;
    if (value != .array) return out;
    for (value.array) |item| if (coerceIdentifierRef(item)) |ref| try out.append(a, ref);
    return out;
}

/// `_ref_to_typedef_name`: `#/$defs/name` to `name`.
pub fn refToTypedefName(ref: []const u8) ?[]const u8 {
    if (ref.len == 0 or !std.mem.startsWith(u8, ref, K.DEFS_URI_PREFIX)) return null;
    return ref[K.DEFS_URI_PREFIX.len..];
}

/// `_format_decimal64_bound`: a decimal64 range bound in YANG lexical form.
pub fn formatDecimal64Bound(a: Allocator, value: Val, fraction_digits: ?i64) error{OutOfMemory}![]const u8 {
    if (fraction_digits) |fd| if (fd > 0) {
        if (xutils.pyFloat(value)) |f| if (std.math.isFinite(f)) {
            var buf: [4096]u8 = undefined;
            const s = std.fmt.float.render(&buf, f, .{ .mode = .decimal, .precision = @intCast(@min(fd, 1000)) }) catch return std.fmt.allocPrint(a, "{f}", .{jv.pyStr(value)});
            return a.dupe(u8, s);
        };
    };
    return std.fmt.allocPrint(a, "{f}", .{jv.pyStr(value)});
}

/// `_fraction_digits_from_multiple_of`: n when the value is 10^-n for n in 1..18.
pub fn fractionDigitsFromMultipleOf(a: Allocator, raw: ?Val) error{OutOfMemory}!?i64 {
    const value = raw orelse return null;
    const t = switch (value) {
        .null, .bool, .array, .object => return null,
        else => try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(value)}),
    };
    const d = jv.Decimal.parse(a, t) catch return null;
    if (d.negative) return null;
    const digits = std.mem.trimEnd(u8, d.digits, "0");
    if (!std.mem.eql(u8, digits, "1")) return null;
    const exponent = d.exponent + @as(i32, @intCast(d.digits.len - digits.len));
    if (exponent < -18 or exponent > -1) return null;
    return -exponent;
}

/// `_resolve_schema`: `$ref` and `allOf` resolved to one schema (list items).
fn resolveSchema(p: *Parse, schema: *const Object, defs: *const Object) Error!*const Object {
    if (schema.count() == 0) return schema;
    if (schema.get(K.REF)) |ref| if (schema.count() <= 2 and ref == .string) {
        if (refToTypedefName(ref.string)) |name| if (name.len > 0) if (getObj(defs, name)) |d| return resolveSchema(p, d, defs);
    };
    if (schema.get(K.ALL_OF)) |all| {
        const merged = try newObject(p.a);
        var props = try newObject(p.a);
        try merged.put(p.a, K.PROPERTIES, gen.objVal(props));
        if (all == .array) for (all.array) |part| {
            if (part != .object) continue;
            const resolved = try resolveSchema(p, part.object, defs);
            const next = try gen.cloneObject(p.a, props);
            if (getObj(resolved, K.PROPERTIES)) |rp| for (rp.keys(), rp.values()) |k, v| try next.put(p.a, k, v);
            props = next;
            try merged.put(p.a, K.PROPERTIES, gen.objVal(props));
            for (resolved.keys(), resolved.values()) |k, v| {
                if (!std.mem.eql(u8, k, K.PROPERTIES)) try merged.put(p.a, k, v);
            }
        };
        return merged;
    }
    return schema;
}

/// `_type_from_schema`: the registry's type plus `units`.
pub fn typeFromSchema(p: *Parse, defs: *const Object, schema: *const Object, xyang: *const Object) Error!?*ast.TypeStmt {
    const t = try registry.typeStmtFromSchema(p, defs, schema, xyang) orelse return null;
    const units = unitsOf(try mergeSchemaXyang(p.a, schema, xyang));
    if (units.len > 0) t.units = units;
    return t;
}

fn stringType(p: *Parse) error{OutOfMemory}!*ast.TypeStmt {
    const t = try p.a.create(ast.TypeStmt);
    t.* = .{ .name = registry.STRING };
    return t;
}

fn xyTypeIs(xy: *const Object, value: []const u8) bool {
    const t = xy.get(K.xy.TYPE) orelse return false;
    return t == .string and std.mem.eql(u8, t.string, value);
}

fn isIdentityDef(p: *Parse, def: *const Object) Error!bool {
    return xyTypeIs(try xyangOf(p, def), K.types.IDENTITY);
}

fn newStatement(p: *Parse, name: []const u8, data: ast.Data) error{OutOfMemory}!*Statement {
    const s = try p.a.create(Statement);
    s.* = .{ .name = name, .data = data };
    return s;
}

/// `_build_typedef`: a `$defs` entry that is not an identity.
fn buildTypedef(p: *Parse, name: []const u8, def: *const Object) Error!*Statement {
    const xy = try xyangOf(p, def);
    const s = try newStatement(p, name, .{ .typedef = .{} });
    s.description = try textField(p, def, K.DESCRIPTION, "");
    s.data.typedef.type = try typeFromSchema(p, p.defs, def, xy) orelse try stringType(p);
    if (def.get(K.DEFAULT)) |d| if (d != .null) {
        s.data.typedef.default_value = d;
        s.data.typedef.default = try std.fmt.allocPrint(p.a, "{f}", .{jv.pyStr(d)});
    };
    const units = unitsOf(xy);
    if (units.len > 0) s.units = units;
    try attachInvocations(p, s, xy);
    return s;
}

/// `_build_identity`: a `$defs` entry with `x-yang.type` identity.
fn buildIdentity(p: *Parse, name: []const u8, def: *const Object) Error!*Statement {
    const xy = try xyangOf(p, def);
    const s = try newStatement(p, name, .{ .identity = .{ .bases = try basesFromJson(p.a, xy.get(K.xy.BASES)) } });
    s.description = try textField(p, def, K.DESCRIPTION, "");
    try setNodeAnnotations(p, s, xy);
    try attachInvocations(p, s, xy);
    return s;
}

/// `_build_must_list`.
fn mustList(p: *Parse, xy: *const Object) Error!std.ArrayList(*ast.MustStmt) {
    var out: std.ArrayList(*ast.MustStmt) = .empty;
    const raw = xy.get(K.xy.MUST) orelse return out;
    if (raw != .array) return out;
    for (raw.array) |m| {
        if (m != .object) continue;
        const must = try p.a.create(ast.MustStmt);
        must.* = .{
            .expression = try textField(p, m.object, K.must_entry.MUST, ""),
            .error_message = try textField(p, m.object, K.must_entry.ERROR_MESSAGE, ""),
            .description = try textField(p, m.object, K.DESCRIPTION, ""),
        };
        must.ast = try p.expression(must.expression, m.object.get(K.xy.XPATH_PREFIXES));
        try out.append(p.a, must);
    }
    return out;
}

const SchemaAndXyang = struct { schema: *const Object, xyang: *const Object };

/// `_property_schema_and_xyang`: a property (maybe `$ref` or `allOf`) as one schema and
/// its merged `x-yang`.
fn propertySchemaAndXyang(p: *Parse, prop: *const Object, defs: *const Object) Error!SchemaAndXyang {
    const a = p.a;
    if (prop.get(K.REF)) |ref| if (prop.contains(K.X_YANG)) {
        const ref_name = if (ref == .string) refToTypedefName(ref.string) else null;
        const base: *const Object = if (ref_name) |n| (if (defs.get(n)) |b| (if (b == .object) b.object else return p.fail("$defs entry {f} must be an object", .{repr(n)})) else &empty_object) else &empty_object;
        const schema = try newObject(a);
        for (base.keys(), base.values()) |k, v| try schema.put(a, k, v);
        for (prop.keys(), prop.values()) |k, v| {
            if (!std.mem.eql(u8, k, K.X_YANG)) try schema.put(a, k, v);
        }
        const merged = try newObject(a);
        const base_xy = try objectOr(p, base, K.X_YANG);
        const prop_xy = try objectOr(p, prop, K.X_YANG);
        for (base_xy.keys(), base_xy.values()) |k, v| try merged.put(a, k, v);
        for (prop_xy.keys(), prop_xy.values()) |k, v| try merged.put(a, k, v);
        return .{ .schema = schema, .xyang = merged };
    };
    if (prop.get(K.ALL_OF)) |all| {
        const merged = try newObject(a);
        const xy = try newObject(a);
        if (all == .array) for (all.array) |part| {
            if (part != .object) continue;
            if (part.object.get(K.REF)) |ref| {
                const name = if (ref == .string) refToTypedefName(ref.string) else null;
                if (name) |n| if (n.len > 0) if (defs.get(n)) |d| {
                    if (d != .object) return p.fail("$defs entry {f} must be an object", .{repr(n)});
                    for (d.object.keys(), d.object.values()) |k, v| try merged.put(a, k, v);
                };
            } else {
                for (part.object.keys(), part.object.values()) |k, v| try merged.put(a, k, v);
            }
            const pxy = try objectOr(p, part.object, K.X_YANG);
            for (pxy.keys(), pxy.values()) |k, v| try xy.put(a, k, v);
        };
        const top = try objectOr(p, prop, K.X_YANG);
        for (top.keys(), top.values()) |k, v| try xy.put(a, k, v);
        return .{ .schema = merged, .xyang = xy };
    }
    return .{ .schema = prop, .xyang = try xyangOf(p, prop) };
}

fn isEmptyBranch(v: Val) bool {
    if (v != .object) return false;
    const t = v.object.get(K.TYPE) orelse return false;
    const mp = v.object.get(K.MAX_PROPERTIES) orelse return false;
    return t == .string and std.mem.eql(u8, t.string, "object") and jv.pyEql(mp, .{ .int = 0 });
}

fn stringItems(a: Allocator, v: ?Val) error{OutOfMemory}![]const []const u8 {
    const value = v orelse return &.{};
    if (!truthy(value) or value != .array) return &.{};
    var out: std.ArrayList([]const u8) = .empty;
    for (value.array) |item| if (item == .string) try out.append(a, item.string);
    return out.items;
}

const NameSet = std.StringArrayHashMapUnmanaged(void);

fn toSet(a: Allocator, items: []const []const u8) error{OutOfMemory}!NameSet {
    var out: NameSet = .empty;
    for (items) |s| try out.put(a, s, {});
    return out;
}

fn intersect(a: Allocator, sets: []const NameSet) error{OutOfMemory}!NameSet {
    var out: NameSet = .empty;
    if (sets.len == 0) return out;
    for (sets[0].keys()) |k| {
        const all = for (sets[1..]) |s| {
            if (!s.contains(k)) break false;
        } else true;
        if (all) try out.put(a, k, {});
    }
    return out;
}

fn setEql(x: *const NameSet, y: *const NameSet) bool {
    if (x.count() != y.count()) return false;
    for (x.keys()) |k| if (!y.contains(k)) return false;
    return true;
}

fn lessString(_: void, x: []const u8, y: []const u8) bool {
    return std.mem.order(u8, x, y) == .lt;
}

fn sorted(a: Allocator, set: *const NameSet) error{OutOfMemory}![]const []const u8 {
    const out = try a.dupe([]const u8, set.keys());
    std.mem.sort([]const u8, out, {}, lessString);
    return out;
}

fn propertiesOf(p: *Parse, o: *const Object) Error!*const Object {
    return objectOr(p, o, K.PROPERTIES);
}

/// `validate_case_unique_child_names` (RFC 7950 7.9).
fn validateCaseUniqueChildNames(p: *Parse, choice: *const Statement) Error!void {
    var seen: std.StringArrayHashMapUnmanaged([]const u8) = .empty;
    for (choice.data.choice.cases.items) |case| {
        for (case.statements.items) |sub| {
            const seg = sub.schemaNode() orelse continue;
            if (seen.get(seg)) |prev| {
                return p.fail("Choice {f}: schema node {f} appears in case {f} and again in case {f} (RFC 7950: names of nodes in the cases of a choice must be unique).", .{ repr(choice.name), repr(seg), repr(prev), repr(case.name) });
            }
            try seen.put(p.a, seg, case.name);
        }
    }
}

/// `_parse_hoisted_choice_oneof`: the common leaves of every branch, then one choice.
fn parseHoistedChoiceOneOf(p: *Parse, one_of: []const Val, defs: *const Object, parent_path: []const u8, mandatory_in: ?bool, choice_name: []const u8, choice_description: []const u8, meta: *const Object) Error![]const *Statement {
    const a = p.a;
    var branches: std.ArrayList(*const Object) = .empty;
    for (one_of) |b| if (b == .object) try branches.append(a, b.object);
    var with_props: std.ArrayList(*const Object) = .empty;
    for (branches.items) |b| if (!isEmptyBranch(.{ .object = @constCast(b) })) try with_props.append(a, b);
    if (with_props.items.len == 0) try with_props.appendSlice(a, branches.items);

    var req_sets: std.ArrayList(NameSet) = .empty;
    for (branches.items) |b| try req_sets.append(a, try toSet(a, try stringItems(a, b.get(K.REQUIRED))));
    const common_req = try intersect(a, req_sets.items);
    const mandatory = mandatory_in orelse !for (req_sets.items) |*rs| {
        if (setEql(rs, &common_req)) break true;
    } else false;

    var case_branches: std.ArrayList(*const Object) = .empty;
    for (with_props.items) |b| {
        const req = try stringItems(a, b.get(K.REQUIRED));
        const extra = for (req) |r| {
            if (!common_req.contains(r)) break true;
        } else false;
        if (extra) try case_branches.append(a, b);
    }
    var key_sets: std.ArrayList(NameSet) = .empty;
    for (with_props.items) |b| try key_sets.append(a, try toSet(a, (try propertiesOf(p, b)).keys()));
    const common_keys = try intersect(a, key_sets.items);
    var case_reqs: std.ArrayList(NameSet) = .empty;
    for (case_branches.items) |b| try case_reqs.append(a, try toSet(a, try stringItems(a, b.get(K.REQUIRED))));
    const common_mandatory = try intersect(a, case_reqs.items);

    var out: std.ArrayList(*Statement) = .empty;
    if (common_keys.count() > 0 and with_props.items.len > 0) {
        const tb_props = try propertiesOf(p, with_props.items[0]);
        for (try sorted(a, &common_keys)) |k| {
            const pv = tb_props.get(k) orelse continue;
            if (pv == .null) continue;
            if (try convertProperty(p, k, try asObject(p, k, pv), defs, try std.fmt.allocPrint(a, "{s}/{s}", .{ parent_path, k }), common_mandatory.contains(k))) |s| try out.append(a, s);
        }
    }
    var cases: std.ArrayList(*Statement) = .empty;
    for (case_branches.items) |branch| {
        const bprops = try propertiesOf(p, branch);
        var breq = try toSet(a, try stringItems(a, branch.get(K.REQUIRED)));
        for (common_mandatory.keys()) |k| _ = breq.orderedRemove(k);
        const disc = try sorted(a, &breq);
        var case_statements: std.ArrayList(*Statement) = .empty;
        for (disc) |dk| {
            const pv = bprops.get(dk) orelse continue;
            if (pv == .null) continue;
            if (try convertProperty(p, dk, try asObject(p, dk, pv), defs, try std.fmt.allocPrint(a, "{s}/{s}", .{ parent_path, dk }), null)) |s| try case_statements.append(a, s);
        }
        if (case_statements.items.len == 0) continue;
        const bxy_raw = branch.get(K.X_YANG) orelse Val.null;
        const bxy: *const Object = if (bxy_raw == .object) bxy_raw.object else &empty_object;
        var case_name: []const u8 = "";
        if (bxy_raw == .object) {
            const n = bxy.get(K.NAME);
            if (truthy(n)) case_name = gen.pyStrip(try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(n.?)}));
        }
        if (case_name.len == 0) case_name = try std.fmt.allocPrint(a, "{s}-case", .{if (disc.len > 0) disc[0] else "case"});
        const d = branch.get(K.DESCRIPTION);
        const case = try newStatement(p, case_name, .{ .case = {} });
        case.description = if (d != null and d.? == .string) d.?.string else "";
        case.statements = case_statements;
        try setNodeAnnotations(p, case, bxy);
        try attachInvocations(p, case, bxy);
        try cases.append(a, case);
    }
    const choice = try newStatement(p, choice_name, .{ .choice = .{ .mandatory = mandatory, .cases = cases } });
    choice.description = choice_description;
    try setNodeAnnotations(p, choice, meta);
    try attachInvocations(p, choice, meta);
    try validateCaseUniqueChildNames(p, choice);
    try out.append(a, choice);
    return out.items;
}

fn asObject(p: *Parse, name: []const u8, v: Val) Error!*const Object {
    if (v != .object) return p.fail("property {f} must be an object, got {f}", .{ repr(name), jv.pyRepr(v) });
    return v.object;
}

/// The hoisted choice of a container or list: its `x-yang.choice` metadata.
fn hoistedChoice(p: *Parse, one_of: []const Val, defs: *const Object, path: []const u8, xy: *const Object) Error![]const *Statement {
    const meta_raw = xy.get(K.xy.CHOICE) orelse Val.null;
    const meta: *const Object = if (meta_raw == .object) meta_raw.object else &empty_object;
    const m = meta.get(K.xy.MANDATORY);
    const man: ?bool = if (m == null or m.? == .null) null else truthy(m);
    const name_v = meta.get(K.NAME);
    const desc_v = meta.get(K.DESCRIPTION);
    const name = if (truthy(name_v)) try std.fmt.allocPrint(p.a, "{f}", .{jv.pyStr(name_v.?)}) else "hoisted-choice";
    const desc = if (truthy(desc_v)) try std.fmt.allocPrint(p.a, "{f}", .{jv.pyStr(desc_v.?)}) else "";
    return parseHoistedChoiceOneOf(p, one_of, defs, path, man, name, desc, meta);
}

fn convertChildren(p: *Parse, props: *const Object, required: []const []const u8, defs: *const Object, base_path: []const u8, skip_non_objects: bool) Error!std.ArrayList(*Statement) {
    var out: std.ArrayList(*Statement) = .empty;
    const req = try toSet(p.a, required);
    for (props.keys(), props.values()) |name, v| {
        if (skip_non_objects and v != .object) continue;
        const child = try convertProperty(p, name, try asObject(p, name, v), defs, try std.fmt.allocPrint(p.a, "{s}/{s}", .{ base_path, name }), req.contains(name)) orelse continue;
        try out.append(p.a, child);
    }
    return out;
}

fn convertContainer(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, defs: *const Object, parent_path: []const u8, musts: std.ArrayList(*ast.MustStmt)) Error!*Statement {
    const props = try propertiesOf(p, schema);
    const one_of = schema.get(K.ONE_OF);
    var children: std.ArrayList(*Statement) = .empty;
    const hoisted = xyTypeIs(xy, "container") and one_of != null and one_of.? == .array and one_of.?.array.len > 0 and props.count() == 0;
    if (hoisted) {
        try children.appendSlice(p.a, try hoistedChoice(p, one_of.?.array, defs, parent_path, xy));
    } else {
        children = try convertChildren(p, props, try stringItems(p.a, schema.get(K.REQUIRED)), defs, parent_path, false);
    }
    const c = try newStatement(p, name, .{ .container = .{} });
    c.description = try textField(p, schema, K.DESCRIPTION, "");
    c.statements = children;
    c.must_statements = musts;
    c.when = try whenOf(p, xy);
    if (xy.get(K.xy.PRESENCE)) |pr| if (pr != .null) {
        c.data.container.presence = try std.fmt.allocPrint(p.a, "{f}", .{jv.pyStr(pr)});
    };
    try setNodeAnnotations(p, c, xy);
    setConfig(c, xy);
    try attachInvocations(p, c, xy);
    return c;
}

fn bound(p: *Parse, schema: *const Object, key: []const u8) Error!?i64 {
    const v = schema.get(key) orelse return null;
    if (v == .null) return null;
    const n = switch (v) {
        .int => |i| i,
        .bool => |b| @as(i128, @intFromBool(b)),
        .float => |f| if (std.math.isFinite(f) and @abs(f) < 1e18) @as(i128, @intFromFloat(@trunc(f))) else null,
        .string => |s| xutils.pyInt(s),
        else => null,
    } orelse return p.fail("{s} must be an integer, got {f}", .{ key, jv.pyRepr(v) });
    return std.math.cast(i64, n) orelse p.fail("{s} {d} is out of range", .{ key, n });
}

fn convertList(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, defs: *const Object, parent_path: []const u8, musts: std.ArrayList(*ast.MustStmt)) Error!*Statement {
    const a = p.a;
    const key = xy.get(K.xy.KEY);
    const items = try resolveSchema(p, try objectOr(p, schema, K.ITEMS), defs);
    const item_props = try propertiesOf(p, items);
    const items_one = items.get(K.ONE_OF);
    const item_base = try std.fmt.allocPrint(a, "{s}/{s}", .{ parent_path, name });
    var children: std.ArrayList(*Statement) = .empty;
    const t = items.get(K.TYPE);
    const hoisted = t != null and t.? == .string and std.mem.eql(u8, t.?.string, "object") and items_one != null and items_one.? == .array and items_one.?.array.len > 0 and item_props.count() == 0;
    if (hoisted) {
        try children.appendSlice(a, try hoistedChoice(p, items_one.?.array, defs, item_base, xy));
    } else {
        children = try convertChildren(p, item_props, try stringItems(a, items.get(K.REQUIRED)), defs, item_base, false);
    }
    const l = try newStatement(p, name, .{ .list = .{} });
    l.description = try textField(p, schema, K.DESCRIPTION, "");
    if (key) |k| if (k != .null) {
        if (k != .string) return p.fail("x-yang 'key' at {s} must be a string, got {f}", .{ item_base, jv.pyRepr(k) });
        l.data.list.key = k.string;
    };
    l.statements = children;
    l.must_statements = musts;
    l.data.list.unique = try uniqueOf(p, xy, item_base);
    l.when = try whenOf(p, xy);
    l.data.list.min_elements = try bound(p, schema, K.MIN_ITEMS);
    l.data.list.max_elements = try bound(p, schema, K.MAX_ITEMS);
    try setNodeAnnotations(p, l, xy);
    setConfig(l, xy);
    try attachInvocations(p, l, xy);
    return l;
}

/// `_unique_from_xyang`: a list of non-empty lists of non-empty paths.
fn uniqueOf(p: *Parse, xy: *const Object, where: []const u8) Error!std.ArrayList([]const []const u8) {
    var out: std.ArrayList([]const []const u8) = .empty;
    const raw = xy.get(K.xy.UNIQUE) orelse return out;
    if (raw == .null) return out;
    const ok = raw == .array and for (raw.array) |paths| {
        if (paths != .array or paths.array.len == 0) break false;
        const good = for (paths.array) |path| {
            if (path != .string or path.string.len == 0) break false;
        } else true;
        if (!good) break false;
    } else true;
    if (!ok) return p.fail("x-yang 'unique' at {s} must be a list of non-empty lists of paths, got {f}", .{ where, jv.pyRepr(raw) });
    for (raw.array) |paths| {
        const list = try p.a.alloc([]const u8, paths.array.len);
        for (paths.array, 0..) |path, i| list[i] = path.string;
        try out.append(p.a, list);
    }
    return out;
}

fn mandatoryOf(name: []const u8, schema: *const Object, xy: *const Object, override: ?bool) bool {
    if (override) |o| return o;
    if (xy.get(K.xy.MANDATORY)) |m| if (m == .bool and m.bool) return true;
    const req = schema.get(K.REQUIRED) orelse return false;
    if (req != .array) return false;
    for (req.array) |r| if (r == .string and std.mem.eql(u8, r.string, name)) return true;
    return false;
}

fn convertLeaf(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, prop: *const Object, defs: *const Object, override: ?bool, musts: std.ArrayList(*ast.MustStmt)) Error!*Statement {
    const a = p.a;
    var type_schema = schema;
    if (prop.get(K.REF)) |ref| if (ref == .string) if (refToTypedefName(ref.string)) |rn| if (rn.len > 0) if (getObj(defs, rn) != null) {
        type_schema = prop;
    };
    const t = try typeFromSchema(p, defs, type_schema, xy) orelse try stringType(p);
    var default: ?[]const u8 = null;
    if (schema.get(K.DEFAULT)) |d| if (d != .null) {
        const st = schema.get(K.TYPE);
        const st_name = if (st != null and st.? == .string) st.?.string else "";
        if (std.mem.eql(u8, st_name, "boolean")) {
            default = switch (d) {
                .bool => |b| if (b) "true" else "false",
                .string => |s| try std.ascii.allocLowerString(a, s),
                else => try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(d)}),
            };
        } else if (std.mem.eql(u8, st_name, "integer") and (d == .int or d == .float or d == .bool)) {
            const n: i128 = switch (d) {
                .int => |i| i,
                .bool => |b| @intFromBool(b),
                .float => |f| if (std.math.isFinite(f) and @abs(f) < 1e38) @intFromFloat(@trunc(f)) else return p.fail("default {f} is not an integer", .{jv.pyRepr(d)}),
                else => unreachable,
            };
            default = try std.fmt.allocPrint(a, "{d}", .{n});
        } else {
            default = if (d == .bool) (if (d.bool) "true" else "false") else try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(d)});
        }
    };
    const leaf = try newStatement(p, name, .{ .leaf = .{ .type = t, .mandatory = mandatoryOf(name, schema, xy, override), .default = default } });
    leaf.description = try textField(p, schema, K.DESCRIPTION, "");
    leaf.must_statements = musts;
    leaf.when = try whenOf(p, xy);
    try setNodeAnnotations(p, leaf, xy);
    const units = unitsOf(xy);
    if (units.len > 0) leaf.units = units;
    setConfig(leaf, xy);
    try attachInvocations(p, leaf, xy);
    return leaf;
}

fn convertAny(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, override: ?bool, musts: std.ArrayList(*ast.MustStmt), anyxml: bool) Error!*Statement {
    const mandatory = mandatoryOf(name, schema, xy, override);
    const node = try newStatement(p, name, if (anyxml) .{ .anyxml = .{ .mandatory = mandatory } } else .{ .anydata = .{ .mandatory = mandatory } });
    node.description = try textField(p, schema, K.DESCRIPTION, "");
    node.must_statements = musts;
    node.when = try whenOf(p, xy);
    try setNodeAnnotations(p, node, xy);
    try attachInvocations(p, node, xy);
    return node;
}

fn convertLeafList(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, defs: *const Object, musts: std.ArrayList(*ast.MustStmt)) Error!*Statement {
    const a = p.a;
    const items_v = schema.get(K.ITEMS);
    const items: *const Object = if (truthy(items_v)) (if (items_v.? == .object) items_v.?.object else return p.fail("leaf-list {f} \"items\" must be an object", .{repr(name)})) else schema;
    const items_xy = try objectOr(p, items, K.X_YANG);
    const t = try typeFromSchema(p, defs, items, if (items_xy.count() > 0) items_xy else xy) orelse try stringType(p);
    const ll = try newStatement(p, name, .{ .leaf_list = .{ .type = t } });
    ll.description = try textField(p, schema, K.DESCRIPTION, "");
    ll.must_statements = musts;
    ll.when = try whenOf(p, xy);
    ll.data.leaf_list.min_elements = try bound(p, schema, K.MIN_ITEMS);
    ll.data.leaf_list.max_elements = try bound(p, schema, K.MAX_ITEMS);
    if (schema.get(K.DEFAULT)) |d| if (d != .null) {
        const vals: []const Val = if (d == .array) d.array else try a.dupe(Val, &.{d});
        ll.data.leaf_list.default_values = vals;
        for (vals) |v| try ll.data.leaf_list.defaults.append(a, try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(v)}));
    };
    try setNodeAnnotations(p, ll, xy);
    const units = unitsOf(xy);
    if (units.len > 0) ll.units = units;
    setConfig(ll, xy);
    try attachInvocations(p, ll, xy);
    return ll;
}

fn convertChoice(p: *Parse, name: []const u8, schema: *const Object, xy: *const Object, defs: *const Object, parent_path: []const u8) Error!*Statement {
    const a = p.a;
    var cases: std.ArrayList(*Statement) = .empty;
    const one_of = schema.get(K.ONE_OF);
    if (truthy(one_of) and one_of.? == .array) for (one_of.?.array) |cv| {
        if (cv != .object or isEmptyBranch(cv)) continue;
        const cs = cv.object;
        const cxy = try xyangOf(p, cs);
        var case_name: []const u8 = if (truthy(cxy.get(K.NAME))) try std.fmt.allocPrint(a, "{f}", .{jv.pyStr(cxy.get(K.NAME).?)}) else "";
        if (case_name.len == 0 and truthy(cs.get(K.REQUIRED))) {
            const req = cs.get(K.REQUIRED).?;
            case_name = if (req == .array and req.array.len == 1 and req.array[0] == .string) try std.fmt.allocPrint(a, "{s}-case", .{req.array[0].string}) else "";
        }
        const case_props = try propertiesOf(p, cs);
        if (case_name.len == 0 and case_props.count() == 1) case_name = try std.fmt.allocPrint(a, "{s}-case", .{case_props.keys()[0]});
        var case_statements: std.ArrayList(*Statement) = .empty;
        for (case_props.keys(), case_props.values()) |pn, pv| {
            const path = try std.fmt.allocPrint(a, "{s}/{s}/{s}/{s}", .{ parent_path, name, case_name, pn });
            if (try convertProperty(p, pn, try asObject(p, pn, pv), defs, path, null)) |s| try case_statements.append(a, s);
        }
        const d = cs.get(K.DESCRIPTION);
        const case = try newStatement(p, case_name, .{ .case = {} });
        case.description = if (d != null and d.? == .string) d.?.string else "";
        case.statements = case_statements;
        try setNodeAnnotations(p, case, cxy);
        try attachInvocations(p, case, cxy);
        try cases.append(a, case);
    };
    const choice = try newStatement(p, name, .{ .choice = .{ .mandatory = truthy(xy.get(K.xy.MANDATORY)), .cases = cases } });
    choice.description = try textField(p, schema, K.DESCRIPTION, "");
    try setNodeAnnotations(p, choice, xy);
    setConfig(choice, xy);
    try attachInvocations(p, choice, xy);
    try validateCaseUniqueChildNames(p, choice);
    return choice;
}

/// `_convert_io_block`: rpc / action `input` or `output`.
fn convertIoBlock(p: *Parse, schema: *const Object, defs: *const Object, parent_path: []const u8, io_type: []const u8) Error!?*Statement {
    const xy = try xyangOf(p, schema);
    if (!xyTypeIs(xy, io_type)) return null;
    const musts = try mustList(p, xy);
    const children = try convertChildren(p, try propertiesOf(p, schema), try stringItems(p.a, schema.get(K.REQUIRED)), defs, parent_path, true);
    const is_input = std.mem.eql(u8, io_type, K.types.INPUT);
    const s = try newStatement(p, io_type, if (is_input) .{ .input = .{} } else .{ .output = .{} });
    s.description = try textField(p, schema, K.DESCRIPTION, "");
    s.statements = children;
    s.must_statements = musts;
    s.when = try whenOf(p, xy);
    try setNodeAnnotations(p, s, xy);
    try attachInvocations(p, s, xy);
    return s;
}

/// `_convert_rpc`: one `x-yang.rpcs` or `x-yang.actions` entry.
fn convertRpc(p: *Parse, name: []const u8, value: *const Object, defs: *const Object, kind: []const u8) Error!*Statement {
    const a = p.a;
    const xy = try xyangOf(p, value);
    if (!xyTypeIs(xy, kind)) {
        return p.fail("{s} {f} must have x-yang type {f}, got {f}", .{ kind, repr(name), repr(kind), jv.pyRepr(xy.get(K.xy.TYPE) orelse .null) });
    }
    const musts = try mustList(p, xy);
    var statements: std.ArrayList(*Statement) = .empty;
    for ([_][]const u8{ K.types.INPUT, K.types.OUTPUT }) |io| {
        const raw = value.get(io) orelse continue;
        if (raw != .object) continue;
        if (try convertIoBlock(p, raw.object, defs, try std.fmt.allocPrint(a, "/{s}/{s}", .{ name, io }), io)) |s| try statements.append(a, s);
    }
    const is_action = std.mem.eql(u8, kind, K.types.ACTION);
    const rpc = try newStatement(p, name, if (is_action) .{ .action = {} } else .{ .rpc = {} });
    rpc.statements = statements;
    rpc.must_statements = musts;
    rpc.when = try whenOf(p, xy);
    try setNodeAnnotations(p, rpc, xy);
    try attachInvocations(p, rpc, xy);
    return rpc;
}

/// `_convert_property`: a `module:name` key is a node another module defines.
fn convertProperty(p: *Parse, name: []const u8, prop: *const Object, defs: *const Object, parent_path: []const u8, override: ?bool) Error!?*Statement {
    const colon = std.mem.indexOfScalar(u8, name, ':') orelse {
        const s = try convertPropertyLocal(p, name, prop, defs, parent_path, override);
        return attachActions(p, s, prop, defs, parent_path);
    };
    const module_name = name[0..colon];
    const local = name[colon + 1 ..];
    if (module_name.len == 0 or local.len == 0) return p.fail("property name {f} must be 'name' or 'module:name'", .{repr(name)});
    const s = try convertPropertyLocal(p, local, prop, defs, parent_path, override);
    if (s) |stmt| stmt.defining_module = module_name;
    return attachActions(p, s, prop, defs, parent_path);
}

/// `_attach_actions`: a container's or list's `x-yang.actions` as action children.
fn attachActions(p: *Parse, s: ?*Statement, prop: *const Object, defs: *const Object, parent_path: []const u8) Error!?*Statement {
    const stmt = s orelse return null;
    switch (stmt.kind()) {
        .container, .notification, .input, .output, .list => {},
        else => return stmt,
    }
    const sx = try propertySchemaAndXyang(p, prop, defs);
    const actions = sx.xyang.get(K.xy.ACTIONS) orelse return stmt;
    if (actions == .null) return stmt;
    if (actions != .object) return p.fail("x-yang \"actions\" at {s} must be an object keyed by action name", .{parent_path});
    for (actions.object.keys(), actions.object.values()) |action_name, v| {
        if (v != .object) return p.fail("action {f} at {s} must be an object", .{ repr(action_name), parent_path });
        const colon = std.mem.lastIndexOfScalar(u8, action_name, ':');
        const local = if (colon) |c| action_name[c + 1 ..] else action_name;
        const action = try convertRpc(p, local, v.object, defs, K.types.ACTION);
        if (colon) |c| action.defining_module = action_name[0..c];
        try stmt.statements.append(p.a, action);
    }
    return stmt;
}

/// `_convert_property_local`: one property, or null when its `x-yang.type` is not a
/// schema node.
fn convertPropertyLocal(p: *Parse, name: []const u8, prop: *const Object, defs: *const Object, parent_path: []const u8, override: ?bool) Error!?*Statement {
    const sx = try propertySchemaAndXyang(p, prop, defs);
    const schema = sx.schema;
    const xy = sx.xyang;
    const tv = xy.get(K.xy.TYPE);
    var node_type: []const u8 = if (tv != null and tv.? == .string) tv.?.string else "";
    if (std.mem.eql(u8, node_type, K.types.LEAFREF) or std.mem.eql(u8, node_type, K.types.IDENTITYREF) or std.mem.eql(u8, node_type, K.types.INSTANCE_IDENTIFIER)) node_type = "leaf";
    const st = schema.get(K.TYPE);
    if (registry.isStringNumber(node_type) and st != null and st.? == .string and std.mem.eql(u8, st.?.string, "string")) node_type = "leaf";
    const with_must = for ([_][]const u8{ "leaf", "leaf-list", "container", "list", K.types.ANYDATA, K.types.ANYXML }) |n| {
        if (std.mem.eql(u8, n, node_type)) break true;
    } else false;
    const musts: std.ArrayList(*ast.MustStmt) = if (with_must) try mustList(p, xy) else .empty;
    if (std.mem.eql(u8, node_type, "container")) return try convertContainer(p, name, schema, xy, defs, parent_path, musts);
    if (std.mem.eql(u8, node_type, "list")) return try convertList(p, name, schema, xy, defs, parent_path, musts);
    if (std.mem.eql(u8, node_type, "leaf")) return try convertLeaf(p, name, schema, xy, prop, defs, override, musts);
    if (std.mem.eql(u8, node_type, "leaf-list")) return try convertLeafList(p, name, schema, xy, defs, musts);
    if (std.mem.eql(u8, node_type, "choice")) return try convertChoice(p, name, schema, xy, defs, parent_path);
    if (std.mem.eql(u8, node_type, K.types.ANYDATA)) return try convertAny(p, name, schema, xy, override, musts, false);
    if (std.mem.eql(u8, node_type, K.types.ANYXML)) return try convertAny(p, name, schema, xy, override, musts, true);
    return null;
}

// ---------------------------------------------------------------------------
// Extensions and imports

fn extensionFromJson(p: *Parse, owner: *const Module, name: []const u8, raw: Val) Error!*Statement {
    const body: *const Object = switch (raw) {
        .null => &empty_object,
        .object => |o| o,
        else => return p.fail("extension {f} must be an object, got {f}", .{ repr(name), jv.pyRepr(raw) }),
    };
    const ext = try newStatement(p, name, .{ .extension = .{ .module_name = owner.name } });
    if (body.get(K.xy.ARGUMENT)) |arg| if (arg == .string and arg.string.len > 0) {
        ext.data.extension.argument_name = arg.string;
    };
    if (body.get(K.xy.YIN_ELEMENT)) |yin| {
        if (yin != .bool) return p.fail("extension {f} \"{s}\" must be a boolean", .{ repr(name), K.xy.YIN_ELEMENT });
        ext.data.extension.argument_yin_element = yin.bool;
    }
    if (body.get(K.DESCRIPTION)) |d| if (d == .string) {
        ext.description = d.string;
    };
    if (body.get(K.xy.REFERENCE)) |r| if (r == .string) {
        ext.reference = r.string;
    };
    return ext;
}

/// `_load_extension_defs`: `x-yang.extension` as the module's extension definitions.
fn loadExtensionDefs(p: *Parse, module: *Module, raw_xy: *const Object) Error!void {
    const raw = raw_xy.get(K.xy.EXTENSION) orelse return;
    if (raw == .null) return;
    if (raw != .object) return p.fail("\"{s}\" must map names to extension definitions, got {f}", .{ K.xy.EXTENSION, jv.pyRepr(raw) });
    for (raw.object.keys(), raw.object.values()) |name, body| {
        try module.extensions.put(p.a, name, try extensionFromJson(p, module, name, body));
    }
}

/// `_invocation_from_json`: rebuild one entry before the module applies callbacks.
fn invocationFromJson(p: *Parse, raw: Val) Error!*Statement {
    const a = p.a;
    const bad = raw != .object or blk: {
        const n = raw.object.get(K.NAME) orelse break :blk true;
        break :blk n != .string or std.mem.indexOfScalar(u8, n.string, ':') == null;
    };
    if (bad) return p.fail("extension invocation must be an object with \"name\" of the form \"prefix:ext\", got {f}", .{jv.pyRepr(raw)});
    if (!p.in_body) return p.fail("extension invocations require parse_json_schema", .{});
    const o = raw.object;
    const name = o.get(K.NAME).?.string;
    const colon = std.mem.indexOfScalar(u8, name, ':').?;
    const prefix = name[0..colon];
    const ext_name = name[colon + 1 ..];
    const owner: *Module = if (std.mem.eql(u8, prefix, p.module.ownPrefix())) p.module else p.module.import_prefixes.get(prefix) orelse
        return p.fail("extension invocation {f}: unknown prefix {f}", .{ repr(name), repr(prefix) });
    const ext = owner.extensions.get(ext_name) orelse
        return p.fail("extension invocation {f}: unknown extension {f} in module {f}", .{ repr(name), repr(ext_name), repr(owner.name) });
    var argument: ?[]const u8 = null;
    if (o.get(K.xy.ARGUMENT)) |arg| if (arg != .null) {
        if (arg != .string) return p.fail("extension invocation {f}: argument must be a string", .{repr(name)});
        argument = arg.string;
    };
    const inv = try newStatement(p, name, .{ .extension_invocation = .{ .prefix = prefix, .argument = argument, .resolved_module = owner.name, .resolved_extension = ext } });
    inv.description = try textOrEmpty(p, o, K.DESCRIPTION);
    inv.reference = try textOrEmpty(p, o, K.xy.REFERENCE);
    try setNodeAnnotations(p, inv, o);
    inv.when = try whenOf(p, o);
    inv.must_statements = try mustList(p, o);
    setConfig(inv, o);
    const body_v = o.get(K.xy.BODY) orelse Val.null;
    if (!truthy(body_v)) return inv;
    if (body_v != .array) return p.fail("extension invocation {f}: \"{s}\" must be a list", .{ repr(name), K.xy.BODY });
    for (body_v.array) |item| {
        if (item != .object) return p.fail("extension invocation {f}: body entry must be an object", .{repr(name)});
        if (item.object.get(K.xy.EXTENSION)) |nested| {
            try inv.statements.append(a, try invocationFromJson(p, nested));
            continue;
        }
        const node = item.object.get("node");
        const schema = item.object.get("schema");
        if (node != null and node.? == .string and schema != null and schema.? == .object) {
            const child = try convertProperty(p, node.?.string, schema.?.object, p.defs, try std.fmt.allocPrint(a, "/{s}", .{node.?.string}), null) orelse
                return p.fail("extension invocation {f}: body node {f} is not a schema node", .{ repr(name), repr(node.?.string) });
            try inv.statements.append(a, child);
            continue;
        }
        return p.fail("extension invocation {f}: body entry must be an extension or a node", .{repr(name)});
    }
    return inv;
}

/// `_attach_invocations`: `x-yang.extensions` onto `s`, in export order.
fn attachInvocations(p: *Parse, s: *Statement, xy: *const Object) Error!void {
    try appendInvocations(p, &s.statements, xy);
}

fn appendInvocations(p: *Parse, list: *std.ArrayList(*Statement), xy: *const Object) Error!void {
    const raw = xy.get(K.xy.EXTENSIONS) orelse return;
    if (!truthy(raw)) return;
    if (raw != .array) return p.fail("\"{s}\" must be a list of invocations, got {f}", .{ K.xy.EXTENSIONS, jv.pyRepr(raw) });
    for (raw.array) |item| try list.append(p.a, try invocationFromJson(p, item));
}

/// `_module_from_import_stub`: one `x-yang.imports` entry, reduced to its identities and
/// extensions.
fn moduleFromImportStub(p: *Parse, key: []const u8, raw: Val) Error!*Module {
    const ok = raw == .object and for ([_][]const u8{ K.xy.MODULE, K.xy.PREFIX }) |k| {
        const v = raw.object.get(k) orelse break false;
        if (v != .string) break false;
    } else true;
    if (!ok) return p.fail("\"{s}\" entry {f} must be an object with \"module\" and \"prefix\"", .{ K.xy.IMPORTS, repr(key) });
    const o = raw.object;
    const stub = try p.a.create(Module);
    stub.* = .{
        .name = o.get(K.xy.MODULE).?.string,
        .namespace = try textField(p, o, K.xy.NAMESPACE, ""),
        .prefix = o.get(K.xy.PREFIX).?.string,
    };
    try loadImports(p, stub, o);
    const identities = o.get(K.xy.IDENTITIES) orelse Val.null;
    if (truthy(identities)) {
        if (identities != .object) return p.fail("\"{s}\" of import {f} must be an object", .{ K.xy.IDENTITIES, repr(key) });
        for (identities.object.keys(), identities.object.values()) |name, def| {
            const is_identity = def == .object and try isIdentityDef(p, def.object);
            if (!is_identity) return p.fail("identity {f} of import {f} is not an identity definition", .{ repr(name), repr(key) });
            try stub.identities.put(p.a, name, try buildIdentity(p, name, def.object));
        }
    }
    try loadExtensionDefs(p, stub, o);
    try loadFeatures(p, stub, o);
    var nested: Parse = .{ .a = p.a, .module = stub, .in_body = true };
    appendInvocations(&nested, &stub.statements, o) catch |err| {
        p.message = nested.message;
        return err;
    };
    try applyInvocations(p, stub);
    return stub;
}

fn applyInvocations(p: *Parse, module: *Module) Error!void {
    var diag: errors.Diagnostic = .{};
    var reporter: errors.Reporter = .{ .arena = p.a, .diag = &diag };
    capabilities.applyExtensionInvocations(&reporter, module) catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        error.YangLoad => return p.fail("{s}", .{diag.message}),
    };
}

fn loadFeatures(p: *Parse, module: *Module, xy: *const Object) Error!void {
    const raw = xy.get(K.xy.FEATURES) orelse return;
    if (raw == .null) return;
    if (raw != .object) return p.fail("\"{s}\" must map feature names to objects, got {f}", .{ K.xy.FEATURES, jv.pyRepr(raw) });
    for (raw.object.keys(), raw.object.values()) |name, body| {
        if (body != .object) return p.fail("feature {f} must be an object, got {f}", .{ repr(name), jv.pyRepr(body) });
        try module.features.put(p.a, name, {});
        if (body.object.get(K.xy.IF_FEATURES)) |guards| if (truthy(guards)) {
            if (guards != .array) return p.fail("feature {f} \"{s}\" must be a list of strings", .{ repr(name), K.xy.IF_FEATURES });
            var names: ast.StringList = .empty;
            for (guards.array) |guard| {
                if (guard != .string) return p.fail("feature {f} \"{s}\" must be a list of strings", .{ repr(name), K.xy.IF_FEATURES });
                try names.append(p.a, guard.string);
            }
            try module.feature_if_features.put(p.a, name, names);
        };
    }
}

/// `_load_imports`: `x-yang.imports` as import prefixes.
fn loadImports(p: *Parse, module: *Module, raw_xy: *const Object) Error!void {
    const imports = raw_xy.get(K.xy.IMPORTS) orelse return;
    if (imports == .null) return;
    if (imports != .object) return p.fail("\"{s}\" must map keys to imported modules, got {f}", .{ K.xy.IMPORTS, jv.pyRepr(imports) });
    for (imports.object.keys(), imports.object.values()) |key, raw| {
        try module.import_prefixes.put(p.a, key, try moduleFromImportStub(p, key, raw));
    }
}

/// `parse_json_schema` on parsed JSON. On `error.JsonForm`, `message` is set.
pub fn parseJsonSchema(a: Allocator, data: Val, message: *[]const u8) Error!*Module {
    const module = try a.create(Module);
    module.* = .{};
    var p: Parse = .{ .a = a, .module = module };
    parseInto(&p, data) catch |err| {
        message.* = p.message;
        return err;
    };
    return module;
}

fn parseInto(p: *Parse, data: Val) Error!void {
    const a = p.a;
    if (data != .object) return p.fail("JSON Schema must be an object, got {f}", .{jv.pyRepr(data)});
    const root = data.object;
    const root_xy_v = root.get(K.X_YANG) orelse Val.null;
    if (root_xy_v != .object) {
        return p.fail("JSON Schema has no root \"x-yang\" annotation; xYang needs a .yang.json produced by \"xyang convert\" (see design/json-schema-xyang-profile.md)", .{});
    }
    const root_xy = root_xy_v.object;
    const defs = try objectOr(p, root, K.DEFS);
    p.defs = defs;
    const m = p.module;
    m.name = try textField(p, root_xy, K.xy.MODULE, "unknown");
    m.yang_version = try textField(p, root_xy, K.xy.YANG_VERSION, "1.1");
    m.namespace = try textField(p, root_xy, K.xy.NAMESPACE, "");
    m.prefix = try textField(p, root_xy, K.xy.PREFIX, "");
    m.organization = try textField(p, root_xy, K.xy.ORGANIZATION, "");
    m.contact = try textField(p, root_xy, K.xy.CONTACT, "");
    m.description = try textField(p, root, K.DESCRIPTION, "");
    try loadImports(p, m, root_xy);
    try loadExtensionDefs(p, m, root_xy);
    try loadFeatures(p, m, root_xy);
    p.in_body = true;
    for (defs.keys(), defs.values()) |name, def| {
        if (def != .object) continue;
        if (try isIdentityDef(p, def.object)) {
            try m.identities.put(a, name, try buildIdentity(p, name, def.object));
        } else {
            try m.typedefs.put(a, name, try buildTypedef(p, name, def.object));
        }
    }
    const props = try objectOr(p, root, K.PROPERTIES);
    for (props.keys(), props.values()) |name, v| {
        if (v != .object) continue;
        if (getObj(v.object, K.X_YANG) == null) return p.fail("JSON Schema property \"{s}\" has no \"x-yang\" annotation", .{name});
        if (try convertProperty(p, name, v.object, defs, try std.fmt.allocPrint(a, "/{s}", .{name}), null)) |s| try m.statements.append(a, s);
    }
    const rpcs = try objectOr(p, root_xy, K.xy.RPCS);
    for (rpcs.keys(), rpcs.values()) |name, v| {
        if (v != .object) continue;
        try m.statements.append(a, try convertRpc(p, name, v.object, defs, K.types.RPC));
    }
    try appendInvocations(p, &m.statements, root_xy);
    try applyInvocations(p, m);
}

fn reloadForTest(a: Allocator, text_in: []const u8, message: *[]const u8) !*Module {
    return parseJsonSchema(a, try jv.parse(a, text_in, message), message);
}

test "the form reloads and regenerates" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, null, &diag, &.{});
    loader.expand_uses = false;
    const m = try loader.parseString(
        \\module t { yang-version 1.1; namespace "urn:t"; prefix t;
        \\  typedef pct { type uint8 { range "0..100"; } }
        \\  identity base; identity one { base base; }
        \\  container top {
        \\    leaf a { type pct; must ". > 1" { error-message "small"; } }
        \\    leaf b { type string { pattern "[a-z]+"; length "1..4"; } }
        \\    leaf-list c { type identityref { base base; } }
        \\    list l { key id; unique "v"; leaf id { type string; } leaf v { type int8; } }
        \\  }
        \\  rpc r { input { leaf i { type boolean; mandatory true; } } }
        \\}
    , "t.yang", null, true);
    const text1 = try gen.schemaToYangJson(a, m, &diag);
    var message: []const u8 = "";
    const back = try reloadForTest(a, text1, &message);
    try std.testing.expectEqualStrings("t", back.name);
    const top = back.statements.items[0];
    try std.testing.expectEqualStrings("pct", top.statements.items[0].data.leaf.type.?.name);
    try std.testing.expect(top.statements.items[1].data.leaf.type.?.patterns.items[0].compiled != null);
    try std.testing.expectEqualStrings("1..4", top.statements.items[1].data.leaf.type.?.length.?);
    try std.testing.expectEqualStrings("rpc", @tagName(back.statements.items[1].kind()));
    try std.testing.expectEqualStrings(text1, try gen.schemaToYangJson(a, back, &diag));
}

test "load errors carry Python's text" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var message: []const u8 = "";
    try std.testing.expectError(error.JsonForm, reloadForTest(a, "{\"type\": \"object\"}", &message));
    try std.testing.expectEqualStrings("JSON Schema has no root \"x-yang\" annotation; xYang needs a .yang.json produced by \"xyang convert\" (see design/json-schema-xyang-profile.md)", message);
    try std.testing.expectError(error.JsonForm, reloadForTest(a, "{\"x-yang\": {}, \"properties\": {\"a\": {\"type\": \"string\"}}}", &message));
    try std.testing.expectEqualStrings("JSON Schema property \"a\" has no \"x-yang\" annotation", message);
    try std.testing.expectError(error.JsonForm, reloadForTest(a, "{\"x-yang\": {\"prefix\": \"m\", \"extensions\": [{\"name\": \"q:e\"}]}}", &message));
    try std.testing.expectEqualStrings("extension invocation 'q:e': unknown prefix 'q'", message);
    try std.testing.expectError(error.JsonForm, reloadForTest(a, "{\"x-yang\": {\"imports\": {\"b\": {\"module\": 1}}}}", &message));
    try std.testing.expectEqualStrings("\"imports\" entry 'b' must be an object with \"module\" and \"prefix\"", message);
}
