//! `xyang-zig`: command-line entry point. Commands live in `cli/commands.zig`.

const std = @import("std");
const commands = @import("cli/commands.zig");

pub fn main(init: std.process.Init) !void {
    const arena = init.arena.allocator();
    const argv = try init.minimal.args.toSlice(arena);
    const args = try arena.alloc([]const u8, argv.len);
    for (argv, 0..) |a, i| args[i] = a;

    var out_buf: [4096]u8 = undefined;
    var err_buf: [4096]u8 = undefined;
    var out: std.Io.File.Writer = .init(.stdout(), init.io, &out_buf);
    var err: std.Io.File.Writer = .init(.stderr(), init.io, &err_buf);
    const ctx: commands.Io = .{ .io = init.io, .arena = arena, .out = &out.interface, .err = &err.interface };

    const code = try run(ctx, if (args.len > 0) args[1..] else args);
    try out.interface.flush();
    try err.interface.flush();
    std.process.exit(code);
}

fn run(ctx: commands.Io, args: []const []const u8) !u8 {
    return commands.runTop(ctx, args);
}
