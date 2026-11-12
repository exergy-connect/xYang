//! Validate an instance document against a module (mirrors `YangValidator` in
//! `src/xyang/validator/yang_validator.py`).
//!
//! The input is walked as written (`encoding/instance.zig`): encoding errors come first,
//! then the document validator's errors on the canonical projection, with pointers
//! mapped back to the input. An RFC 8791 structure instance is validated against the
//! structure. With `rpc` or `action` set, the data is that operation's input or output
//! (`operation.zig`); a call that makes no sense returns `error.Usage`.

const std = @import("std");
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
        if (options.rpc != null or options.action != null) return self.collectOperation(u, data, options);
        var checker: type_checker.TypeChecker = .{ .a = self.a, .root = self.module };
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
            .module_root = structure == null,
        };
        errdefer self.unsupported = checker.unsupported;

        var out: std.ArrayList(ValidationError) = .empty;
        var canonical = instance_data;
        var map: instance.PointerMap = .empty;
        if (instance_data == .object) {
            var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = options.native_json, .keys = &keys, .checker = &checker };
            const nodes = try walk.walkObject(instance_data.object, structure, "", true);
            const projection = try instance.project(self.a, &keys, nodes.items);
            canonical = .{ .object = projection.data };
            map = projection.map;
            for (try instance.encodingErrors(self.a, nodes.items)) |e| {
                try out.append(self.a, .{ .path = if (e.pointer.len > 0) e.pointer else "/", .pointer = e.pointer, .code = e.code, .message = e.message });
            }
        }
        const found = if (structure) |s| try dv.validateStructure(canonical, s) else try dv.validate(canonical);
        for (found) |e| {
            var err = e;
            err.pointer = try instance.remapPointer(self.a, e.pointer, &map);
            try out.append(self.a, err);
        }
        if (structure != null) {
            for (out.items) |*e| {
                e.pointer = try prefixMember(self.a, structure_key, e.pointer);
                e.path = try prefixMember(self.a, structure_key, e.path);
            }
        }
        return out.items;
    }

    fn collectOperation(self: *YangValidator, u: *operation.Usage, data: Val, options: Options) Error![]const ValidationError {
        const target = if (options.rpc) |name| try operation.findRpc(u, self.module, name) else try operation.resolveAction(u, self.module, options.action.?);
        const op_node = try operation.operationNode(self.a, target.operation, operation.findBody(target.operation, options.direction));
        var out: std.ArrayList(ValidationError) = .empty;
        if (options.context) |context| {
            // RFC 7950 6.4.1: the operation reads the server data, so it must be valid data first.
            const issues = try self.collect(u, context, .{ .native_json = options.native_json, .enabled_features_by_module = options.enabled_features_by_module });
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
            const single = data == .object and data.object.count() == 1 and std.mem.eql(u8, data.object.keys()[0], m);
            if (!single) {
                var found: []const u8 = jv.typeName(data);
                if (data == .object) {
                    var names: std.ArrayList([]const u8) = .empty;
                    for (data.object.keys()) |k| try names.append(self.a, try std.fmt.allocPrint(self.a, "{f}", .{pyfmt.repr(k)}));
                    found = if (names.items.len > 0) try std.mem.join(self.a, ", ", names.items) else "no members";
                }
                const kind = if (options.rpc != null) "rpc" else "action";
                const one = try self.a.alloc(ValidationError, 1);
                one[0] = .{
                    .path = "/",
                    .pointer = "",
                    .code = "operation-wrapper",
                    .message = try std.fmt.allocPrint(self.a, "{s} {s} must be an object with the single member '{s}' (RFC 8040 \u{a7}3.6); found {s}. Pass native_json=True for the bare parameter object", .{ kind, options.direction, m, found }),
                };
                return one;
            }
            params = data.object.values()[0];
            if (params != .object) {
                const one = try self.a.alloc(ValidationError, 1);
                one[0] = .{
                    .path = try std.fmt.allocPrint(self.a, "/{s}", .{m}),
                    .pointer = try prefixMember(self.a, m, ""),
                    .code = "type",
                    .message = try std.fmt.allocPrint(self.a, "{s} must be an object", .{options.direction}),
                };
                return one;
            }
        }
        const accessible = try operation.accessibleModule(self.a, self.module, target, op_node);
        var checker: type_checker.TypeChecker = .{ .a = self.a, .root = accessible.module };
        var keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = self.module.name };
        var dv: document_validator.DocumentValidator = .{
            .a = self.a,
            .module = accessible.module,
            .enabled = try if_feature_eval.buildEnabledFeatures(self.a, accessible.module, options.enabled_features_by_module),
            .checker = &checker,
            .keys = &keys,
        };
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
        if (std.mem.indexOfScalar(u8, key, ':')) |colon| {
            if (!std.mem.eql(u8, key[0..colon], self.module.name) or colon + 1 == key.len) return null;
            name = key[colon + 1 ..];
        }
        const schema = self.module.structures.get(name) orelse return null;
        return .{ .schema = schema, .inner = inner, .key = key };
    }
};

/// `_prefix_member`: a path or JSON Pointer under the member as written.
fn prefixMember(a: Allocator, json_key: []const u8, location: []const u8) error{OutOfMemory}![]const u8 {
    const token = try instance.pointerToken(a, json_key);
    if (location.len == 0 or std.mem.eql(u8, location, "/")) return std.fmt.allocPrint(a, "/{s}", .{token});
    if (location[0] == '/') return std.fmt.allocPrint(a, "/{s}{s}", .{ token, location });
    return std.fmt.allocPrint(a, "/{s}/{s}", .{ token, location });
}

/// `ValidationError.__str__` / `YangValidator._format_error`.
pub fn formatError(a: Allocator, e: ValidationError) error{OutOfMemory}![]const u8 {
    const where = if (std.mem.eql(u8, e.document, "data")) e.path else try std.fmt.allocPrint(a, "{s} {s}", .{ e.document, e.path });
    if (e.expression) |x| if (x.len > 0) return std.fmt.allocPrint(a, "{s}: {s} (expression: {s})", .{ where, e.message, x });
    return std.fmt.allocPrint(a, "{s}: {s}", .{ where, e.message });
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
            message.* = try std.fmt.allocPrint(a, "features[{f}] must be an iterable of feature name strings", .{pyfmt.repr(name)});
            return error.InvalidFeatures;
        }
        var set: if_feature_eval.FeatureSet = .empty;
        for (feats.array) |f| {
            if (f != .string) {
                message.* = try std.fmt.allocPrint(a, "features[{f}] must be an iterable of feature name strings", .{pyfmt.repr(name)});
                return error.InvalidFeatures;
            }
            try set.put(a, f.string, {});
        }
        try out.put(a, name, set);
    }
    return out;
}
