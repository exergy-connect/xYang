//! Extension apply callbacks and their application after a load (mirrors
//! `src/xyang/ext/capabilities.py` and the built-in registrations in
//! `src/xyang/ext/rfc8791/`).
//!
//! One registry: an extension identity (defining module, extension name) maps to the
//! callback that replaces or removes each invocation. Invocations of other extensions
//! stay in the tree unchanged, like Python.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const Module = @import("../module.zig").Module;
const augment_expand = @import("../augment_expand.zig");
const refine_expand = @import("../refine_expand.zig");
const uses_expand = @import("../uses_expand.zig");

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
    .{ .module_name = RFC8791_MODULE, .extension_name = "structure", .apply = applyStructure },
    .{ .module_name = RFC8791_MODULE, .extension_name = "augment-structure", .apply = applyAugmentStructure },
};

pub fn find(module_name: []const u8, extension_name: []const u8) ?*const Capability {
    for (&CAPABILITIES) |*c| {
        if (std.mem.eql(u8, c.module_name, module_name) and std.mem.eql(u8, c.extension_name, extension_name)) return c;
    }
    return null;
}

/// RFC 8791 `sx:structure` is represented by the invocation node itself; it is
/// registered by name for `augment-structure` targets and structure instances.
fn applyStructure(r: *Reporter, invocation: *Statement, context_module: *Module) Error!?*Statement {
    const name = std.mem.trim(u8, invocation.data.extension_invocation.argument orelse "", &std.ascii.whitespace);
    if (name.len > 0) try context_module.structures.put(r.arena, name, invocation);
    return invocation;
}

fn lookupRegisteredStructure(module: *Module, name: []const u8) ?*Statement {
    return module.structures.get(name);
}

/// `apply_augment_structure_invocation`: copy the invocation's children into the target
/// node inside a registered structure; the invocation itself is removed.
fn applyAugmentStructure(r: *Reporter, invocation: *Statement, context_module: *Module) Error!?*Statement {
    const path = invocation.data.extension_invocation.argument orelse "";
    if (path.len == 0) return r.fail(.syntax, "augment-structure requires an absolute path argument", .{});
    const target = try augment_expand.resolveAbsoluteSchemaPath(r, context_module, path, "augment-structure", lookupRegisteredStructure);
    const copies = try refine_expand.copyStatements(r, invocation.statements.items);
    try uses_expand.mergeIfFeaturesIntoRoots(r.arena, copies.items, invocation.if_features.items);
    try uses_expand.mergeWhenIntoRoots(r.arena, copies.items, invocation.when);
    try target.statements.appendSlice(r.arena, copies.items);
    return null;
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
