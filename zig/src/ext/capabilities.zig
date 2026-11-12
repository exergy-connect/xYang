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
    if (module.structures.get(name)) |node| return node;
    for (module.statements.items) |node| {
        if (isRfc8791(node, "structure") and std.mem.eql(u8, std.mem.trim(u8, node.data.extension_invocation.argument orelse "", &std.ascii.whitespace), name)) return node;
    }
    return null;
}

/// `apply_augment_structure_invocation`: copy the invocation's children into the target
/// node inside a registered structure; the invocation itself is removed.
fn applyAugmentStructure(r: *Reporter, invocation: *Statement, context_module: *Module) Error!?*Statement {
    if (invocation.rfc8791_applied) return null;
    const path = invocation.data.extension_invocation.argument orelse "";
    if (path.len == 0) return r.fail(.syntax, "augment-structure requires an absolute path argument", .{});
    const target = try augment_expand.resolveAbsoluteSchemaPath(r, context_module, path, "augment-structure", lookupRegisteredStructure);
    const copies = try refine_expand.copyStatements(r, invocation.statements.items);
    try uses_expand.mergeIfFeaturesIntoRoots(r.arena, copies.items, invocation.if_features.items);
    const when = if (invocation.when) |original| blk: {
        const copy = try r.arena.create(ast.WhenStmt);
        copy.* = original.*;
        break :blk copy;
    } else null;
    try uses_expand.mergeWhenIntoRoots(r.arena, copies.items, when);
    for (copies.items) |node| {
        node.augment_structure = path;
        node.augment_structure_module = context_module.name;
    }
    invocation.rfc8791_applied = true;
    try target.statements.appendSlice(r.arena, copies.items);
    return null;
}

/// RFC 8791 identities are resolved by defining module, never by the local prefix.
pub fn isRfc8791(node: *const Statement, name: []const u8) bool {
    if (node.kind() != .extension_invocation) return false;
    const inv = node.data.extension_invocation;
    return std.mem.eql(u8, inv.resolved_module, RFC8791_MODULE) and std.mem.eql(u8, inv.resolved_extension.name, name);
}

pub fn augmentOwner(module: *Module, path: []const u8) ?*Module {
    const raw = std.mem.trimStart(u8, std.mem.trim(u8, path, &std.ascii.whitespace), "/");
    const colon = std.mem.indexOfScalar(u8, raw, ':') orelse return null;
    return module.resolvePrefixedModule(raw[0..colon]);
}

/// Apply callbacks after loading YANG or native JSON.
pub fn applyExtensionInvocations(r: *Reporter, module: *Module) Error!void {
    module.statements = try walk(r, module, module.statements.items, false, true);
}

/// Merge own augments on the export copy; leave imported modules untouched.
pub fn applyForExport(r: *Reporter, module: *Module) Error!void {
    // A copied module must index its copied structures, not the original nodes.
    module.structures = .empty;
    module.statements = try walk(r, module, module.statements.items, true, true);
}

fn walk(r: *Reporter, module: *Module, statements: []const *Statement, export_view: bool, at_root: bool) Error!std.ArrayList(*Statement) {
    var out: std.ArrayList(*Statement) = .empty;
    var kept_extensions: usize = 0;
    for (statements) |s| {
        var cur: ?*Statement = s;
        var foreign = false;
        if (s.kind() == .extension_invocation) {
            const inv = s.data.extension_invocation;
            if (isRfc8791(s, "augment-structure")) {
                const owner = augmentOwner(module, inv.argument orelse "");
                foreign = owner != null and owner.? != module;
            }
            if (export_view and foreign) {
                // Validate the target without merging into the imported module.
                _ = try augment_expand.resolveAbsoluteSchemaPath(r, module, inv.argument orelse "", "augment-structure", lookupRegisteredStructure);
            } else {
                if (find(inv.resolved_extension.data.extension.module_name, inv.resolved_extension.name)) |cap| cur = try cap.apply(r, s, module);
            }
        }
        if (cur == null and at_root and foreign and !export_view) {
            if (std.mem.indexOfScalar(*Statement, module.foreign_structure_augments.items, s) == null) {
                try module.foreign_structure_augments.append(r.arena, s);
                try module.foreign_structure_slots.append(r.arena, kept_extensions);
            }
        }
        const node = cur orelse continue;
        if (node.kind() == .choice) {
            for (node.data.choice.cases.items) |case| case.statements = try walk(r, module, case.statements.items, export_view, false);
        }
        node.statements = try walk(r, module, node.statements.items, export_view, false);
        if (at_root and node.kind() == .extension_invocation) kept_extensions += 1;
        try out.append(r.arena, node);
    }
    return out;
}

test "registry lookup by extension identity" {
    try std.testing.expect(find(RFC8791_MODULE, "structure") != null);
    try std.testing.expect(find(RFC8791_MODULE, "augment-structure") != null);
    try std.testing.expect(find("other", "structure") == null);
}
