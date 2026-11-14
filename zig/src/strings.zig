const std = @import("std");

/// Byte-wise ascending, like Python's `sorted()` on `str`.
pub fn lessThan(_: void, a: []const u8, b: []const u8) bool {
    return std.mem.order(u8, a, b) == .lt;
}

pub fn sortStrings(items: [][]const u8) void {
    std.mem.sort([]const u8, items, {}, lessThan);
}

test "sortStrings" {
    var items = [_][]const u8{ "b", "ab", "a", "B" };
    sortStrings(&items);
    try std.testing.expectEqualDeep(&[_][]const u8{ "B", "a", "ab", "b" }, &items);
}
