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
    extensions: std.StringArrayHashMapUnmanaged(*ast.Statement) = .empty,
    statements: std.ArrayList(*ast.Statement) = .empty,
    /// Set when `belongs-to` was parsed (this is a submodule).
    is_submodule: bool = false,

    /// `own_prefix_stripped()`.
    pub fn ownPrefix(self: *const Module) []const u8 {
        return std.mem.trim(u8, self.prefix, "'\"");
    }

    /// `resolve_prefixed_module(prefix)`. Imports are resolved from phase 2 on; until then
    /// an `import` statement fails the load before any prefixed reference is reached.
    pub fn resolvePrefixedModule(self: *const Module, prefix: []const u8) ?*const Module {
        if (std.mem.eql(u8, prefix, self.ownPrefix())) return self;
        return null;
    }
};
