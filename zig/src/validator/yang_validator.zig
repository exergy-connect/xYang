//! Validate an instance document against a module (mirrors `YangValidator` in
//! `src/xyang/validator/yang_validator.py`).
//!
//! The input is walked as written (`encoding/instance.zig`): encoding errors come first,
//! then the document validator's errors on the canonical projection, with pointers
//! mapped back to the input. Operations (`rpc` / `action`) and RFC 8791 structure
//! instances are phase 5 of #165 and fail with `error.Unsupported`.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const if_feature_eval = @import("../if_feature_eval.zig");
const capabilities = @import("../ext/capabilities.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const instance = @import("../encoding/instance.zig");
const type_checker = @import("type_checker.zig");
const document_validator = @import("document_validator.zig");

const Allocator = std.mem.Allocator;
const Module = module_mod.Module;
const Statement = ast.Statement;
const Val = jv.Val;

pub const ValidationError = document_validator.ValidationError;
pub const Severity = document_validator.Severity;
pub const EnabledFeatures = if_feature_eval.EnabledFeatures;
pub const Error = type_checker.Error;

pub const Options = struct {
    native_json: bool = false,
    /// Module name -> enabled features; null enables every declared feature.
    enabled_features_by_module: ?*const EnabledFeatures = null,
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
    /// Set when `validate` returns `error.Unsupported`: what this port cannot check yet.
    unsupported: ?[]const u8 = null,

    pub fn init(a: Allocator, module: *Module) YangValidator {
        return .{ .a = a, .module = module };
    }

    pub fn validate(self: *YangValidator, data: Val, options: Options) Error!Result {
        const all = try self.collect(data, options);
        var errors: std.ArrayList(ValidationError) = .empty;
        var warnings: std.ArrayList(ValidationError) = .empty;
        for (all) |e| try (if (e.severity == .@"error") &errors else &warnings).append(self.a, e);
        return .{ .errors = errors.items, .warnings = warnings.items };
    }

    fn collect(self: *YangValidator, data: Val, options: Options) Error![]const ValidationError {
        if (try self.structureMember(data)) |name| {
            self.unsupported = try std.fmt.allocPrint(self.a, "xyang-zig cannot validate the RFC 8791 structure '{s}' yet (structure instances are phase 5 of #165)", .{name});
            return error.Unsupported;
        }
        var checker: type_checker.TypeChecker = .{ .a = self.a, .root = self.module };
        var keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = self.module.name };
        var dv: document_validator.DocumentValidator = .{
            .a = self.a,
            .module = self.module,
            .enabled = try if_feature_eval.buildEnabledFeatures(self.a, self.module, options.enabled_features_by_module),
            .checker = &checker,
            .keys = &keys,
        };
        errdefer self.unsupported = checker.unsupported;

        var out: std.ArrayList(ValidationError) = .empty;
        var canonical = data;
        var map: instance.PointerMap = .empty;
        if (data == .object) {
            var walk: instance.Walk = .{ .a = self.a, .module = self.module, .native = options.native_json, .keys = &keys, .checker = &checker };
            const nodes = try walk.walkObject(data.object, null, "", true);
            const projection = try instance.project(self.a, &keys, nodes.items);
            canonical = .{ .object = projection.data };
            map = projection.map;
            for (try instance.encodingErrors(self.a, nodes.items)) |e| {
                try out.append(self.a, .{ .path = if (e.pointer.len > 0) e.pointer else "/", .pointer = e.pointer, .code = e.code, .message = e.message });
            }
        }
        for (try dv.validate(canonical)) |e| {
            var err = e;
            err.pointer = try instance.remapPointer(self.a, e.pointer, &map);
            try out.append(self.a, err);
        }
        return out.items;
    }

    /// `resolve_structure_instance`: the member when `data` is one object naming a
    /// registered `sx:structure` (`msg` or `module:msg`).
    fn structureMember(self: *YangValidator, data: Val) error{OutOfMemory}!?[]const u8 {
        if (data != .object or data.object.count() != 1) return null;
        const key = data.object.keys()[0];
        if (data.object.values()[0] != .object) return null;
        var name = key;
        if (std.mem.indexOfScalar(u8, key, ':')) |colon| {
            if (!std.mem.eql(u8, key[0..colon], self.module.name) or colon + 1 == key.len) return null;
            name = key[colon + 1 ..];
        }
        return if (hasStructure(self.module.statements.items, name)) key else null;
    }

    fn hasStructure(statements: []const *Statement, name: []const u8) bool {
        for (statements) |s| {
            switch (s.data) {
                .extension_invocation => |inv| {
                    const ext = inv.resolved_extension;
                    if (std.mem.eql(u8, ext.data.extension.module_name, capabilities.RFC8791_MODULE) and std.mem.eql(u8, ext.name, "structure")) {
                        if (std.mem.eql(u8, std.mem.trim(u8, inv.argument orelse "", &std.ascii.whitespace), name)) return true;
                    }
                },
                .choice => |c| for (c.cases.items) |case| if (hasStructure(case.statements.items, name)) return true,
                else => {},
            }
            if (hasStructure(s.statements.items, name)) return true;
        }
        return false;
    }
};

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
            message.* = try std.fmt.allocPrint(a, "features[{f}] must be an iterable of feature name strings", .{@import("../pyfmt.zig").repr(name)});
            return error.InvalidFeatures;
        }
        var set: if_feature_eval.FeatureSet = .empty;
        for (feats.array) |f| {
            if (f != .string) {
                message.* = try std.fmt.allocPrint(a, "features[{f}] must be an iterable of feature name strings", .{@import("../pyfmt.zig").repr(name)});
                return error.InvalidFeatures;
            }
            try set.put(a, f.string, {});
        }
        try out.put(a, name, set);
    }
    return out;
}
