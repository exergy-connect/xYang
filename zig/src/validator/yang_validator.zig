//! Validate an instance document against a module (mirrors `YangValidator` in
//! `src/xyang/validator/yang_validator.py`).
//!
//! The input is walked as written (`encoding/instance.zig`): encoding errors come first,
//! then the document validator's errors on the canonical projection, with pointers
//! mapped back to the input. An RFC 8791 structure instance is validated against the
//! structure. With `rpc` or `action` set, the data is that operation's input or output
//! (`operation.zig`); a call that makes no sense returns `error.Usage`.

const std = @import("std");
const builtin = @import("builtin");
const utf8 = @import("../utf8.zig");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const if_feature_eval = @import("../if_feature_eval.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const instance = @import("../encoding/instance.zig");
const type_checker = @import("type_checker.zig");
const document_validator = @import("document_validator.zig");
const operation = @import("operation.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Module = module_mod.Module;
const Statement = ast.Statement;
const Val = jv.Val;

pub const ValidationError = document_validator.ValidationError;
pub const Severity = document_validator.Severity;
pub const EnabledFeatures = if_feature_eval.EnabledFeatures;
pub const Error = type_checker.Error || error{Usage};

pub const Options = struct {
    native_json: bool = false,
    allow_jsonld: bool = true,
    allow_json_schema: bool = true,
    /// Module name -> enabled features; null enables every declared feature.
    enabled_features_by_module: ?*const EnabledFeatures = null,
    /// An rpc name: the data is that rpc's `direction` instance.
    rpc: ?[]const u8 = null,
    /// The RFC 8040 3.5.3 data resource identifier of an action node.
    action: ?[]const u8 = null,
    /// `input` or `output`.
    direction: []const u8 = "input",
    /// Server data (RFC 7950 6.4.1): validated first, then joined to the operation node.
    context: ?Val = null,
    /// With `native_json`: the data claims to be canonical. It is checked and validated as
    /// written, without a projection; a failed check returns only its errors.
    canonical: bool = false,
    /// Caller promises canonical native JSON, including canonical names, list arrays,
    /// scalar representations, and values unchanged by normalization. Debug builds
    /// verify the promise and panic on the first violation.
    canonical_trusted: bool = false,
    /// Caller promises that all instance strings and schema defaults checked as strings
    /// contain only ASCII. Debug builds assert the promise; a false promise is invalid.
    assume_ascii: bool = false,
};

pub const Result = struct {
    errors: []const ValidationError,
    warnings: []const ValidationError,

    pub fn valid(self: Result) bool {
        return self.errors.len == 0;
    }
};

pub const YangValidator = struct {
    a: Allocator,
    module: *Module,
    /// Set when `validate` returns `error.Unsupported` or `error.Raised`: the message.
    unsupported: ?[]const u8 = null,
    /// Set when `validate` returns `error.Usage`: Python's `ValueError` text.
    usage: ?[]const u8 = null,

    pub fn init(a: Allocator, module: *Module) YangValidator {
        return .{ .a = a, .module = module };
    }

    pub fn validate(self: *YangValidator, data: Val, options: Options) Error!Result {
        if (builtin.mode == .debug and options.assume_ascii) {
            assertAsciiValues(data);
            if (options.context) |context| assertAsciiValues(context);
        }
        var u: operation.Usage = .{ .a = self.a };
        const all = self.collect(&u, data, options) catch |err| {
            if (err == error.Usage) self.usage = u.message;
            return err;
        };
        var errors: std.ArrayList(ValidationError) = .empty;
        var warnings: std.ArrayList(ValidationError) = .empty;
        for (all) |e| try (if (e.severity == .@"error") &errors else &warnings).append(self.a, e);
        return .{ .errors = errors.items, .warnings = warnings.items };
    }

    fn collect(self: *YangValidator, u: *operation.Usage, data: Val, options: Options) Error![]const ValidationError {
        try operation.checkOptions(u, options.rpc, options.action, options.direction, options.context);
        if ((options.canonical or options.canonical_trusted) and !options.native_json) return u.fail("canonical applies only to native JSON (native_json=True)", .{});
        if ((options.canonical or options.canonical_trusted) and (options.rpc != null or options.action != null)) return u.fail("canonical does not apply to rpc or action instances", .{});
        if (options.rpc != null or options.action != null) return self.collectOperation(u, data, options);
        var checker: type_checker.TypeChecker = .{ .a = self.a, .root = self.module, .assume_ascii = options.assume_ascii };
        defer checker.deinit();
        var structure: ?*Statement = null;
        var structure_key: []const u8 = "";
        var instance_data = data;
        if (self.structureInstance(data)) |found| {
            structure = found.schema;
            structure_key = found.key;
            instance_data = found.inner;
            checker.module_schema = false;
        }
        var keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = if (structure == null) self.module.name else "" };
        var dv: document_validator.DocumentValidator = .{
            .a = self.a,
            .module = self.module,
            .enabled = try if_feature_eval.buildEnabledFeatures(self.a, self.module, options.enabled_features_by_module),
            .checker = &checker,
            .keys = &keys,
            .annotations = .{ .allow_jsonld = options.allow_jsonld, .allow_json_schema = options.allow_json_schema },
            .module_root = structure == null,
        };
        checker.enabled = &dv.enabled;
        checker.feature_module = dv.module;
        errdefer self.unsupported = checker.unsupported;

        var out: std.ArrayList(ValidationError) = .empty;
        var canonical = instance_data;
        var map: instance.PointerMap = .empty;
        if (options.canonical_trusted) {
            // A false proclamation is a caller bug: Debug builds stop on it, never fall back.
            if (builtin.mode == .debug) if (try self.trustedViolation(instance_data, structure, &keys, &checker)) |v|
                std.debug.panic("canonical_trusted violation at '{s}' ({s}): {s}", .{ v.pointer, v.code, v.message });
        } else if (options.canonical and instance_data == .object) {
            // One walk: the document validator runs the canonical check as it goes, and a
            // failed check returns only its errors.
            var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = true, .keys = &keys, .checker = &checker };
            var check: document_validator.Canonical = .{ .walk = &walk, .root = instance_data.object, .root_schema = structure };
            if (try walk.canonicalRoot(instance_data.object, structure, true, &check.issues)) {
                dv.canonical = &check;
                const found = if (structure) |s| try dv.validateStructure(instance_data, s) else try dv.validate(instance_data);
                // The validator enters the root unless it stops first; then check it here.
                if (check.root) |root| try walk.checkObject(root, structure, "", &check.issues);
                if (builtin.mode == .debug) try self.assertCanonicalParity(instance_data.object, structure, &keys, &checker, check.issues.items);
                if (check.issues.items.len == 0) {
                    try out.appendSlice(self.a, found);
                    return self.prefixStructure(structure, structure_key, out.items);
                }
            }
            for (check.issues.items) |i| try out.append(self.a, .{ .path = if (i.pointer.len > 0) i.pointer else "/", .pointer = i.pointer, .code = i.code, .message = i.message });
            return self.prefixStructure(structure, structure_key, out.items);
        } else {
            var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = options.native_json, .keys = &keys, .checker = &checker };
            const nodes = try walk.iterDocument(instance_data, structure, true);
            if (nodes.items.len > 0 or instance_data == .object) {
                const projection = try instance.project(self.a, &keys, nodes.items);
                canonical = .{ .object = projection.data };
                map = projection.map;
            }
            try document_validator.appendEncodingErrors(self.a, &out, nodes.items);
        }
        const found = if (structure) |s| try dv.validateStructure(canonical, s) else try dv.validate(canonical);
        for (found) |e| {
            var err = e;
            if (!options.canonical_trusted) err.pointer = try instance.remapPointer(self.a, e.pointer, &map);
            try out.append(self.a, err);
        }
        return self.prefixStructure(structure, structure_key, out.items);
    }

    /// The first way `data` breaks the `canonical_trusted` proclamation, or null when it holds.
    fn trustedViolation(self: *YangValidator, data: Val, structure: ?*Statement, keys: *rfc7951.MemberKeys, checker: *type_checker.TypeChecker) Error!?instance.EncodingIssue {
        if (data != .object) return .{ .pointer = "", .code = "canonical", .message = "a canonical instance is a JSON object" };
        var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = true, .keys = keys, .checker = checker };
        const issues = try walk.canonicalErrors(data.object, structure, true);
        return if (issues.len > 0) issues[0] else null;
    }

    /// Debug: the canonical check run during validation reports what the separate walk
    /// reports, in any order.
    fn assertCanonicalParity(self: *YangValidator, data: *const jv.Object, structure: ?*Statement, keys: *rfc7951.MemberKeys, checker: *type_checker.TypeChecker, fused: []const instance.EncodingIssue) Error!void {
        var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = true, .keys = keys, .checker = checker };
        const separate = try walk.canonicalErrors(data, structure, true);
        const lines = struct {
            fn of(a: Allocator, issues: []const instance.EncodingIssue) error{OutOfMemory}![]const u8 {
                const out = try a.alloc([]const u8, issues.len);
                for (issues, out) |i, *line| line.* = try a.print("{s} {s} {s}", .{ i.pointer, i.code, i.message });
                std.mem.sort([]const u8, out, {}, struct {
                    fn lt(_: void, x: []const u8, y: []const u8) bool {
                        return std.mem.order(u8, x, y) == .lt;
                    }
                }.lt);
                return std.mem.join(a, "\n", out);
            }
        };
        const want = try lines.of(self.a, separate);
        const got = try lines.of(self.a, fused);
        if (!std.mem.eql(u8, want, got)) std.debug.panic("fused canonical check differs\nseparate:\n{s}\nfused:\n{s}", .{ want, got });
    }

    fn prefixStructure(self: *YangValidator, structure: ?*Statement, structure_key: []const u8, errors: []ValidationError) error{OutOfMemory}![]const ValidationError {
        if (structure != null) {
            for (errors) |*e| {
                e.pointer = try prefixMember(self.a, structure_key, e.pointer);
                e.path = try prefixMember(self.a, structure_key, e.path);
            }
        }
        return errors;
    }

    fn collectOperation(self: *YangValidator, u: *operation.Usage, data: Val, options: Options) Error![]const ValidationError {
        const target = if (options.rpc) |name| try operation.findRpc(u, self.module, name) else try operation.resolveAction(u, self.module, options.action.?);
        const op_node = try operation.operationNode(self.a, target.operation, operation.findBody(target.operation, options.direction));
        var out: std.ArrayList(ValidationError) = .empty;
        if (options.context) |context| {
            // RFC 7950 6.4.1: the operation reads the server data, so it must be valid data first.
            const issues = try self.collect(u, context, .{ .native_json = options.native_json, .enabled_features_by_module = options.enabled_features_by_module, .allow_jsonld = options.allow_jsonld, .allow_json_schema = options.allow_json_schema });
            var has_error = false;
            for (issues) |issue| {
                var e = issue;
                e.document = "context";
                if (e.severity == .@"error") has_error = true;
                try out.append(self.a, e);
            }
            if (has_error) return out.items;
        }
        var member: ?[]const u8 = null;
        var params = data;
        if (!options.native_json) {
            const m = try operation.wrapperMember(self.a, target.module_name, options.direction);
            member = m;
            var members: std.ArrayList([]const u8) = .empty;
            if (data == .object) for (data.object.keys()) |key| {
                if (!@import("../encoding/annotations.zig").isAnnotation(key, .{ .allow_jsonld = options.allow_jsonld, .allow_json_schema = options.allow_json_schema })) try members.append(self.a, key);
            };
            const single = data == .object and members.items.len == 1 and std.mem.eql(u8, members.items[0], m);
            if (!single) {
                var found: []const u8 = jv.typeName(data);
                if (data == .object) {
                    var names: std.ArrayList([]const u8) = .empty;
                    for (data.object.keys()) |k| try names.append(self.a, try self.a.print("{f}", .{pyfmt.repr(k)}));
                    found = if (names.items.len > 0) try std.mem.join(self.a, ", ", names.items) else "no members";
                }
                const kind = if (options.rpc != null) "rpc" else "action";
                const one = try self.a.alloc(ValidationError, 1);
                one[0] = .{
                    .path = "/",
                    .pointer = "",
                    .code = "operation-wrapper",
                    .message = try self.a.print("{s} {s} must be an object with the single member '{s}' (RFC 8040 \u{a7}3.6); found {s}. Pass native_json=True for the bare parameter object", .{ kind, options.direction, m, found }),
                };
                return one;
            }
            params = data.object.get(m).?;
            if (params != .object) {
                const one = try self.a.alloc(ValidationError, 1);
                one[0] = .{
                    .path = try self.a.print("/{s}", .{m}),
                    .pointer = try prefixMember(self.a, m, ""),
                    .code = "type",
                    .message = try self.a.print("{s} must be an object", .{options.direction}),
                };
                return one;
            }
        }
        const accessible = try operation.accessibleModule(self.a, self.module, target, op_node);
        var checker: type_checker.TypeChecker = .{ .a = self.a, .root = accessible.module, .assume_ascii = options.assume_ascii };
        defer checker.deinit();
        var keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = self.module.name };
        var dv: document_validator.DocumentValidator = .{
            .a = self.a,
            .module = accessible.module,
            .enabled = try if_feature_eval.buildEnabledFeatures(self.a, accessible.module, options.enabled_features_by_module),
            .checker = &checker,
            .keys = &keys,
            .annotations = .{ .allow_jsonld = options.allow_jsonld, .allow_json_schema = options.allow_json_schema },
        };
        checker.enabled = &dv.enabled;
        checker.feature_module = dv.module;
        errdefer self.unsupported = checker.unsupported;
        const errors = try dv.validateOperation(u, params, .{
            .target = target,
            .operation = op_node,
            .parent_copies = accessible.parent_copies,
            .host = self.module,
            .context = options.context,
            .native = options.native_json,
        });
        for (errors) |e| {
            var err = e;
            if (member) |m| if (std.mem.eql(u8, err.document, "data")) {
                err.pointer = try prefixMember(self.a, m, err.pointer);
                err.path = try prefixMember(self.a, m, err.path);
            };
            try out.append(self.a, err);
        }
        return out.items;
    }

    const StructureInstance = struct { schema: *Statement, inner: Val, key: []const u8 };

    /// `resolve_structure_instance`: one object member naming a registered `sx:structure`
    /// (`msg` or `module:msg`) whose value is an object.
    fn structureInstance(self: *YangValidator, data: Val) ?StructureInstance {
        if (data != .object or data.object.count() != 1) return null;
        const key = data.object.keys()[0];
        const inner = data.object.values()[0];
        if (inner != .object) return null;
        var name = key;
        if (std.mem.findScalar(u8, key, ':')) |colon| {
            if (!std.mem.eql(u8, key[0..colon], self.module.name) or colon + 1 == key.len) return null;
            name = key[colon + 1 ..];
        }
        const schema = self.module.structures.get(name) orelse return null;
        return .{ .schema = schema, .inner = inner, .key = key };
    }
};

fn assertAsciiValues(value: Val) void {
    switch (value) {
        .string => |s| {
            _ = utf8.AsciiSlice.initTrusted(s);
        },
        .array => |items| for (items) |item| assertAsciiValues(item),
        .object => |obj| for (obj.values()) |item| assertAsciiValues(item),
        else => {},
    }
}

/// `_prefix_member`: a path or JSON Pointer under the member as written.
fn prefixMember(a: Allocator, json_key: []const u8, location: []const u8) error{OutOfMemory}![]const u8 {
    const token = try instance.pointerToken(a, json_key);
    if (location.len == 0 or std.mem.eql(u8, location, "/")) return a.print("/{s}", .{token});
    if (location[0] == '/') return a.print("/{s}{s}", .{ token, location });
    return a.print("/{s}/{s}", .{ token, location });
}

/// `ValidationError.__str__` / `YangValidator._format_error`.
pub fn formatError(a: Allocator, e: ValidationError) error{OutOfMemory}![]const u8 {
    const where = if (std.mem.eql(u8, e.document, "data")) e.path else try a.print("{s} {s}", .{ e.document, e.path });
    if (e.expression) |x| if (x.len > 0) return a.print("{s}: {s} (expression: {s})", .{ where, e.message, x });
    return a.print("{s}: {s}", .{ where, e.message });
}

/// `_feature_map` on a parsed `--features` / case-file value; null enables everything.
pub fn featureMap(a: Allocator, value: Val, message: *[]const u8) error{ OutOfMemory, InvalidFeatures }!?*EnabledFeatures {
    if (value == .null) return null;
    if (value != .object) {
        message.* = "features must be a mapping of module name to feature names, or None";
        return error.InvalidFeatures;
    }
    const out = try a.create(EnabledFeatures);
    out.* = .empty;
    var it = value.object.iterator();
    while (it.next()) |e| {
        const name = e.key_ptr.*;
        const feats = e.value_ptr.*;
        if (feats != .array) {
            message.* = try a.print("features[{f}] must be an iterable of feature name strings", .{pyfmt.repr(name)});
            return error.InvalidFeatures;
        }
        var set: if_feature_eval.FeatureSet = .empty;
        for (feats.array) |f| {
            if (f != .string) {
                message.* = try a.print("features[{f}] must be an iterable of feature name strings", .{pyfmt.repr(name)});
                return error.InvalidFeatures;
            }
            try set.put(a, f.string, {});
        }
        try out.put(a, name, set);
    }
    return out;
}

test "ASCII proclamation preserves validation results" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; leaf x { type string { length '2..4'; pattern '[a-z]+'; } } }", "test.yang", &diag);
    var message: []const u8 = "";
    const data = try jv.parse(a, "{\"m:x\":\"abc\"}", &message);
    var validator = YangValidator.init(a, module);
    try std.testing.expect((try validator.validate(data, .{})).valid());
    try std.testing.expect((try validator.validate(data, .{ .assume_ascii = true })).valid());
    const invalid = try jv.parse(a, "{\"m:x\":\"A\"}", &message);
    const normal = try validator.validate(invalid, .{});
    const claimed = try validator.validate(invalid, .{ .assume_ascii = true });
    try std.testing.expectEqual(normal.errors.len, claimed.errors.len);
    try std.testing.expectEqual(@as(usize, 2), claimed.errors.len);
}

test "trusted canonical native input preserves validation results" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; leaf x { type string { length '2..4'; } } }", "test.yang", &diag);
    var message: []const u8 = "";
    const data = try jv.parse(a, "{\"x\":\"a\"}", &message);
    var validator = YangValidator.init(a, module);
    const checked = try validator.validate(data, .{ .native_json = true, .canonical = true });
    const trusted = try validator.validate(data, .{ .native_json = true, .canonical_trusted = true });
    try std.testing.expectEqual(@as(usize, 1), checked.errors.len);
    try std.testing.expectEqualStrings(checked.errors[0].code, trusted.errors[0].code);
    try std.testing.expectEqualStrings(checked.errors[0].pointer, trusted.errors[0].pointer);
}

test "canonical native keyed list is rejected before document errors" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; list item { key 'id'; leaf id { type string; } } leaf required { type string; mandatory true; } }", "test.yang", &diag);
    var message: []const u8 = "";
    const data = try jv.parse(a, "{\"item\":{\"a\":{\"id\":\"a\"}}}", &message);
    var validator = YangValidator.init(a, module);
    const result = try validator.validate(data, .{ .native_json = true, .canonical = true });
    try std.testing.expectEqual(@as(usize, 1), result.errors.len);
    try std.testing.expectEqualStrings("canonical", result.errors[0].code);
    try std.testing.expectEqualStrings("/item", result.errors[0].pointer);
}

test "canonical native wrong module prefix is rejected" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; leaf x { type string; } }", "test.yang", &diag);
    var message: []const u8 = "";
    const data = try jv.parse(a, "{\"other:x\":\"a\"}", &message);
    var validator = YangValidator.init(a, module);
    const result = try validator.validate(data, .{ .native_json = true, .canonical = true });
    try std.testing.expectEqual(@as(usize, 1), result.errors.len);
    try std.testing.expectEqualStrings("unknown-field", result.errors[0].code);
}

test "canonical native dotted key is rejected" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const dir = "../tests/cases/normalization/dotted";
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, std.testing.io, &diag, &.{dir});
    const module = try loader.parseFile(dir ++ "/m.yang");
    var message: []const u8 = "";
    const data = try jv.parse(a, "{\"defaults.bgp.as\":65000}", &message);
    var validator = YangValidator.init(a, module);
    const result = try validator.validate(data, .{ .native_json = true, .canonical = true });
    try std.testing.expectEqual(@as(usize, 1), result.errors.len);
    try std.testing.expectEqualStrings("canonical", result.errors[0].code);
    try std.testing.expectEqualStrings("/defaults.bgp.as", result.errors[0].pointer);
}

test "trusted canonical proclamation detects non-canonical input" {
    // Debug builds panic with this violation; the check itself is tested here.
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; list item { key 'id'; leaf id { type string; } } }", "test.yang", &diag);
    var message: []const u8 = "";
    var validator = YangValidator.init(a, module);
    var checker: type_checker.TypeChecker = .{ .a = a, .root = module };
    defer checker.deinit();
    var keys: rfc7951.MemberKeys = .{ .a = a, .parent_module = module.name };
    const keyed = try jv.parse(a, "{\"item\":{\"a\":{\"id\":\"a\"}}}", &message);
    const violation = (try validator.trustedViolation(keyed, null, &keys, &checker)) orelse return error.TestExpectedViolation;
    try std.testing.expectEqualStrings("canonical", violation.code);
    try std.testing.expectEqualStrings("/item", violation.pointer);
    try std.testing.expect((try validator.trustedViolation(.null, null, &keys, &checker)) != null);
    const canonical = try jv.parse(a, "{\"item\":[{\"id\":\"a\"}]}", &message);
    try std.testing.expect((try validator.trustedViolation(canonical, null, &keys, &checker)) == null);
}

fn canonicalErrorsFor(a: Allocator, yang: []const u8, json: []const u8) ![]const ValidationError {
    var diag: @import("../errors.zig").Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, yang, "test.yang", &diag);
    var message: []const u8 = "";
    const data = try jv.parse(a, json, &message);
    var validator = YangValidator.init(a, module);
    return (try validator.validate(data, .{ .native_json = true, .canonical = true })).errors;
}

test "canonical check covers a subtree whose when is false" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const errors = try canonicalErrorsFor(arena.allocator(),
        "module m { namespace 'urn:m'; prefix m; leaf on { type boolean; } container c { when '../on = \"true\"'; container inner { list item { key 'id'; leaf id { type string; } } } } }",
        "{\"on\":false,\"c\":{\"inner\":{\"item\":{\"a\":{\"id\":\"a\"}}}}}");
    try std.testing.expectEqual(@as(usize, 1), errors.len);
    try std.testing.expectEqualStrings("canonical", errors[0].code);
    try std.testing.expectEqualStrings("/c/inner/item", errors[0].pointer);
}

test "canonical check covers a container given as a non-object" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const errors = try canonicalErrorsFor(arena.allocator(),
        "module m { namespace 'urn:m'; prefix m; container c { leaf x { type string; } } list l { key 'id'; leaf id { type string; } container d { leaf y { type int64; } } } }",
        "{\"c\":1,\"l\":[{\"id\":\"a\",\"d\":{\"y\":\"7\"}},2]}");
    try std.testing.expectEqual(@as(usize, 3), errors.len);
    var codes: [3][]const u8 = undefined;
    for (errors, &codes) |e, *c| c.* = try std.fmt.allocPrint(arena.allocator(), "{s} {s}", .{ e.pointer, e.code });
    std.mem.sort([]const u8, &codes, {}, struct {
        fn lt(_: void, x: []const u8, y: []const u8) bool {
            return std.mem.order(u8, x, y) == .lt;
        }
    }.lt);
    try std.testing.expectEqualStrings("/c type", codes[0]);
    try std.testing.expectEqualStrings("/l/0/d/y type", codes[1]);
    try std.testing.expectEqualStrings("/l/1 type", codes[2]);
}

test "canonical check covers members of a choice" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const errors = try canonicalErrorsFor(arena.allocator(),
        "module m { namespace 'urn:m'; prefix m; container c { choice ch { case a { container ca { list item { key 'id'; leaf id { type string; } } } } case b { leaf cb { type string; } } } } }",
        "{\"c\":{\"ca\":{\"item\":{\"k\":{\"id\":\"k\"}}},\"cb\":\"x\"}}");
    try std.testing.expectEqual(@as(usize, 1), errors.len);
    try std.testing.expectEqualStrings("/c/ca/item", errors[0].pointer);
}

test "valid canonical input returns the document errors" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const errors = try canonicalErrorsFor(arena.allocator(),
        "module m { namespace 'urn:m'; prefix m; list l { key 'id'; leaf id { type string; } leaf n { type int64; mandatory true; } } }",
        "{\"l\":[{\"id\":\"a\",\"n\":1},{\"id\":\"b\"}]}");
    try std.testing.expectEqual(@as(usize, 1), errors.len);
    try std.testing.expectEqualStrings("mandatory", errors[0].code);
    try std.testing.expectEqualStrings("/l/1/n", errors[0].pointer);
}
