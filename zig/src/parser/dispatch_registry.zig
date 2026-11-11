//! Parent statement -> allowed substatements (mirrors `src/xyang/parser/dispatch_registry.py`).
//!
//! One frozen table. `statement_parsers` builds the keyword -> handler maps from it at
//! comptime. The sets are the keywords Python accepts, including known RFC drift. Keep the
//! parent order identical to Python's `_PARENTS`; the conformance runner can print a
//! parity snapshot that `zig/tests/cross_check.py` compares against Python.

const std = @import("std");
const kw = @import("keywords.zig");

pub const METADATA_SUBSTATEMENTS = [_][]const u8{ kw.DESCRIPTION, kw.REFERENCE, kw.UNITS, kw.STATUS };
pub const DATA_NODE_SUBSTATEMENTS = METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.CONFIG, kw.TYPEDEF };
pub const DATA_DEF_SUBSTATEMENTS = [_][]const u8{
    kw.LEAF, kw.LEAF_LIST, kw.CONTAINER, kw.LIST, kw.CHOICE, kw.ANYDATA, kw.ANYXML, kw.USES,
};

pub const ParentId = enum {
    module,
    submodule,
    belongs_to,
    import,
    include,
    typedef,
    type,
    pattern,
    @"enum",
    bit,
    identity,
    leaf,
    leaf_list,
    list,
    container,
    grouping,
    notification,
    rpc,
    action,
    input,
    output,
    choice,
    case,
    augment,
    uses,
    refine,
    anydata,
    anyxml,
    must,
    when,
    feature,
    if_feature,
    extension,
    argument,
    deviation,
    revision,
    extension_invocation,
    length,
    range,
};

/// RFC 7950 section (or 6.3.1 for an extension invocation) and allowed keywords.
pub const DispatchParent = struct {
    id: ParentId,
    name: []const u8,
    rfc: []const u8,
    keywords: []const []const u8,

    pub fn allows(self: DispatchParent, keyword: []const u8) bool {
        for (self.keywords) |k| {
            if (std.mem.eql(u8, k, keyword)) return true;
        }
        return false;
    }
};

fn dedupe(comptime parts: []const []const u8) []const []const u8 {
    comptime {
        var out: [parts.len][]const u8 = undefined;
        var n: usize = 0;
        outer: for (parts) |p| {
            for (out[0..n]) |q| {
                if (std.mem.eql(u8, p, q)) continue :outer;
            }
            out[n] = p;
            n += 1;
        }
        const final = out[0..n].*;
        return &final;
    }
}

fn parent(comptime id: ParentId, comptime name: []const u8, comptime rfc: []const u8, comptime keywords: []const []const u8) DispatchParent {
    @setEvalBranchQuota(100_000);
    return .{ .id = id, .name = name, .rfc = rfc, .keywords = comptime dedupe(keywords) };
}

const IO_KEYWORDS = METADATA_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{ kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE };

pub const PARENTS = [_]DispatchParent{
    parent(.module, "module", "7.1.1", &.{
        kw.LEAF,     kw.LIST,        kw.LEAF_LIST,    kw.CONTAINER, kw.NOTIFICATION, kw.RPC,
        kw.ANYDATA,  kw.ANYXML,      kw.TYPEDEF,      kw.GROUPING,  kw.IMPORT,       kw.INCLUDE,
        kw.REVISION, kw.DESCRIPTION, kw.REFERENCE,    kw.FEATURE,   kw.IDENTITY,     kw.EXTENSION,
        kw.AUGMENT,  kw.DEVIATION,   kw.YANG_VERSION, kw.NAMESPACE, kw.PREFIX,       kw.ORGANIZATION,
        kw.CONTACT,
    }),
    parent(.submodule, "submodule", "7.2.1", &.{
        kw.YANG_VERSION, kw.ORGANIZATION, kw.CONTACT,   kw.DESCRIPTION,  kw.REFERENCE, kw.IMPORT,
        kw.INCLUDE,      kw.REVISION,     kw.FEATURE,   kw.EXTENSION,    kw.TYPEDEF,   kw.IDENTITY,
        kw.GROUPING,     kw.AUGMENT,      kw.DEVIATION, kw.CONTAINER,    kw.LIST,      kw.LEAF,
        kw.LEAF_LIST,    kw.ANYDATA,      kw.ANYXML,    kw.NOTIFICATION,
    }),
    parent(.belongs_to, "belongs-to", "7.2.2", &.{kw.PREFIX}),
    parent(.import, "import", "7.1.5", &.{ kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION }),
    parent(.include, "include", "7.1.6", &.{ kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION }),
    parent(.typedef, "typedef", "7.3.1", &(METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.TYPE, kw.DEFAULT })),
    parent(.type, "type", "7.4.1", &.{
        kw.TYPE,             kw.PATTERN, kw.LENGTH, kw.RANGE,       kw.FRACTION_DIGITS, kw.ENUM, kw.BIT, kw.PATH,
        kw.REQUIRE_INSTANCE, kw.BASE,    kw.UNITS,  kw.DESCRIPTION, kw.REFERENCE,
    }),
    parent(.pattern, "pattern", "9.4.5", &.{ kw.DESCRIPTION, kw.REFERENCE, kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.MODIFIER }),
    parent(.@"enum", "enum", "9.6.4", &.{ kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE, kw.VALUE, kw.STATUS }),
    parent(.bit, "bit", "9.7.4", &.{ kw.POSITION, kw.DESCRIPTION, kw.REFERENCE }),
    parent(.identity, "identity", "7.18.1", &(METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.BASE, kw.IF_FEATURE })),
    parent(.leaf, "leaf", "7.6.2", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{ kw.TYPE, kw.MANDATORY, kw.DEFAULT, kw.MUST, kw.WHEN, kw.IF_FEATURE })),
    parent(.leaf_list, "leaf-list", "7.7.3", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{
        kw.TYPE, kw.MIN_ELEMENTS, kw.MAX_ELEMENTS, kw.ORDERED_BY, kw.WHEN, kw.MUST, kw.IF_FEATURE,
    })),
    parent(.list, "list", "7.8.1", &(DATA_NODE_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{
        kw.KEY,        kw.UNIQUE,       kw.MIN_ELEMENTS, kw.MAX_ELEMENTS, kw.ORDERED_BY, kw.WHEN, kw.MUST,
        kw.IF_FEATURE, kw.NOTIFICATION, kw.ACTION,
    })),
    parent(.container, "container", "7.5.2", &(DATA_NODE_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{
        kw.PRESENCE, kw.WHEN, kw.MUST, kw.GROUPING, kw.IF_FEATURE, kw.NOTIFICATION, kw.ACTION,
    })),
    parent(.grouping, "grouping", "7.12.1", &(METADATA_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{
        kw.TYPEDEF, kw.GROUPING, kw.IF_FEATURE, kw.WHEN, kw.MUST, kw.NOTIFICATION, kw.ACTION,
    })),
    parent(.notification, "notification", "7.16.1", &(METADATA_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{
        kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE,
    })),
    parent(.rpc, "rpc", "7.14.1", &(METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.MUST, kw.INPUT, kw.OUTPUT, kw.IF_FEATURE })),
    parent(.action, "action", "7.15.1", &(METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.INPUT, kw.OUTPUT, kw.IF_FEATURE })),
    parent(.input, "input", "7.14.2", &IO_KEYWORDS),
    parent(.output, "output", "7.14.3", &IO_KEYWORDS),
    parent(.choice, "choice", "7.9.1", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.IF_FEATURE, kw.CASE, kw.MANDATORY, kw.DEFAULT })),
    parent(.case, "case", "7.9.2", &(DATA_NODE_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.IF_FEATURE })),
    parent(.augment, "augment", "7.17.1", &(DATA_NODE_SUBSTATEMENTS ++ DATA_DEF_SUBSTATEMENTS ++ [_][]const u8{
        kw.IF_FEATURE, kw.CASE, kw.WHEN, kw.MUST, kw.NOTIFICATION, kw.ACTION,
    })),
    parent(.uses, "uses", "7.13.1", &(METADATA_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.IF_FEATURE, kw.REFINE, kw.AUGMENT })),
    parent(.refine, "refine", "7.13.2", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{
        kw.MUST, kw.MIN_ELEMENTS, kw.MAX_ELEMENTS, kw.ORDERED_BY, kw.MANDATORY, kw.DEFAULT, kw.IF_FEATURE, kw.TYPE,
    })),
    parent(.anydata, "anydata", "7.10.1", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY })),
    parent(.anyxml, "anyxml", "7.11.1", &(DATA_NODE_SUBSTATEMENTS ++ [_][]const u8{ kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY })),
    parent(.must, "must", "7.5.4", &.{ kw.ERROR_MESSAGE, kw.DESCRIPTION, kw.REFERENCE }),
    parent(.when, "when", "7.21.5", &.{ kw.DESCRIPTION, kw.REFERENCE }),
    parent(.feature, "feature", "7.20.1", &.{ kw.DESCRIPTION, kw.IF_FEATURE, kw.REFERENCE }),
    parent(.if_feature, "if-feature", "7.20.2", &.{ kw.DESCRIPTION, kw.REFERENCE }),
    parent(.extension, "extension", "7.19.1", &.{ kw.ARGUMENT, kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE }),
    parent(.argument, "argument", "7.19.2", &.{kw.YIN_ELEMENT}),
    parent(.deviation, "deviation", "7.20.3", &.{ kw.DESCRIPTION, kw.REFERENCE, kw.DEVIATE }),
    parent(.revision, "revision", "7.1.9", &.{ kw.DESCRIPTION, kw.REFERENCE }),
    parent(.extension_invocation, "extension-invocation", "6.3.1", &.{
        kw.IF_FEATURE, kw.WHEN,      kw.MUST, kw.DESCRIPTION, kw.REFERENCE, kw.TYPE,    kw.USES,   kw.LEAF,
        kw.LEAF_LIST,  kw.CONTAINER, kw.LIST, kw.CHOICE,      kw.CASE,      kw.ANYDATA, kw.ANYXML,
    }),
    parent(.length, "length", "9.4.4", &.{ kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.DESCRIPTION, kw.REFERENCE }),
    parent(.range, "range", "9.2.4", &.{ kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.DESCRIPTION, kw.REFERENCE }),
};

comptime {
    // Every ParentId has exactly one entry, stored at its enum index.
    for (PARENTS, 0..) |p, i| {
        if (@backingInt(p.id) != i) @compileError("dispatch registry order must follow ParentId: " ++ p.name);
    }
    if (PARENTS.len != @typeInfo(ParentId).@"enum".field_names.len) @compileError("dispatch registry is missing a parent");
}

pub fn get(id: ParentId) DispatchParent {
    return PARENTS[@backingInt(id)];
}

/// `{parent: {rfc, keywords}}` with sorted keywords, the same shape as Python's
/// `dispatch_registry_parity_snapshot()`.
pub fn writeParitySnapshot(w: *std.Io.Writer, gpa: std.mem.Allocator) !void {
    try w.writeAll("{");
    for (PARENTS, 0..) |p, i| {
        if (i != 0) try w.writeAll(", ");
        const sorted = try gpa.dupe([]const u8, p.keywords);
        defer gpa.free(sorted);
        std.mem.sort([]const u8, sorted, {}, struct {
            fn lt(_: void, a: []const u8, b: []const u8) bool {
                return std.mem.order(u8, a, b) == .lt;
            }
        }.lt);
        try w.print("\"{s}\": {{\"rfc\": \"{s}\", \"keywords\": [", .{ p.name, p.rfc });
        for (sorted, 0..) |k, j| {
            if (j != 0) try w.writeAll(", ");
            try w.print("\"{s}\"", .{k});
        }
        try w.writeAll("]}");
    }
    try w.writeAll("}\n");
}

test "registry parents are indexed by id" {
    try std.testing.expect(get(.leaf).allows(kw.TYPE));
    try std.testing.expect(!get(.case).allows(kw.MANDATORY));
    try std.testing.expectEqualStrings("leaf-list", get(.leaf_list).name);
}
