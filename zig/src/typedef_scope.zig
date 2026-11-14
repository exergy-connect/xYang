//! Scope checks on the global typedef table; references resolve on demand.
const std = @import("std");
const ast = @import("ast.zig");
const Module = @import("module.zig").Module;
const errors = @import("errors.zig");

pub fn inScope(restriction: ?[]const u8, context: []const u8) bool {
    const scope = restriction orelse return true;
    return std.mem.eql(u8, scope, context) or
        (std.mem.startsWith(u8, context, scope) and context.len > scope.len and context[scope.len] == '/');
}

pub fn path(a: std.mem.Allocator, context: []const u8, stmt: *const ast.Statement) error{OutOfMemory}![]const u8 {
    const name = switch (stmt.kind()) {
        .container, .list, .rpc, .action, .notification => stmt.name,
        .grouping => try std.fmt.allocPrint(a, "@grouping:{s}", .{stmt.name}),
        .input => "input",
        .output => "output",
        else => return context,
    };
    const escaped = try pointerEscape(a, name);
    return std.fmt.allocPrint(a, "{s}/{s}", .{ context, escaped });
}

pub fn pointerEscape(a: std.mem.Allocator, name: []const u8) error{OutOfMemory}![]const u8 {
    var out: std.ArrayList(u8) = .empty;
    for (name) |c| switch (c) {
        '~' => try out.appendSlice(a, "~0"),
        '/' => try out.appendSlice(a, "~1"),
        else => try out.append(a, c),
    };
    return out.toOwnedSlice(a);
}

pub fn register(r: *errors.Reporter, module: *Module, td: *ast.Statement) errors.Error!void {
    for (module.typedefs.values()) |previous| {
        if (previous == td) return;
        if (std.mem.eql(u8, previous.name, td.name) and
            (inScope(previous.data.typedef.scope, td.data.typedef.scope orelse "") or
                inScope(td.data.typedef.scope, previous.data.typedef.scope orelse "")))
            return r.fail(.semantic, "Duplicate typedef '{s}' in lexical scope", .{td.name});
    }
    if (@import("types/registry.zig").get(td.name) != null)
        return r.fail(.semantic, "Duplicate typedef '{s}': built-in type", .{td.name});
    const key = if (td.data.typedef.scope) |scope| try std.fmt.allocPrint(r.arena, "{s}/{s}", .{ scope, td.name }) else td.name;
    try module.typedefs.put(r.arena, key, td);
}

pub fn valid(value: []const u8) bool {
    if (value.len == 0 or value[0] != '/' or value[value.len - 1] == '/' or std.mem.indexOf(u8, value, "//") != null) return false;
    for (value, 0..) |c, i| if (c == '~' and (i + 1 == value.len or (value[i + 1] != '0' and value[i + 1] != '1'))) return false;
    return true;
}

pub fn defsUri(a: std.mem.Allocator, key: []const u8) error{OutOfMemory}![]const u8 {
    const escaped = try pointerEscape(a, key);
    var out: std.ArrayList(u8) = .empty;
    try out.appendSlice(a, "#/$defs/");
    const hex = "0123456789ABCDEF";
    for (escaped) |c| {
        if (std.ascii.isAlphanumeric(c) or c == '-' or c == '_' or c == '.' or c == '~') {
            try out.append(a, c);
        } else {
            try out.appendSlice(a, &.{ '%', hex[c >> 4], hex[c & 15] });
        }
    }
    return out.toOwnedSlice(a);
}
