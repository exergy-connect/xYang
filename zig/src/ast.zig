//! AST nodes for YANG statements (mirrors `src/xyang/ast.py`).
//!
//! Python models each statement as a dataclass in a small hierarchy
//! (`YangStatement` -> `YangStatementWithMust` / `YangStatementWithWhen` -> concrete class).
//! Here every statement is a `Statement` with the shared base fields and a tagged `data`
//! payload for the class-specific fields. `hasMust`, `hasWhen` and friends answer the
//! `isinstance` / `hasattr` questions the Python parser asks.
//!
//! XPath expressions (`must`, `when`, leafref `path`, `refine` targets) are kept as source
//! strings until the XPath phase adds a parser.

const std = @import("std");
const Module = @import("module.zig").Module;

pub const StringList = std.ArrayList([]const u8);

pub const IdentifierRef = struct {
    prefix: ?[]const u8 = null,
    name: []const u8,
};

pub const BitStmt = struct {
    name: []const u8,
    position: ?i64 = null,
    description: []const u8 = "",
    reference: []const u8 = "",
};

pub const PatternSpec = struct {
    pattern: []const u8,
    invert_match: bool = false,
    error_message: ?[]const u8 = null,
    error_app_tag: ?[]const u8 = null,
};

pub const TypeStmt = struct {
    name: []const u8,
    prefix: ?[]const u8 = null,
    units: []const u8 = "",
    patterns: std.ArrayList(PatternSpec) = .empty,
    length: ?[]const u8 = null,
    range: ?[]const u8 = null,
    length_error_message: ?[]const u8 = null,
    length_error_app_tag: ?[]const u8 = null,
    length_description: []const u8 = "",
    length_reference: []const u8 = "",
    range_error_message: ?[]const u8 = null,
    range_error_app_tag: ?[]const u8 = null,
    range_description: []const u8 = "",
    range_reference: []const u8 = "",
    fraction_digits: ?i64 = null,
    enums: StringList = .empty,
    bits: std.ArrayList(BitStmt) = .empty,
    types: std.ArrayList(*TypeStmt) = .empty,
    /// leafref `path` source text.
    path: ?[]const u8 = null,
    require_instance: bool = true,
    identityref_bases: std.ArrayList(IdentifierRef) = .empty,
    /// Module that wrote this `type` (RFC 7950 7.13, 9.9.2): its prefix and typedef name
    /// resolve there, also when a grouping or augment places the node in another module.
    scope: ?*Module = null,
};

pub const MustStmt = struct {
    expression: []const u8,
    description: []const u8 = "",
    reference: []const u8 = "",
    error_message: []const u8 = "",
};

pub const WhenStmt = struct {
    expression: []const u8,
    description: []const u8 = "",
    reference: []const u8 = "",
    /// RFC 7950 7.21.5: a `when` merged from `uses` or `augment` is evaluated with the
    /// parent of that statement as the context node.
    evaluate_with_parent_context: bool = false,
};

pub const Kind = enum {
    typedef,
    identity,
    container,
    notification,
    input,
    output,
    rpc,
    action,
    list,
    leaf,
    leaf_list,
    anydata,
    anyxml,
    extension,
    extension_invocation,
    grouping,
    uses,
    augment,
    deviation,
    refine,
    choice,
    case,
};

pub const Container = struct {
    presence: ?[]const u8 = null,
    /// Groupings declared in this container; visible here and in descendants only.
    groupings: std.StringArrayHashMapUnmanaged(*Statement) = .empty,
};

/// `min-elements` / `max-elements`: `null` is unset or `unbounded`, like Python's `None`.
pub const Bound = ?i64;

pub const Data = union(Kind) {
    typedef: struct {
        type: ?*TypeStmt = null,
        default: ?[]const u8 = null,
        /// Submodule the typedef was merged from by `include`.
        included_from: ?[]const u8 = null,
    },
    identity: struct { bases: std.ArrayList(IdentifierRef) = .empty },
    container: Container,
    notification: Container,
    input: Container,
    output: Container,
    rpc: void,
    action: void,
    list: struct {
        key: ?[]const u8 = null,
        min_elements: Bound = null,
        max_elements: Bound = null,
        unique: std.ArrayList([]const []const u8) = .empty,
    },
    leaf: struct { type: ?*TypeStmt = null, mandatory: bool = false, default: ?[]const u8 = null },
    leaf_list: struct {
        type: ?*TypeStmt = null,
        min_elements: Bound = null,
        max_elements: Bound = null,
        defaults: StringList = .empty,
    },
    anydata: struct { mandatory: bool = false },
    anyxml: struct { mandatory: bool = false },
    extension: struct {
        argument_name: []const u8 = "",
        argument_yin_element: ?bool = null,
        /// Name of the (sub)module whose body declares the extension; with the extension
        /// name it selects the apply callback in `ext/capabilities.zig`.
        module_name: []const u8 = "",
    },
    extension_invocation: struct {
        prefix: []const u8,
        argument: ?[]const u8 = null,
        /// Name of the module that defines the invoked extension.
        resolved_module: []const u8,
        resolved_extension: *Statement,
    },
    grouping: struct { typedef_names: StringList = .empty },
    uses: struct {
        grouping_name: []const u8 = "",
        grouping_prefix: ?[]const u8 = null,
        refines: std.ArrayList(*Statement) = .empty,
        augmentations: std.ArrayList(*Statement) = .empty,
    },
    augment: struct { augment_path: []const u8 = "", augment_path_segments: std.ArrayList(IdentifierRef) = .empty },
    deviation: struct {
        target_path: []const u8 = "",
        target_path_segments: std.ArrayList(IdentifierRef) = .empty,
        not_supported: bool = false,
    },
    refine: struct {
        target_path: []const u8 = "",
        type: ?*TypeStmt = null,
        min_elements: Bound = null,
        max_elements: Bound = null,
        refined_defaults: StringList = .empty,
        refined_mandatory: ?bool = null,
        refined_config: ?bool = null,
    },
    choice: struct { mandatory: bool = false, default: ?[]const u8 = null, cases: std.ArrayList(*Statement) = .empty },
    case: void,
};

pub const Statement = struct {
    name: []const u8 = "",
    description: []const u8 = "",
    reference: []const u8 = "",
    units: []const u8 = "",
    statements: std.ArrayList(*Statement) = .empty,
    /// `YangStatementWithMust`.
    must_statements: std.ArrayList(*MustStmt) = .empty,
    /// `YangStatementWithWhen`.
    when: ?*WhenStmt = null,
    if_features: StringList = .empty,
    config: ?bool = null,
    /// RFC 7951: module that defined this node when it differs from the enclosing parent
    /// (merged from a foreign `augment`); null means the parent's module.
    defining_module: ?[]const u8 = null,
    data: Data,

    pub fn kind(self: *const Statement) Kind {
        return std.meta.activeTag(self.data);
    }

    /// `isinstance(stmt, YangStatementWithMust)`.
    pub fn hasMust(self: *const Statement) bool {
        return switch (self.kind()) {
            .container, .notification, .input, .output, .rpc, .action, .list, .leaf, .leaf_list, .anydata, .anyxml, .extension_invocation, .refine => true,
            else => false,
        };
    }

    /// `isinstance(stmt, YangStatementWithWhen)`.
    pub fn hasWhen(self: *const Statement) bool {
        return switch (self.kind()) {
            .container, .notification, .input, .output, .rpc, .action, .list, .leaf, .leaf_list, .anydata, .anyxml, .extension_invocation, .uses, .augment, .choice, .case => true,
            else => false,
        };
    }

    /// `hasattr(stmt, "if_features")`: `YangStatementWithWhen`, identity and refine.
    pub fn hasIfFeatures(self: *const Statement) bool {
        return self.hasWhen() or self.kind() == .identity or self.kind() == .refine;
    }

    /// The `type` slot of typedef, leaf, leaf-list and refine (`hasattr(parent, "type")`).
    pub fn typeSlot(self: *Statement) ?*?*TypeStmt {
        return switch (self.data) {
            .typedef => |*d| &d.type,
            .leaf => |*d| &d.type,
            .leaf_list => |*d| &d.type,
            .refine => |*d| &d.type,
            else => null,
        };
    }

    pub fn minElementsSlot(self: *Statement) ?*Bound {
        return switch (self.data) {
            .list => |*d| &d.min_elements,
            .leaf_list => |*d| &d.min_elements,
            .refine => |*d| &d.min_elements,
            else => null,
        };
    }

    pub fn maxElementsSlot(self: *Statement) ?*Bound {
        return switch (self.data) {
            .list => |*d| &d.max_elements,
            .leaf_list => |*d| &d.max_elements,
            .refine => |*d| &d.max_elements,
            else => null,
        };
    }

    /// `get_schema_node()`: the path segment this statement adds, or null.
    pub fn schemaNode(self: *const Statement) ?[]const u8 {
        if (!self.hasWhen()) return null;
        return switch (self.kind()) {
            .uses, .augment, .extension_invocation => null,
            else => if (self.name.len == 0) null else self.name,
        };
    }
};
