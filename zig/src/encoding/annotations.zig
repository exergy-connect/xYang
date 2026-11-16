const std = @import("std");
const jv = @import("../json_value.zig");
const families = @import("annotation_families.zig");
pub const Options = struct { allow_jsonld: bool = true, allow_json_schema: bool = true };
pub fn isAnnotation(key: []const u8, options: Options) bool {
    if (key.len < 2) return false;
    const enabled = (key[0] == families.jsonld.prefix and options.allow_jsonld) or
        (key[0] == families.json_schema.prefix and options.allow_json_schema);
    if (!enabled) return false;
    for (key[1..]) |c| if (!std.ascii.isAlphabetic(c)) return false;
    return true;
}
pub fn isEmptyChoiceBranch(value: jv.Val) bool {
    if (value != .object) return false;
    const obj = value.object;
    const t = obj.get("type") orelse return false;
    if (t != .string or !std.mem.eql(u8, t.string, "object")) return false;
    if (obj.get("maxProperties")) |mp| if (jv.pyEql(mp, .{ .int = 0 })) return true;
    const extra = obj.get("additionalProperties") orelse return false;
    const props = obj.get("properties") orelse return false;
    return extra == .bool and !extra.bool and obj.contains("patternProperties") and props == .object and props.object.count() == 0;
}
fn newObject(a: std.mem.Allocator) !*jv.Object {
    const obj = try a.create(jv.Object);
    obj.* = .empty;
    return obj;
}
pub fn annotateSchema(a: std.mem.Allocator, value: jv.Val, options: Options) error{OutOfMemory}!void {
    if (value != .object or (!options.allow_jsonld and !options.allow_json_schema)) return;
    const obj = value.object;
    const t = obj.get("type");
    if ((t != null and t.? == .string and std.mem.eql(u8, t.?.string, "object")) or obj.contains("properties")) {
        if (obj.get("maxProperties")) |mp| if (jv.pyEql(mp, .{ .int = 0 })) {
            _ = obj.orderedRemove("maxProperties");
            try obj.put(a, "properties", .{ .object = try newObject(a) });
            try obj.put(a, "additionalProperties", .{ .bool = false });
        };
        const patterns = try newObject(a);
        if (options.allow_jsonld) try patterns.put(a, families.jsonld.pattern, .{ .bool = true });
        if (options.allow_json_schema) try patterns.put(a, families.json_schema.pattern, .{ .bool = true });
        try obj.put(a, "patternProperties", .{ .object = patterns });
    }
    for ([_][]const u8{ "properties", "$defs" }) |key| {
        if (obj.get(key)) |children| if (children == .object) {
            for (children.object.values()) |child| try annotateSchema(a, child, options);
        };
    }
    for ([_][]const u8{ "items", "not", "additionalProperties" }) |key| {
        if (obj.get(key)) |child| try annotateSchema(a, child, options);
    }
    for ([_][]const u8{ "oneOf", "anyOf", "allOf" }) |key| {
        if (obj.get(key)) |children| if (children == .array) {
            for (children.array) |child| try annotateSchema(a, child, options);
        };
    }
}
