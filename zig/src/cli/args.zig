//! Argument parsing for one subcommand, with the behavior and messages of Python's
//! `argparse` as `xyang` configures it (`src/xyang/__main__.py`).
//!
//! A command declares its options and positionals once (`commands.zig`); this parser
//! reads them: long options by exact name or unambiguous prefix, `--opt=value`, `--`,
//! `-h`/`--help`, choices, repeatable options, and positionals filled in order across
//! options (Python 3.13 argparse, the version the cross-check runs); extra positionals
//! are unrecognized.

const std = @import("std");

pub const Opt = struct {
    long: []const u8,
    /// `-x` alias; argparse names the option `-x/--long` in messages.
    short: ?[]const u8 = null,
    /// Null for a flag (`store_true`).
    metavar: ?[]const u8 = null,
    choices: ?[]const []const u8 = null,
    /// `action="append"`.
    repeat: bool = false,
};

pub const Positional = struct {
    name: []const u8,
    /// `nargs="?"`.
    optional: bool = false,
};

pub const Spec = struct {
    prog: []const u8,
    usage: []const u8,
    help: []const u8,
    options: []const Opt,
    positionals: []const Positional,
};

pub const Parsed = struct {
    values: std.StringHashMapUnmanaged(std.ArrayList([]const u8)) = .empty,
    flags: std.StringHashMapUnmanaged(void) = .empty,
    positionals: std.StringHashMapUnmanaged([]const u8) = .empty,

    pub fn flag(self: *const Parsed, long: []const u8) bool {
        return self.flags.contains(long);
    }

    /// The last value of an option, or null.
    pub fn value(self: *const Parsed, long: []const u8) ?[]const u8 {
        const list = self.values.get(long) orelse return null;
        return if (list.items.len > 0) list.items[list.items.len - 1] else null;
    }

    pub fn all(self: *const Parsed, long: []const u8) []const []const u8 {
        const list = self.values.get(long) orelse return &.{};
        return list.items;
    }

    pub fn positional(self: *const Parsed, name: []const u8) ?[]const u8 {
        return self.positionals.get(name);
    }
};

pub const Outcome = union(enum) {
    parsed: Parsed,
    /// Help was printed; exit 0.
    help,
    /// A usage error: print `usage` (when set) and `prog: error: message`, exit 2.
    usage_error: struct { usage: []const u8, prog: []const u8, message: []const u8 },
};

/// argparse's name for the option in messages.
fn displayName(arena: std.mem.Allocator, o: *const Opt) ![]const u8 {
    const short = o.short orelse return o.long;
    return std.fmt.allocPrint(arena, "{s}/{s}", .{ short, o.long });
}

fn looksLikeOption(a: []const u8) bool {
    return a.len > 1 and a[0] == '-';
}

/// The option an argument names: exact match first, else the unique prefix.
fn match(spec: Spec, arena: std.mem.Allocator, arg: []const u8, flag_part: []const u8) !union(enum) { opt: *const Opt, help, none, ambiguous: []const u8 } {
    if (std.mem.eql(u8, flag_part, "--help")) return .help;
    for (spec.options) |*o| {
        if (std.mem.eql(u8, o.long, flag_part)) return .{ .opt = o };
        if (o.short) |short| if (std.mem.eql(u8, short, flag_part)) return .{ .opt = o };
    }
    if (flag_part.len <= 2 or !std.mem.startsWith(u8, flag_part, "--")) return .none;
    var names: std.ArrayList([]const u8) = .empty;
    var found: ?*const Opt = null;
    var help = false;
    if (std.mem.startsWith(u8, "--help", flag_part)) {
        try names.append(arena, "--help");
        help = true;
    }
    for (spec.options) |*o| {
        if (std.mem.startsWith(u8, o.long, flag_part)) {
            try names.append(arena, o.long);
            found = o;
        }
    }
    if (names.items.len > 1) return .{ .ambiguous = try std.fmt.allocPrint(arena, "ambiguous option: {s} could match {s}", .{ arg, try std.mem.join(arena, ", ", names.items) }) };
    if (help) return .help;
    if (found) |o| return .{ .opt = o };
    return .none;
}

/// Parse `args` (after the command name). `main_usage` / `main_prog` report the
/// unrecognized arguments, which argparse leaves to the top-level parser.
pub fn parse(arena: std.mem.Allocator, spec: Spec, args: []const []const u8, main_usage: []const u8, main_prog: []const u8, out: *std.Io.Writer) !Outcome {
    var p: Parsed = .{};
    var extras: std.ArrayList([]const u8) = .empty;
    var chunk: std.ArrayList([]const u8) = .empty;
    var filled: usize = 0;
    var only_positional = false;

    const usageError = struct {
        fn f(s: Spec, a: std.mem.Allocator, comptime fmt: []const u8, fargs: anytype) !Outcome {
            return .{ .usage_error = .{ .usage = s.usage, .prog = s.prog, .message = try std.fmt.allocPrint(a, fmt, fargs) } };
        }
    }.f;

    var i: usize = 0;
    while (i <= args.len) : (i += 1) {
        const at_end = i == args.len;
        const a = if (at_end) "" else args[i];
        const is_option = !at_end and !only_positional and looksLikeOption(a);
        const is_sep = !at_end and !only_positional and std.mem.eql(u8, a, "--");
        if (at_end or is_option or is_sep) {
            if (chunk.items.len > 0) {
                var k: usize = 0;
                while (k < chunk.items.len and filled < spec.positionals.len) : (k += 1) {
                    try p.positionals.put(arena, spec.positionals[filled].name, chunk.items[k]);
                    filled += 1;
                }
                try extras.appendSlice(arena, chunk.items[k..]);
                chunk.clearRetainingCapacity();
            }
        }
        if (at_end) break;
        if (is_sep) {
            only_positional = true;
            continue;
        }
        if (!is_option) {
            try chunk.append(arena, a);
            continue;
        }
        if (std.mem.eql(u8, a, "-h")) {
            try out.writeAll(spec.usage);
            try out.writeAll(spec.help);
            return .help;
        }
        var eq = std.mem.indexOfScalar(u8, a, '=');
        var flag_part = if (eq) |e| a[0..e] else a;
        var attached: ?[]const u8 = null;
        if (a.len > 2 and a[1] != '-') {
            for (spec.options) |o| if (o.short) |short| if (o.metavar != null and std.mem.eql(u8, short, a[0..2]) and !std.mem.eql(u8, a, short)) {
                if (!(eq != null and std.mem.eql(u8, a[0..eq.?], short))) {
                    flag_part = short;
                    attached = a[2..];
                    eq = null;
                }
            };
        }
        switch (try match(spec, arena, a, flag_part)) {
            .help => {
                try out.writeAll(spec.usage);
                try out.writeAll(spec.help);
                return .help;
            },
            .ambiguous => |msg| return .{ .usage_error = .{ .usage = spec.usage, .prog = spec.prog, .message = msg } },
            .none => try extras.append(arena, a),
            .opt => |o| {
                const name = try displayName(arena, o);
                if (o.metavar == null) {
                    if (eq) |e| return usageError(spec, arena, "argument {s}: ignored explicit argument '{s}'", .{ name, a[e + 1 ..] });
                    try p.flags.put(arena, o.long, {});
                    continue;
                }
                var v: []const u8 = undefined;
                if (attached) |rest| {
                    v = rest;
                } else if (eq) |e| {
                    v = a[e + 1 ..];
                } else if (i + 1 < args.len and !looksLikeOption(args[i + 1])) {
                    i += 1;
                    v = args[i];
                } else {
                    return usageError(spec, arena, "argument {s}: expected one argument", .{name});
                }
                if (o.choices) |choices| {
                    const ok = for (choices) |c| {
                        if (std.mem.eql(u8, c, v)) break true;
                    } else false;
                    if (!ok) {
                        var quoted: std.ArrayList([]const u8) = .empty;
                        for (choices) |c| try quoted.append(arena, try std.fmt.allocPrint(arena, "'{s}'", .{c}));
                        return usageError(spec, arena, "argument {s}: invalid choice: '{s}' (choose from {s})", .{ name, v, try std.mem.join(arena, ", ", quoted.items) });
                    }
                }
                const gop = try p.values.getOrPut(arena, o.long);
                if (!gop.found_existing) gop.value_ptr.* = .empty;
                if (!o.repeat) gop.value_ptr.clearRetainingCapacity();
                try gop.value_ptr.append(arena, v);
            },
        }
    }
    var missing: std.ArrayList([]const u8) = .empty;
    for (spec.positionals) |pos| {
        if (!pos.optional and !p.positionals.contains(pos.name)) try missing.append(arena, pos.name);
    }
    if (missing.items.len > 0) return usageError(spec, arena, "the following arguments are required: {s}", .{try std.mem.join(arena, ", ", missing.items)});
    if (extras.items.len > 0) {
        return .{ .usage_error = .{ .usage = main_usage, .prog = main_prog, .message = try std.fmt.allocPrint(arena, "unrecognized arguments: {s}", .{try std.mem.join(arena, " ", extras.items)}) } };
    }
    return .{ .parsed = p };
}
