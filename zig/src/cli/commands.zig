//! CLI command registry (mirrors the subcommands of `xyang` in `src/xyang/__main__.py`).
//!
//! Each command owns its usage line, help text and handler. `main.zig` dispatches by name
//! through `COMMANDS`; adding a command means adding one entry here.

const std = @import("std");
const xyang = @import("xyang");

pub const PROG = "xyang-zig";

pub const Io = struct {
    io: std.Io,
    arena: std.mem.Allocator,
    out: *std.Io.Writer,
    err: *std.Io.Writer,
};

pub const Command = struct {
    name: []const u8,
    summary: []const u8,
    usage: []const u8,
    help: []const u8,
    run: *const fn (ctx: Io, args: []const []const u8) anyerror!u8,
};

pub const COMMANDS = [_]Command{
    .{
        .name = "parse",
        .summary = "Parse a YANG file and print module info",
        .usage = "usage: " ++ PROG ++ " parse [-h] [--include-path DIR] yang_file\n",
        .help =
        \\
        \\Parse a YANG file and print module name, yang-version, namespace, prefix,
        \\organization (if set), typedef count, and top-level statement count.
        \\
        \\positional arguments:
        \\  yang_file           Path to .yang file
        \\
        \\options:
        \\  -h, --help          show this help message and exit
        \\  --include-path DIR  Directory to search for imported modules (repeatable; searched
        \\                      after the main file's directory). Default: none
        \\
        \\examples:
        \\  xyang-zig parse --help
        \\  xyang-zig parse -h
        \\  xyang-zig parse module.yang
        \\  xyang-zig parse --include-path ./modules module.yang
        \\
        ,
        .run = runParse,
    },
};

pub fn find(name: []const u8) ?*const Command {
    for (&COMMANDS) |*c| {
        if (std.mem.eql(u8, c.name, name)) return c;
    }
    return null;
}

/// `{parse,validate}` for the usage line.
pub const CHOICES = blk: {
    var s: []const u8 = "{";
    for (COMMANDS, 0..) |c, i| {
        s = s ++ (if (i == 0) "" else ",") ++ c.name;
    }
    break :blk s ++ "}";
};

pub const MAIN_USAGE = "usage: " ++ PROG ++ " [-h] " ++ CHOICES ++ " ...\n";

pub const MAIN_HELP = blk: {
    var width: usize = CHOICES.len;
    for (COMMANDS) |c| width = @max(width, c.name.len + 2);
    var s: []const u8 = MAIN_USAGE ++
        "\nxYang (Zig): Parse YANG modules, validate RFC 7951 JSON instance data, and export JSON Schema\n" ++
        "\npositional arguments:\n  " ++ pad(CHOICES, width) ++ "  Commands\n";
    for (COMMANDS) |c| s = s ++ "    " ++ pad(c.name, width - 2) ++ "  " ++ c.summary ++ "\n";
    s = s ++ "\noptions:\n  " ++ pad("-h, --help", width) ++ "  show this help message and exit\n" ++
        "\nexamples:\n  " ++ PROG ++ " --help\n  " ++ PROG ++ " -h\n";
    for (COMMANDS) |c| s = s ++ "  " ++ PROG ++ " " ++ c.name ++ " module.yang\n";
    break :blk s;
};

fn pad(comptime s: []const u8, comptime width: usize) []const u8 {
    var out: []const u8 = s;
    if (width > s.len) {
        for (s.len..width) |_| out = out ++ " ";
    }
    return out;
}

/// argparse-style usage error: usage line, `prog: error: message`, exit 2.
pub fn usageError(ctx: Io, usage: []const u8, prog: []const u8, comptime fmt: []const u8, args: anytype) !u8 {
    try ctx.err.writeAll(usage);
    try ctx.err.print("{s}: error: " ++ fmt ++ "\n", .{prog} ++ args);
    return 2;
}

fn runParse(ctx: Io, args: []const []const u8) anyerror!u8 {
    const cmd = find("parse").?;
    var yang_file: ?[]const u8 = null;
    var include_path: std.ArrayList([]const u8) = .empty;
    var extras: std.ArrayList([]const u8) = .empty;
    var only_positional = false;
    var i: usize = 0;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (!only_positional and std.mem.eql(u8, a, "--")) {
            only_positional = true;
            continue;
        }
        if (!only_positional and a.len > 1 and a[0] == '-') {
            if (std.mem.eql(u8, a, "-h") or isLongPrefix(a, "--help")) {
                try ctx.out.writeAll(cmd.usage);
                try ctx.out.writeAll(cmd.help);
                return 0;
            }
            const eq = std.mem.indexOfScalar(u8, a, '=');
            const flag = if (eq) |e| a[0..e] else a;
            if (isLongPrefix(flag, "--include-path")) {
                if (eq) |e| {
                    try include_path.append(ctx.arena, a[e + 1 ..]);
                } else if (i + 1 < args.len and !(args[i + 1].len > 1 and args[i + 1][0] == '-')) {
                    i += 1;
                    try include_path.append(ctx.arena, args[i]);
                } else {
                    return usageError(ctx, cmd.usage, PROG ++ " parse", "argument --include-path: expected one argument", .{});
                }
                continue;
            }
            try extras.append(ctx.arena, a);
            continue;
        }
        if (yang_file == null) {
            yang_file = a;
        } else {
            try extras.append(ctx.arena, a);
        }
    }
    const path = yang_file orelse
        return usageError(ctx, cmd.usage, PROG ++ " parse", "the following arguments are required: yang_file", .{});
    if (extras.items.len > 0) {
        const joined = try std.mem.join(ctx.arena, " ", extras.items);
        return usageError(ctx, MAIN_USAGE, PROG, "unrecognized arguments: {s}", .{joined});
    }

    std.Io.Dir.cwd().access(ctx.io, path, .{}) catch {
        try ctx.err.print("Error: file not found: {s}\n", .{path});
        return 1;
    };
    var diag: xyang.Diagnostic = .{};
    const module = xyang.parseFile(ctx.arena, ctx.io, path, &diag) catch |err| switch (err) {
        error.YangLoad => {
            try ctx.err.print("Error: {f}\n", .{diag});
            return 1;
        },
        else => return err,
    };
    try ctx.out.print("Module: {s}\n", .{module.name});
    try ctx.out.print("  yang-version: {s}\n", .{module.yang_version});
    try ctx.out.print("  namespace: {s}\n", .{module.namespace});
    try ctx.out.print("  prefix: {s}\n", .{module.prefix});
    if (module.organization.len > 0) try ctx.out.print("  organization: {s}\n", .{module.organization});
    try ctx.out.print("  typedefs: {d}\n", .{module.typedefs.count()});
    try ctx.out.print("  top-level statements: {d}\n", .{module.statements.items.len});
    return 0;
}

/// argparse accepts an unambiguous prefix of a long option (`--inc` for `--include-path`).
fn isLongPrefix(arg: []const u8, option: []const u8) bool {
    return arg.len > 2 and std.mem.startsWith(u8, option, arg);
}
