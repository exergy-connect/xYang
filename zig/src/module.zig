//! A parsed YANG module or submodule (mirrors `YangModule` in `src/xyang/module.py`).

const std = @import("std");
const ast = @import("ast.zig");

pub const Revision = struct {
    date: []const u8,
    description: []const u8 = "",
    reference: []const u8 = "",
};

pub const Module = struct {
    name: []const u8 = "",
    yang_version: []const u8 = "1.1",
    namespace: []const u8 = "",
    prefix: []const u8 = "",
    organization: []const u8 = "",
    contact: []const u8 = "",
    description: []const u8 = "",
    reference: []const u8 = "",
    revisions: std.ArrayList(Revision) = .empty,
    belongs_to_module: []const u8 = "",
    typedefs: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    identities: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    groupings: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    features: std.StringArrayHashMapUnmanaged(void) = .empty,
    feature_if_features: std.StringArrayHashMapUnmanaged(ast.StringList) = .empty,
    /// Import prefix (local) -> loaded module (RFC 7950 `import`).
    import_prefixes: std.StringArrayHashMapUnmanaged(*Module) = .empty,
    extensions: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    statements: std.ArrayList(*ast.Statement) = .empty,
    /// RFC 8791 `sx:structure` invocations by name, registered when the extension is
    /// applied (Python's `extension_runtime["ietf-yang-structure-ext:structure-index"]`).
    structures: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    /// Removed foreign augments and their positions among retained root invocations.
    foreign_structure_augments: std.ArrayList(*ast.Statement) = .empty,
    foreign_structure_slots: std.ArrayList(usize) = .empty,
    /// Set when `belongs-to` was parsed (this is a submodule).
    is_submodule: bool = false,
    included_parent: ?*Module = null,
    /// Submodule that contributed an included feature or its if-feature list.
    feature_included_from: std.StringArrayHashMapUnmanaged([]const u8) = .empty,
    feature_if_included_from: std.StringArrayHashMapUnmanaged([]const u8) = .empty,
    /// Submodule names whose statements are already on this module.
    included_submodules: std.StringArrayHashMapUnmanaged(void) = .empty,

    /// `own_prefix_stripped()`.
    pub fn ownPrefix(self: *const Module) []const u8 {
        return std.mem.trim(u8, self.prefix, "'\"");
    }

    /// The module this tree belongs to. An included submodule resolves to its parent.
    pub fn definingModule(self: *Module) *Module {
        var scope = self;
        while (scope.included_parent) |parent| scope = parent;
        return scope;
    }

    /// `resolve_prefixed_module(prefix)`: this module for its own prefix, else the import.
    pub fn resolvePrefixedModule(self: *Module, prefix: []const u8) ?*Module {
        if (std.mem.eql(u8, prefix, self.ownPrefix())) return self;
        return self.import_prefixes.get(prefix);
    }

    /// `resolve_prefix_to_module_name(prefix)`: a submodule resolves to its parent module.
    pub fn resolvePrefixToModuleName(self: *Module, prefix: []const u8) ?[]const u8 {
        const target = self.resolvePrefixedModule(prefix) orelse return null;
        return if (target.belongs_to_module.len > 0) target.belongs_to_module else target.name;
    }

    /// `copy.copy(module)` with its own top-level statement list and import map, so one
    /// deviating build can edit it while the parser cache keeps the original.
    pub fn cowCopy(self: *const Module, arena: std.mem.Allocator) error{OutOfMemory}!*Module {
        const out = try arena.create(Module);
        out.* = self.*;
        out.statements = try self.statements.clone(arena);
        out.structures = try self.structures.clone(arena);
        out.foreign_structure_augments = try self.foreign_structure_augments.clone(arena);
        out.foreign_structure_slots = try self.foreign_structure_slots.clone(arena);
        out.import_prefixes = try self.import_prefixes.clone(arena);
        return out;
    }
};

/// `resolve_typedef(type_stmt, fallback)`: the typedef a derived `type` names, resolved in
/// the module that wrote the `type` (`scope`), else in `fallback`.
pub const ResolvedTypedef = struct { typedef: *ast.Statement, module: *Module };

pub fn resolveTypedef(type_stmt: *const ast.TypeStmt, fallback: ?*Module) ?ResolvedTypedef {
    var scope = type_stmt.scope orelse fallback orelse return null;
    scope = scope.definingModule();
    const target = if (type_stmt.prefix) |pre| scope.resolvePrefixedModule(pre) orelse return null else scope;
    const scopes = @import("typedef_scope.zig");
    const context = type_stmt.context orelse "";
    if (target.typedefs.get(type_stmt.name)) |td| {
        if (if (type_stmt.prefix != null) td.data.typedef.scope == null else scopes.inScope(td.data.typedef.scope, context))
            return .{ .typedef = td, .module = target };
        return null;
    }
    for (target.typedefs.values()) |td| {
        if (!std.mem.eql(u8, td.name, type_stmt.name)) continue;
        if (if (type_stmt.prefix != null) td.data.typedef.scope == null else scopes.inScope(td.data.typedef.scope, context))
            return .{ .typedef = td, .module = target };
    }
    return null;
}

test "prefixes resolve to the module and to imports" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var base: Module = .{ .name = "base", .prefix = "b" };
    var m: Module = .{ .name = "m", .prefix = "\"m\"" };
    try m.import_prefixes.put(a, "bb", &base);
    try std.testing.expect(m.resolvePrefixedModule("m").? == &m);
    try std.testing.expect(m.resolvePrefixedModule("bb").? == &base);
    try std.testing.expect(m.resolvePrefixedModule("b") == null);
    var sub: Module = .{ .name = "sub", .prefix = "s", .belongs_to_module = "m" };
    try m.import_prefixes.put(a, "s", &sub);
    try std.testing.expectEqualStrings("m", m.resolvePrefixToModuleName("s").?);
    const copy = try m.cowCopy(a);
    try copy.import_prefixes.put(a, "x", &base);
    try std.testing.expect(m.import_prefixes.get("x") == null);
}
