//! Lazy display paths and JSON Pointers for the document walk.
const std = @import("std");
const instance = @import("../encoding/instance.zig");
const jv = @import("../json_value.zig");
const Allocator = std.mem.Allocator;

pub const PathBuilder = struct {
    a: Allocator,
    frames: std.ArrayList(Frame) = .empty,
    const Frame = struct {
        name: []const u8,
        key: ?[]const u8 = null,
        entry: ?*const jv.Object = null,
        key_names: []const []const u8 = &.{},
        index: ?usize = null,
        pointer_name: ?[]const u8 = null,
    };
    pub fn push(self: *PathBuilder, name: []const u8, key: ?[]const u8, index: ?usize, pointer_name: ?[]const u8) error{OutOfMemory}!void {
        try self.frames.append(self.a, .{ .name = name, .key = key, .index = index, .pointer_name = pointer_name });
    }
    pub fn pushEntry(self: *PathBuilder, name: []const u8, entry: *const jv.Object, keys: []const []const u8, index: usize, pointer_name: []const u8) error{OutOfMemory}!void {
        try self.frames.append(self.a, .{ .name = name, .entry = entry, .key_names = keys, .index = index, .pointer_name = pointer_name });
    }
    pub fn pop(self: *PathBuilder) void {
        _ = self.frames.pop();
    }
    pub fn current(self: *const PathBuilder) error{OutOfMemory}![]const u8 {
        if (self.frames.items.len == 0) return "/";
        var parts: std.ArrayList([]const u8) = .empty;
        for (self.frames.items) |frame| {
            var key = frame.key;
            if (frame.entry) |entry| if (frame.key_names.len != 0) {
                var keys: std.ArrayList([]const u8) = .empty;
                for (frame.key_names) |k| try keys.append(self.a, try self.a.print("{s}='{f}'", .{ k, jv.pyStr(entry.get(k) orelse .null) }));
                key = try std.mem.join(self.a, ", ", keys.items);
            };
            try parts.append(self.a, if (key) |k| try self.a.print("{s}[{s}]", .{ frame.name, k }) else frame.name);
        }
        return self.a.print("/{s}", .{try std.mem.join(self.a, "/", parts.items)});
    }
    pub fn pointer(self: *const PathBuilder) error{OutOfMemory}![]const u8 {
        if (self.frames.items.len == 0) return "";
        var tokens: std.ArrayList([]const u8) = .empty;
        for (self.frames.items) |frame| {
            try tokens.append(self.a, try instance.pointerToken(self.a, frame.pointer_name orelse frame.name));
            if (frame.index) |i| try tokens.append(self.a, try self.a.print("{d}", .{i}));
        }
        return self.a.print("/{s}", .{try std.mem.join(self.a, "/", tokens.items)});
    }
    pub fn child(self: *const PathBuilder, name: []const u8) error{OutOfMemory}![]const u8 {
        return self.a.print("{s}/{s}", .{ std.mem.trimEnd(u8, try self.current(), "/"), name });
    }
    pub fn childPointer(self: *const PathBuilder, name: []const u8) error{OutOfMemory}![]const u8 {
        return self.a.print("{s}/{s}", .{ try self.pointer(), try instance.pointerToken(self.a, name) });
    }
};

test "display path and pointer" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var p: PathBuilder = .{ .a = arena.allocator() };
    try std.testing.expectEqualStrings("/", try p.current());
    try std.testing.expectEqualStrings("", try p.pointer());
    try p.push("top", null, null, "m:top");
    try p.push("items", "id='a'", 0, null);
    try std.testing.expectEqualStrings("/top/items[id='a']", try p.current());
    try std.testing.expectEqualStrings("/m:top/items/0", try p.pointer());
    try std.testing.expectEqualStrings("/m:top/items/0/a~1b", try p.childPointer("a/b"));
    p.pop();
    try std.testing.expectEqualStrings("/top/x", try p.child("x"));
}

test "list entry keys and escaped pointers are materialized lazily" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var entry: jv.Object = .empty;
    try entry.put(a, "id", .{ .string = "one" });
    try entry.put(a, "zone", .{ .string = "west" });
    var path: PathBuilder = .{ .a = a };
    try path.push("top", null, null, "m:top");
    try path.pushEntry("items", &entry, &.{ "id", "zone" }, 2, "items");
    try std.testing.expectEqualStrings("/top/items[id='one', zone='west']/a/b", try path.child("a/b"));
    try std.testing.expectEqualStrings("/m:top/items/2/a~1b", try path.childPointer("a/b"));
}
