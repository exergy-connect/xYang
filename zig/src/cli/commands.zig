//! CLI command registry (mirrors the subcommands of `xyang` in `src/xyang/__main__.py`).
//!
//! Each command owns its usage line, help text, options and handler. `main.zig`
//! dispatches by name through `COMMANDS`; adding a command means adding one entry here.

const std = @import("std");
const xyang = @import("xyang");
const args_mod = @import("args.zig");

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
    options: []const args_mod.Opt,
    positionals: []const args_mod.Positional,
    run: *const fn (ctx: Io, cmd: *const Command, parsed: *const args_mod.Parsed) anyerror!u8,

    fn spec(self: *const Command, arena: std.mem.Allocator) !args_mod.Spec {
        const prog = try std.fmt.allocPrint(arena, "{s} {s}", .{ PROG, self.name });
        return .{ .prog = prog, .usage = self.usage, .help = self.help, .options = self.options, .positionals = self.positionals };
    }
};

const INCLUDE_PATH: args_mod.Opt = .{ .long = "--include-path", .metavar = "DIR", .repeat = true };

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
        .options = &.{INCLUDE_PATH},
        .positionals = &.{.{ .name = "yang_file" }},
        .run = runParse,
    },
    .{
        .name = "validate",
        .summary = "Validate JSON data against a YANG module",
        .usage = "usage: " ++ PROG ++ " validate [-h] [--include-path DIR] [--format {text,json}] [--native-json]\n" ++
            "                      [--rpc NAME] [--action PATH] [--output] [--context FILE]\n" ++
            "                      [--features JSON] [--anydata-validation {off,complete,candidate}]\n" ++
            "                      [--anydata-module PATH]\n" ++
            "                      yang_file [data_file]\n",
        .help =
        \\
        \\Validate JSON or YAML instance data against a YANG module.
        \\Exit 0 is valid, 1 is invalid, and 2 is a usage or module error.
        \\
        \\positional arguments:
        \\  yang_file                     Path to .yang file
        \\  data_file                     Path to JSON or YAML data (.yaml/.yml need PyYAML). '-'
        \\                                or omitted reads JSON from stdin. Default: stdin
        \\
        \\options:
        \\  -h, --help                    show this help message and exit
        \\  --include-path DIR            Directory to search for imported modules (repeatable;
        \\                                searched after the main file's directory). Default: none
        \\  --format {text,json}          Output format: text (default) or json ({valid, errors}
        \\                                on stdout)
        \\  --native-json                 Accept native dict-style JSON instead of strict RFC
        \\                                7951. Default: off (RFC 7951)
        \\  --rpc NAME                    Validate the data as rpc NAME (RFC 7950 §7.14): the RFC
        \\                                8040 {"module:input": {...}} wrapper, or
        \\                                {"module:output": {...}} with --output, or bare
        \\                                parameters with --native-json. Default direction: input
        \\  --action PATH                 Validate the data as the action at PATH (RFC 7950
        \\                                §7.15): the RFC 8040 §3.5.3 data resource identifier
        \\                                /module:list=key/action. Mutually exclusive with --rpc.
        \\                                Needs --context containing that instance. Default
        \\                                direction: input
        \\  --output                      With --rpc or --action, validate the output instead of
        \\                                the input. Requires --rpc or --action. Default: input
        \\  --context FILE                With --rpc or --action, JSON or YAML server data.
        \\                                Validated against the module first (errors carry
        \\                                "document": "context"), then joined to the operation
        \\                                node (RFC 7950 §6.4.1) so must and leafref can reach it.
        \\                                Required with --action. Default: none
        \\  --features JSON               Enabled features as a JSON object {"module": ["feature",
        \\                                ...]}, or null to enable every declared feature (the
        \\                                default)
        \\  --anydata-validation {off,complete,candidate}
        \\                                Optional draft-ietf-netmod-yang-anydata-validation:
        \\                                validate JSON under anydata using extra modules (RFC
        \\                                7951 names). Default: off. When enabled, modules are
        \\                                taken from --anydata-module and/or every *.yang file in
        \\                                --include-path and the host file's directory.
        \\  --anydata-module PATH         Additional .yang file for the anydata module map
        \\                                (repeatable). If omitted, all *.yang files in
        \\                                --include-path and the host directory are loaded
        \\                                (unparseable files are skipped with a warning).
        \\
        \\examples:
        \\  xyang-zig validate --help
        \\  xyang-zig validate -h
        \\  xyang-zig validate --format json module.yang data.json
        \\  xyang-zig validate --rpc add-link module.yang rpc-input.json
        \\  xyang-zig validate --rpc add-link --output --context state.json module.yang output.json
        \\  xyang-zig validate --native-json --rpc add-link module.yang params.json
        \\  xyang-zig validate --action /ex:interfaces/interface=eth0/reset --context state.json module.yang in.json
        \\
        ,
        .options = &.{
            INCLUDE_PATH,
            .{ .long = "--format", .metavar = "{text,json}", .choices = &.{ "text", "json" } },
            .{ .long = "--native-json" },
            .{ .long = "--rpc", .metavar = "NAME" },
            .{ .long = "--action", .metavar = "PATH" },
            .{ .long = "--output" },
            .{ .long = "--context", .metavar = "FILE" },
            .{ .long = "--features", .metavar = "JSON" },
            .{ .long = "--anydata-validation", .metavar = "{off,complete,candidate}", .choices = &.{ "off", "complete", "candidate" } },
            .{ .long = "--anydata-module", .metavar = "PATH", .repeat = true },
        },
        .positionals = &.{ .{ .name = "yang_file" }, .{ .name = "data_file", .optional = true } },
        .run = runValidate,
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

/// Parse the command's arguments, then run it.
pub fn dispatch(ctx: Io, cmd: *const Command, args: []const []const u8) !u8 {
    switch (try args_mod.parse(ctx.arena, try cmd.spec(ctx.arena), args, MAIN_USAGE, PROG, ctx.out)) {
        .help => return 0,
        .usage_error => |e| return usageError(ctx, e.usage, e.prog, "{s}", .{e.message}),
        .parsed => |p| return cmd.run(ctx, cmd, &p),
    }
}

fn exists(ctx: Io, path: []const u8) bool {
    std.Io.Dir.cwd().access(ctx.io, path, .{}) catch return false;
    return true;
}

/// Load the module named on the command line; loader warnings go to stderr as Python logs them.
fn loadModule(ctx: Io, parsed: *const args_mod.Parsed, path: []const u8, diag: *xyang.Diagnostic) !?*xyang.Module {
    var dirs: std.ArrayList([]const u8) = .empty;
    for (parsed.all("--include-path")) |dir| try dirs.append(ctx.arena, try resolvePath(ctx, dir));
    var loader = xyang.Loader.init(ctx.arena, ctx.io, diag, dirs.items);
    const loaded = loader.parseFile(path);
    for (loader.warnings()) |w| try ctx.err.print("{s}\n", .{w});
    return loaded catch |err| switch (err) {
        error.YangLoad => null,
        else => return err,
    };
}

fn runParse(ctx: Io, _: *const Command, parsed: *const args_mod.Parsed) anyerror!u8 {
    const path = parsed.positional("yang_file").?;
    if (!exists(ctx, path)) {
        try ctx.err.print("Error: file not found: {s}\n", .{path});
        return 1;
    }
    var diag: xyang.Diagnostic = .{};
    const module = (try loadModule(ctx, parsed, path, &diag)) orelse {
        try ctx.err.print("Error: {f}\n", .{diag});
        return 1;
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

fn runValidate(ctx: Io, _: *const Command, parsed: *const args_mod.Parsed) anyerror!u8 {
    const jv = xyang.json_value;
    const yv = xyang.yang_validator;
    const path = parsed.positional("yang_file").?;
    if (!exists(ctx, path)) {
        try ctx.err.print("Error: file not found: {s}\n", .{path});
        return 2;
    }
    const rpc = parsed.value("--rpc");
    const action = parsed.value("--action");
    const context = parsed.value("--context");
    if (rpc != null and action != null) {
        try ctx.err.writeAll("Error: --rpc and --action are mutually exclusive\n");
        return 2;
    }
    if (rpc == null and action == null and (parsed.flag("--output") or context != null)) {
        try ctx.err.writeAll("Error: --output and --context apply only together with --rpc or --action\n");
        return 2;
    }
    var message: []const u8 = "";
    var features: ?*yv.EnabledFeatures = null;
    if (parsed.value("--features")) |raw| {
        const value = jv.parse(ctx.arena, raw, &message) catch |err| switch (err) {
            error.OutOfMemory => return err,
            else => return fail(ctx, "--features must be a JSON object or null: {s}", .{message}),
        };
        features = yv.featureMap(ctx.arena, value, &message) catch |err| switch (err) {
            error.OutOfMemory => return err,
            error.InvalidFeatures => return fail(ctx, "{s}", .{message}),
        };
    }
    if (context) |c| if (!exists(ctx, c)) return fail(ctx, "file not found: {s}", .{c});
    var diag: xyang.Diagnostic = .{};
    const module = (try loadModule(ctx, parsed, path, &diag)) orelse return fail(ctx, "{f}", .{diag});
    if (parsed.value("--anydata-validation")) |mode| if (!std.mem.eql(u8, mode, "off")) {
        return fail(ctx, "xyang-zig cannot run --anydata-validation {s} yet (the anydata validation extension is not ported)", .{mode});
    };

    const data_file = parsed.positional("data_file");
    var text: []const u8 = undefined;
    if (data_file != null and !std.mem.eql(u8, data_file.?, "-")) {
        const data_path = data_file.?;
        if (!exists(ctx, data_path)) return fail(ctx, "file not found: {s}", .{data_path});
        const lower = try std.ascii.allocLowerString(ctx.arena, std.fs.path.extension(data_path));
        if (std.mem.eql(u8, lower, ".yaml") or std.mem.eql(u8, lower, ".yml")) {
            return fail(ctx, "xyang-zig cannot read YAML instance data ({s}); pass JSON", .{data_path});
        }
        text = std.Io.Dir.cwd().readFileAlloc(ctx.io, data_path, ctx.arena, .unlimited) catch |err| return fail(ctx, "cannot read {s}: {s}", .{ data_path, @errorName(err) });
    } else {
        var buf: [4096]u8 = undefined;
        var r = std.Io.File.stdin().reader(ctx.io, &buf);
        text = try r.interface.allocRemaining(ctx.arena, .unlimited);
    }
    const data = jv.parse(ctx.arena, text, &message) catch |err| switch (err) {
        error.OutOfMemory => return err,
        else => return fail(ctx, "{s}", .{message}),
    };
    if (rpc != null or action != null) {
        return fail(ctx, "xyang-zig cannot validate rpc or action input and output yet (operations are phase 5 of #165)", .{});
    }

    var validator = xyang.YangValidator.init(ctx.arena, module);
    const result = validator.validate(data, .{ .native_json = parsed.flag("--native-json"), .enabled_features_by_module = features }) catch |err| switch (err) {
        error.Unsupported, error.Raised => return fail(ctx, "{s}", .{validator.unsupported orelse "unsupported construct"}),
        else => return err,
    };

    const format = parsed.value("--format") orelse "text";
    if (std.mem.eql(u8, format, "json")) {
        for (result.warnings) |w| try ctx.err.print("Warning: {s}: {s}\n", .{ w.pointer, w.message });
        const str = struct {
            fn f(w: *std.Io.Writer, v: []const u8) !void {
                try std.json.Stringify.encodeJsonString(v, .{ .escape_unicode = true }, w);
            }
        }.f;
        try ctx.out.writeAll("{\"valid\": ");
        try ctx.out.writeAll(if (result.valid()) "true" else "false");
        try ctx.out.writeAll(", \"errors\": [");
        for (result.errors, 0..) |e, i| {
            if (i > 0) try ctx.out.writeAll(", ");
            try ctx.out.writeAll("{");
            if (!std.mem.eql(u8, e.document, "data")) {
                try ctx.out.writeAll("\"document\": ");
                try str(ctx.out, e.document);
                try ctx.out.writeAll(", ");
            }
            try ctx.out.writeAll("\"path\": ");
            try str(ctx.out, e.pointer);
            try ctx.out.writeAll(", \"code\": ");
            try str(ctx.out, e.code);
            try ctx.out.writeAll(", \"message\": ");
            try str(ctx.out, e.message);
            try ctx.out.writeAll("}");
        }
        try ctx.out.writeAll("]}\n");
        return if (result.valid()) 0 else 1;
    }
    if (result.valid()) {
        try ctx.out.writeAll("Valid.\n");
        for (result.warnings) |w| try ctx.out.print("  Warning: {s}\n", .{try yv.formatError(ctx.arena, w)});
        return 0;
    }
    try ctx.err.writeAll("Validation failed:\n");
    for (result.errors) |e| try ctx.err.print("  {s}\n", .{try yv.formatError(ctx.arena, e)});
    return 1;
}

/// `_print_cli_error`: `Error: message` on stderr, exit 2.
fn fail(ctx: Io, comptime fmt: []const u8, args: anytype) !u8 {
    try ctx.err.print("Error: " ++ fmt ++ "\n", args);
    return 2;
}

/// `Path(p).resolve()`: symlinks resolved when the path exists, else made absolute.
fn resolvePath(ctx: Io, p: []const u8) ![]const u8 {
    return std.Io.Dir.cwd().realPathFileAlloc(ctx.io, p, ctx.arena) catch {
        const cwd = try std.process.currentPathAlloc(ctx.io, ctx.arena);
        return std.fs.path.resolveAlloc(ctx.arena, &.{ cwd, p });
    };
}
