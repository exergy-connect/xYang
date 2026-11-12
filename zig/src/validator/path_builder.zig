//! Display path and JSON Pointer of the walker's current node (mirrors
//! `src/xyang/validator/path_builder.py`). List entries display as key predicates
//! (`/data-model/entities[name='foo']`); the pointer uses entry positions (`/entities/0`).

const std = @import("std");
const instance = @import("../encoding/instance.zig");

const Allocator = std.mem.Allocator;

pub const PathBuilder = struct {
    a: Allocator,
    segments: std.ArrayList([]const u8) = .empty,
    tokens: std.ArrayList([]const u8) = .empty,
    widths: std.ArrayList(u8) = .empty,

    pub fn push(self: *PathBuilder, name: []const u8, key: ?[]const u8, index: ?usize, pointer_name: ?[]const u8) error{OutOfMemory}!void {
        try self.segments.append(self.a, if (key) |k| try std.fmt.allocPrint(self.a, "{s}[{s}]", .{ name, k }) else name);
        try self.tokens.append(self.a, try instance.pointerToken(self.a, pointer_name orelse name));
        if (index) |i| {
            try self.tokens.append(self.a, try std.fmt.allocPrint(self.a, "{d}", .{i}));
            try self.widths.append(self.a, 2);
        } else {
            try self.widths.append(self.a, 1);
        }
    }

    pub fn pop(self: *PathBuilder) void {
        _ = self.segments.pop();
        const width = self.widths.pop().?;
        self.tokens.shrinkRetainingCapacity(self.tokens.items.len - width);
    }

    pub fn current(self: *const PathBuilder) error{OutOfMemory}![]const u8 {
        if (self.segments.items.len == 0) return "/";
        return std.fmt.allocPrint(self.a, "/{s}", .{try std.mem.join(self.a, "/", self.segments.items)});
    }

    /// The document root is `""`.
    pub fn pointer(self: *const PathBuilder) error{OutOfMemory}![]const u8 {
        if (self.tokens.items.len == 0) return "";
        return std.fmt.allocPrint(self.a, "/{s}", .{try std.mem.join(self.a, "/", self.tokens.items)});
    }

    pub fn child(self: *const PathBuilder, name: []const u8) error{OutOfMemory}![]const u8 {
        const cur = try self.current();
        return std.fmt.allocPrint(self.a, "{s}/{s}", .{ std.mem.trimEnd(u8, cur, "/"), name });
    }

    pub fn childPointer(self: *const PathBuilder, name: []const u8) error{OutOfMemory}![]const u8 {
        return std.fmt.allocPrint(self.a, "{s}/{s}", .{ try self.pointer(), try instance.pointerToken(self.a, name) });
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
