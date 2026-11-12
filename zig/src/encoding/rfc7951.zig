//! RFC 7951 member names (mirrors `src/xyang/encoding/rfc7951.py`).
//!
//! A child defined in the parent's module is the bare identifier; a child another module
//! defines (a foreign `augment`) is `module-name:identifier`.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;

/// `defining_module_name`.
pub fn definingModuleName(stmt: *const Statement, parent_module: []const u8) []const u8 {
    if (stmt.defining_module) |m| if (m.len > 0) return m;
    return parent_module;
}

/// `member_keys_cached`: the one JSON member name of `stmt`, or null for an unnamed one.
pub const MemberKeys = struct {
    a: Allocator,
    parent_module: []const u8,
    cache: std.AutoHashMapUnmanaged(*const Statement, ?[]const u8) = .empty,

    pub fn key(self: *MemberKeys, stmt: *const Statement) error{OutOfMemory}!?[]const u8 {
        if (self.cache.get(stmt)) |k| return k;
        const k: ?[]const u8 = if (stmt.name.len == 0) null else blk: {
            const def = definingModuleName(stmt, self.parent_module);
            if (std.mem.eql(u8, def, self.parent_module)) break :blk stmt.name;
            break :blk try std.fmt.allocPrint(self.a, "{s}:{s}", .{ def, stmt.name });
        };
        try self.cache.put(self.a, stmt, k);
        return k;
    }

    /// `instance_member_present`.
    pub fn present(self: *MemberKeys, data: *const jv.Object, stmt: *const Statement) error{OutOfMemory}!bool {
        const k = (try self.key(stmt)) orelse return false;
        return data.contains(k);
    }

    pub const Lookup = struct { value: jv.Val, json_key: ?[]const u8 };

    /// `instance_member_lookup`: the value and the member name as found, or no key.
    pub fn lookup(self: *MemberKeys, data: *const jv.Object, stmt: *const Statement) error{OutOfMemory}!Lookup {
        const k = (try self.key(stmt)) orelse return .{ .value = .null, .json_key = null };
        if (data.get(k)) |v| return .{ .value = v, .json_key = k };
        return .{ .value = .null, .json_key = null };
    }
};
