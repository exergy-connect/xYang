//! JSON dump of a resolved module for comparing the effective schema tree with Python's
//! (`zig/tests/cross_check.py`). Not a public format.

const std = @import("std");
const ast = @import("ast.zig");
const Module = @import("module.zig").Module;

const Stringify = std.json.Stringify;
const Error = Stringify.Error;

pub fn writeModule(w: *std.Io.Writer, arena: std.mem.Allocator, m: *const Module) (Error || error{OutOfMemory})!void {
    var s: Stringify = .{ .writer = w };
    try s.beginObject();
    try s.objectField("name");
    try s.write(m.name);
    try sortedKeys(&s, arena, "typedefs", m.typedefs.keys());
    try sortedKeys(&s, arena, "identities", m.identities.keys());
    try sortedKeys(&s, arena, "groupings", m.groupings.keys());
    try sortedKeys(&s, arena, "features", m.features.keys());
    try s.objectField("imports");
    try s.beginObject();
    for (m.import_prefixes.keys(), m.import_prefixes.values()) |k, v| {
        try s.objectField(k);
        try s.write(v.name);
    }
    try s.endObject();
    try s.objectField("statements");
    try writeList(&s, m.statements.items);
    try s.endObject();
}

fn sortedKeys(s: *Stringify, arena: std.mem.Allocator, name: []const u8, keys: []const []const u8) (Error || error{OutOfMemory})!void {
    const sorted = try arena.dupe([]const u8, keys);
    std.mem.sort([]const u8, sorted, {}, struct {
        fn lt(_: void, a: []const u8, b: []const u8) bool {
            return std.mem.order(u8, a, b) == .lt;
        }
    }.lt);
    try s.objectField(name);
    try s.write(sorted);
}

fn writeList(s: *Stringify, items: []const *ast.Statement) Error!void {
    try s.beginArray();
    for (items) |child| try writeNode(s, child);
    try s.endArray();
}

fn field(s: *Stringify, name: []const u8, value: anytype) Error!void {
    try s.objectField(name);
    try s.write(value);
}

fn writeNode(s: *Stringify, n: *const ast.Statement) Error!void {
    try s.beginObject();
    try field(s, "kind", @tagName(n.kind()));
    try field(s, "name", n.name);
    try field(s, "description", n.description);
    try field(s, "units", n.units);
    try field(s, "config", n.config);
    try field(s, "if_features", n.if_features.items);
    try field(s, "when", if (n.when) |w| w.expression else null);
    try field(s, "when_parent", if (n.when) |w| w.evaluate_with_parent_context else false);
    try s.objectField("must");
    try s.beginArray();
    for (n.must_statements.items) |m| try s.write(m.expression);
    try s.endArray();
    try field(s, "defining_module", n.defining_module);
    var type_name: ?[]const u8 = null;
    var mandatory: ?bool = null;
    var default: ?[]const u8 = null;
    var defaults: ?[]const []const u8 = null;
    var key: ?[]const u8 = null;
    var min: ?i64 = null;
    var max: ?i64 = null;
    switch (n.data) {
        .leaf => |d| {
            type_name = if (d.type) |t| t.name else null;
            mandatory = d.mandatory;
            default = d.default;
        },
        .leaf_list => |d| {
            type_name = if (d.type) |t| t.name else null;
            defaults = d.defaults.items;
            min = d.min_elements;
            max = d.max_elements;
        },
        .list => |d| {
            key = d.key;
            min = d.min_elements;
            max = d.max_elements;
        },
        .choice => |d| mandatory = d.mandatory,
        .anydata => |d| mandatory = d.mandatory,
        .anyxml => |d| mandatory = d.mandatory,
        else => {},
    }
    try field(s, "type", type_name);
    try field(s, "mandatory", mandatory);
    try field(s, "default", default);
    try field(s, "defaults", defaults);
    try field(s, "key", key);
    try field(s, "min", min);
    try field(s, "max", max);
    try s.objectField("children");
    try writeList(s, n.statements.items);
    try s.objectField("cases");
    if (n.kind() == .choice) try writeList(s, n.data.choice.cases.items) else try s.write(null);
    try s.endObject();
}
