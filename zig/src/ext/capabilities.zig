//! Extension apply callbacks and their application after a load (mirrors
//! `src/xyang/ext/capabilities.py` and the built-in registrations in
//! `src/xyang/ext/rfc8791/__init__.py`).
//!
//! One registry: an extension identity (defining module, extension name) maps to the
//! callback that replaces or removes each invocation. Invocations of other extensions
//! stay in the tree unchanged, like Python.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const Module = @import("../module.zig").Module;

const Statement = ast.Statement;
const Error = errors.Error;
const Reporter = errors.Reporter;

/// Returns the statement that replaces the invocation, or null to remove it.
pub const ApplyFn = *const fn (r: *Reporter, invocation: *Statement, context_module: *Module) Error!?*Statement;

pub const Capability = struct {
    module_name: []const u8,
    extension_name: []const u8,
    apply: ApplyFn,
};

pub const RFC8791_MODULE = "ietf-yang-structure-ext";

pub const CAPABILITIES = [_]Capability{
    // RFC 8791 `sx:structure` is represented by the invocation node itself.
    .{ .module_name = RFC8791_MODULE, .extension_name = "structure", .apply = keepInvocation },
    .{ .module_name = RFC8791_MODULE, .extension_name = "augment-structure", .apply = augmentStructureUnsupported },
};

pub fn find(module_name: []const u8, extension_name: []const u8) ?*const Capability {
    for (&CAPABILITIES) |*c| {
        if (std.mem.eql(u8, c.module_name, module_name) and std.mem.eql(u8, c.extension_name, extension_name)) return c;
    }
    return null;
}

fn keepInvocation(_: *Reporter, invocation: *Statement, _: *Module) Error!?*Statement {
    return invocation;
}

fn augmentStructureUnsupported(r: *Reporter, invocation: *Statement, _: *Module) Error!?*Statement {
    return r.fail(.unsupported, "xyang-zig cannot apply '{s}' yet (RFC 8791 augment-structure is phase 5 of #165)", .{invocation.name});
}

/// `apply_extension_invocations`: walk the schema tree and apply each registered callback.
pub fn applyExtensionInvocations(r: *Reporter, module: *Module) Error!void {
    module.statements = try walk(r, module, module.statements.items);
}

fn walk(r: *Reporter, module: *Module, statements: []const *Statement) Error!std.ArrayList(*Statement) {
    var out: std.ArrayList(*Statement) = .empty;
    for (statements) |s| {
        var cur: ?*Statement = s;
        switch (s.data) {
            .extension_invocation => |inv| {
                const ext = inv.resolved_extension;
                if (find(ext.data.extension.module_name, ext.name)) |cap| cur = try cap.apply(r, s, module);
            },
            else => {},
        }
        const node = cur orelse continue;
        if (node.kind() == .choice) {
            for (node.data.choice.cases.items) |case| case.statements = try walk(r, module, case.statements.items);
        }
        node.statements = try walk(r, module, node.statements.items);
        try out.append(r.arena, node);
    }
    return out;
}

test "registry lookup by extension identity" {
    try std.testing.expect(find(RFC8791_MODULE, "structure") != null);
    try std.testing.expect(find(RFC8791_MODULE, "augment-structure") != null);
    try std.testing.expect(find("other", "structure") == null);
}
