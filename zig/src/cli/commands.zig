//! CLI command registry (mirrors the subcommands of `xyang` in `src/xyang/__main__.py`).
//!
//! Each command owns its usage line, help text, options and handler. `main.zig`
//! dispatches by name through `COMMANDS`; adding a command means adding one entry here.

const std = @import("std");
const xyang = @import("xyang");
const args_mod = @import("args.zig");
const build_options = @import("build_options");

pub const PROG = "xyang-zig";

/// Same text `xyang -V` prints (`pyproject.toml` `version`, read in `build.zig`).
pub const VERSION = build_options.version;

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
    .{
        .name = "convert",
        .summary = "Convert .yang to .yang.json (JSON Schema with x-yang)",
        .usage = "usage: " ++ PROG ++ " convert [-h] [--include-path DIR] [-o PATH] yang_file\n",
        .help =
        \\
        \\Write JSON Schema (2020-12) with x-yang to a file whose name ends in .yang.json.
        \\Default path: <stem>.yang.json beside the input.
        \\
        \\positional arguments:
        \\  yang_file           Path to .yang file
        \\
        \\options:
        \\  -h, --help          show this help message and exit
        \\  --include-path DIR  Directory to search for imported modules (repeatable; searched
        \\                      after the main file's directory). Default: none
        \\  -o, --output PATH   Output file (default: <stem>.yang.json beside the input). If the
        \\                      name does not end in .yang.json, that suffix is added
        \\
        \\examples:
        \\  xyang-zig convert --help
        \\  xyang-zig convert -h
        \\  xyang-zig convert module.yang
        \\  xyang-zig convert module.yang -o module.yang.json
        \\  xyang-zig convert --include-path ./modules module.yang -o out.yang.json
        \\
        ,
        .options = &.{ INCLUDE_PATH, .{ .long = "--output", .short = "-o", .metavar = "PATH" } },
        .positionals = &.{.{ .name = "yang_file" }},
        .run = runConvert,
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

pub const MAIN_USAGE = "usage: " ++ PROG ++ " [-h] [-V] " ++ CHOICES ++ " ...\n";

/// Python 3.14 argparse help for the top-level parser (`_CliHelpFormatter`: width 88,
/// max_help_position 32). An option with a short and a long form is `-V, --version`,
/// and the help column wraps to that invocation width. The examples are the epilog
/// from `build_parser`, not one generated line per command.
pub const MAIN_HELP = blk: {
    var width: usize = CHOICES.len;
    for (COMMANDS) |c| width = @max(width, c.name.len + 2);
    var s: []const u8 = MAIN_USAGE ++
        "\nxYang: Parse YANG modules, validate RFC 7951 JSON instance data, and export JSON Schema\n" ++
        "\npositional arguments:\n  " ++ pad(CHOICES, width) ++ "  Commands\n";
    for (COMMANDS) |c| s = s ++ "    " ++ pad(c.name, width - 2) ++ "  " ++ c.summary ++ "\n";
    s = s ++ "\noptions:\n  " ++ pad("-h, --help", width) ++ "  show this help message and exit\n" ++
        "  " ++ pad("-V, --version", width) ++ "  show program's version number and exit\n" ++
        "\nexamples:\n" ++
        "  " ++ PROG ++ " --help\n" ++
        "  " ++ PROG ++ " -h\n" ++
        "  " ++ PROG ++ " -V\n" ++
        "  " ++ PROG ++ " parse module.yang\n" ++
        "  " ++ PROG ++ " validate --format json module.yang data.json\n" ++
        "  " ++ PROG ++ " validate --rpc add-link --output --context state.json module.yang output.json\n" ++
        "  " ++ PROG ++ " convert module.yang -o module.yang.json\n";
    break :blk s;
};

const LongOpt = struct {
    name: []const u8,
    display: []const u8,
    help: bool,
};

/// Top-level optional actions, in the order argparse registered them.
const LONGS = [_]LongOpt{
    .{ .name = "--help", .display = "-h/--help", .help = true },
    .{ .name = "--version", .display = "-V/--version", .help = false },
};

const TopKind = union(enum) { help, version, unknown, err: []const u8 };

fn ignoredExplicit(arena: std.mem.Allocator, display: []const u8, value: []const u8) !TopKind {
    return .{ .err = try std.fmt.allocPrint(arena, "argument {s}: ignored explicit argument '{s}'", .{ display, value }) };
}

/// Long-option prefix match, including `--opt=value` on a flag (`nargs == 0`).
fn classifyLong(arena: std.mem.Allocator, arg: []const u8) !TopKind {
    const eq = std.mem.indexOfScalar(u8, arg, '=');
    const prefix = if (eq) |e| arg[0..e] else arg;
    var matched: [LONGS.len]usize = undefined;
    var n: usize = 0;
    for (LONGS, 0..) |o, idx| {
        if (std.mem.startsWith(u8, o.name, prefix)) {
            matched[n] = idx;
            n += 1;
        }
    }
    if (n == 0) return .unknown;
    if (n > 1) {
        var parts: [LONGS.len][]const u8 = undefined;
        for (matched[0..n], 0..) |idx, k| parts[k] = LONGS[idx].name;
        return .{ .err = try std.fmt.allocPrint(arena, "ambiguous option: {s} could match {s}", .{ arg, try std.mem.join(arena, ", ", parts[0..n]) }) };
    }
    const o = LONGS[matched[0]];
    if (eq) |e| return ignoredExplicit(arena, o.display, arg[e + 1 ..]);
    return if (o.help) .help else .version;
}

/// Single-dash cluster. `-h` and `-V` take no value, so the first one exits, unless a
/// later `=` in the same argv element is an ignored explicit argument (argparse raises
/// that while collecting the cluster, before running the first action).
fn classifyShort(arena: std.mem.Allocator, arg: []const u8) !TopKind {
    if (std.mem.indexOfScalar(u8, arg, '=')) |eq| {
        const left = arg[0..eq];
        if (std.mem.eql(u8, left, "-h") or std.mem.eql(u8, left, "-V")) {
            const display = if (left[1] == 'h') "-h/--help" else "-V/--version";
            return ignoredExplicit(arena, display, arg[eq + 1 ..]);
        }
    }
    var index: usize = 1;
    var first: ?u8 = null;
    while (index < arg.len) {
        const ch = arg[index];
        if (ch != 'h' and ch != 'V') {
            if (first == null) return .unknown;
            break;
        }
        if (first == null) first = ch;
        index += 1;
        if (index < arg.len and arg[index] == '=') {
            const display = if (ch == 'h') "-h/--help" else "-V/--version";
            return ignoredExplicit(arena, display, arg[index + 1 ..]);
        }
    }
    return if (first.? == 'h') .help else .version;
}

fn classifyTop(arena: std.mem.Allocator, arg: []const u8) !TopKind {
    if (std.mem.startsWith(u8, arg, "--")) return classifyLong(arena, arg);
    return classifyShort(arena, arg);
}

/// Top-level argv, with the same exits as `xyang`: help and version on stdout exit 0
/// (and do no file I/O), a missing command prints help, and usage errors exit 2.
/// Unknown options before the command are extras of this parser. They are reported
/// only when the subcommand's own parse succeeds; a subcommand usage error wins, as
/// it does in argparse (the subparser runs inside the parent parse).
pub fn runTop(ctx: Io, args: []const []const u8) !u8 {
    const arena = ctx.arena;
    var extras: std.ArrayList([]const u8) = .empty;
    var i: usize = 0;
    var only_positional = false;
    while (i < args.len) {
        const a = args[i];
        if (!only_positional and std.mem.eql(u8, a, "--")) {
            if (i + 1 >= args.len) {
                try extras.append(arena, a);
                i += 1;
                break;
            }
            only_positional = true;
            i += 1;
            continue;
        }
        if (!only_positional and args_mod.looksLikeOption(a)) {
            switch (try classifyTop(arena, a)) {
                .help => {
                    try ctx.out.writeAll(MAIN_HELP);
                    return 0;
                },
                .version => {
                    try ctx.out.print("{s} {s}\n", .{ PROG, VERSION });
                    return 0;
                },
                .unknown => {
                    try extras.append(arena, a);
                    i += 1;
                    continue;
                },
                .err => |msg| return usageError(ctx, MAIN_USAGE, PROG, "{s}", .{msg}),
            }
        }
        break;
    }
    if (i >= args.len) {
        if (extras.items.len > 0) {
            return usageError(ctx, MAIN_USAGE, PROG, "unrecognized arguments: {s}", .{try std.mem.join(arena, " ", extras.items)});
        }
        try ctx.out.writeAll(MAIN_HELP);
        return 0;
    }
    const name = args[i];
    const cmd = find(name) orelse {
        var names: std.ArrayList(u8) = .empty;
        for (COMMANDS, 0..) |c, n| {
            if (n != 0) try names.appendSlice(arena, ", ");
            try names.appendSlice(arena, c.name);
        }
        return usageError(ctx, MAIN_USAGE, PROG, "argument cmd: invalid choice: '{s}' (choose from {s})", .{ name, names.items });
    };
    switch (try args_mod.parse(arena, try cmd.spec(arena), args[i + 1 ..], MAIN_USAGE, PROG, ctx.out)) {
        .help => return 0,
        .usage_error => |e| return usageError(ctx, e.usage, e.prog, "{s}", .{e.message}),
        .parsed => |p| {
            if (extras.items.len > 0) {
                return usageError(ctx, MAIN_USAGE, PROG, "unrecognized arguments: {s}", .{try std.mem.join(arena, " ", extras.items)});
            }
            return cmd.run(ctx, cmd, &p);
        },
    }
}

test "top-level help is the Python 3.14 registry" {
    try std.testing.expect(std.mem.indexOf(u8, MAIN_HELP, "[-h] [-V] {parse,validate,convert}") != null);
    try std.testing.expect(std.mem.indexOf(u8, MAIN_HELP, "-V, --version") != null);
    try std.testing.expect(std.mem.indexOf(u8, MAIN_HELP, "xYang: Parse YANG modules") != null);
    try std.testing.expect(std.mem.indexOf(u8, MAIN_HELP, "xyang-zig -V\n") != null);
    try std.testing.expect(std.mem.indexOf(u8, MAIN_HELP, "xyang-zig convert module.yang -o module.yang.json\n") != null);
    try std.testing.expect(std.mem.indexOf(u8, COMMANDS[2].usage, "[-o PATH]") != null);
    try std.testing.expect(std.mem.indexOf(u8, COMMANDS[2].help, "-o, --output PATH") != null);
    try std.testing.expect(std.mem.indexOf(u8, COMMANDS[2].help, "-o PATH, --output PATH") == null);
}

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
    var context_data: ?jv.Val = null;
    if (rpc != null or action != null) if (context) |c| {
        if (!exists(ctx, c)) return fail(ctx, "file not found: {s}", .{c});
        const c_text = (try readInstanceFile(ctx, c, &message)) orelse return fail(ctx, "{s}", .{message});
        context_data = jv.parse(ctx.arena, c_text, &message) catch |err| switch (err) {
            error.OutOfMemory => return err,
            else => return fail(ctx, "{s}", .{message}),
        };
    };
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
        text = (try readInstanceFile(ctx, data_path, &message)) orelse return fail(ctx, "{s}", .{message});
    } else {
        var buf: [4096]u8 = undefined;
        var r = std.Io.File.stdin().reader(ctx.io, &buf);
        text = try r.interface.allocRemaining(ctx.arena, .unlimited);
    }
    const data = jv.parse(ctx.arena, text, &message) catch |err| switch (err) {
        error.OutOfMemory => return err,
        else => return fail(ctx, "{s}", .{message}),
    };
    var validator = xyang.YangValidator.init(ctx.arena, module);
    const result = validator.validate(data, .{
        .native_json = parsed.flag("--native-json"),
        .enabled_features_by_module = features,
        .rpc = rpc,
        .action = action,
        .direction = if (parsed.flag("--output")) "output" else "input",
        .context = context_data,
    }) catch |err| switch (err) {
        error.Unsupported, error.Raised => return fail(ctx, "{s}", .{validator.unsupported orelse "unsupported construct"}),
        error.Usage => return fail(ctx, "{s}", .{validator.usage orelse "invalid call"}),
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

/// `xyang convert`: parse without expanding `uses` and write the native JSON form. An
/// export error exits 2, a module error 1.
fn runConvert(ctx: Io, _: *const Command, parsed: *const args_mod.Parsed) anyerror!u8 {
    const raw = parsed.positional("yang_file").?;
    const p = try pyPath(ctx.arena, raw);
    if (!exists(ctx, raw)) {
        try ctx.err.print("Error: file not found: {s}\n", .{p});
        return 1;
    }
    const out_path = if (parsed.value("--output")) |o| blk: {
        const op = try pyPath(ctx.arena, o);
        const name = std.fs.path.basename(op);
        if (std.mem.endsWith(u8, name, ".yang.json")) break :blk op;
        const parent = std.fs.path.dirname(op);
        const file = try std.fmt.allocPrint(ctx.arena, "{s}.yang.json", .{pathStem(name)});
        break :blk if (parent) |d| try std.fs.path.join(ctx.arena, &.{ d, file }) else file;
    } else try withSuffix(ctx.arena, p, ".yang.json");

    var dirs: std.ArrayList([]const u8) = .empty;
    for (parsed.all("--include-path")) |dir| try dirs.append(ctx.arena, try resolvePath(ctx, dir));
    var diag: xyang.Diagnostic = .{};
    var loader = xyang.Loader.init(ctx.arena, ctx.io, &diag, dirs.items);
    loader.expand_uses = false;
    const loaded = loader.parseFile(raw);
    for (loader.warnings()) |w| try ctx.err.print("{s}\n", .{w});
    const module = loaded catch |err| switch (err) {
        error.YangLoad => {
            try ctx.err.print("Error: {f}\n", .{diag});
            return 1;
        },
        else => return err,
    };
    const text = xyang.json_generator.schemaToYangJson(ctx.arena, module, &diag) catch |err| switch (err) {
        error.Export => {
            try ctx.err.print("Error: {f}\n", .{diag});
            return 2;
        },
        error.YangLoad => {
            try ctx.err.print("Error: {f}\n", .{diag});
            return 1;
        },
        else => return err,
    };
    const cwd = std.Io.Dir.cwd();
    if (std.fs.path.dirname(out_path)) |d| cwd.createDirPath(ctx.io, d) catch |err| {
        try ctx.err.print("Error: cannot create {s}: {s}\n", .{ d, @errorName(err) });
        return 1;
    };
    cwd.writeFile(ctx.io, .{ .sub_path = out_path, .data = text }) catch |err| {
        try ctx.err.print("Error: cannot write {s}: {s}\n", .{ out_path, @errorName(err) });
        return 1;
    };
    try ctx.out.print("Wrote {s}\n", .{out_path});
    return 0;
}

/// `str(Path(p))`: repeated and trailing slashes and `.` components removed.
fn pyPath(arena: std.mem.Allocator, p: []const u8) ![]const u8 {
    if (p.len == 0) return ".";
    var out: std.ArrayList(u8) = .empty;
    const leading: usize = if (std.mem.startsWith(u8, p, "//") and !std.mem.startsWith(u8, p, "///")) 2 else if (p[0] == '/') 1 else 0;
    try out.appendNTimes(arena, '/', leading);
    var it = std.mem.tokenizeScalar(u8, p, '/');
    var first = true;
    while (it.next()) |part| {
        if (std.mem.eql(u8, part, ".")) continue;
        if (!first) try out.append(arena, '/');
        try out.appendSlice(arena, part);
        first = false;
    }
    if (out.items.len == 0) return ".";
    return out.items;
}

/// `PurePath.suffix` start: the last `.` of the name, unless it leads or ends the name.
fn suffixIndex(name: []const u8) ?usize {
    const i = std.mem.lastIndexOfScalar(u8, name, '.') orelse return null;
    if (i == 0 or i == name.len - 1) return null;
    return i;
}

fn pathStem(name: []const u8) []const u8 {
    return if (suffixIndex(name)) |i| name[0..i] else name;
}

/// `Path.with_suffix(suffix)`.
fn withSuffix(arena: std.mem.Allocator, p: []const u8, suffix: []const u8) ![]const u8 {
    const name = std.fs.path.basename(p);
    const head = p[0 .. p.len - name.len];
    return std.fmt.allocPrint(arena, "{s}{s}{s}", .{ head, pathStem(name), suffix });
}

/// `_load_instance_data` for a JSON file: its text, or null with `message` set. YAML is
/// refused loudly.
fn readInstanceFile(ctx: Io, path: []const u8, message: *[]const u8) !?[]const u8 {
    const lower = try std.ascii.allocLowerString(ctx.arena, std.fs.path.extension(path));
    if (std.mem.eql(u8, lower, ".yaml") or std.mem.eql(u8, lower, ".yml")) {
        message.* = try std.fmt.allocPrint(ctx.arena, "xyang-zig cannot read YAML instance data ({s}); pass JSON", .{path});
        return null;
    }
    return std.Io.Dir.cwd().readFileAlloc(ctx.io, path, ctx.arena, .unlimited) catch |err| {
        message.* = try std.fmt.allocPrint(ctx.arena, "cannot read {s}: {s}", .{ path, @errorName(err) });
        return null;
    };
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

fn expectUsageError(argv: []const []const u8, expected: []const u8) !void {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var out: std.Io.Writer.Allocating = .init(arena.allocator());
    var err: std.Io.Writer.Allocating = .init(arena.allocator());
    const status = try runTop(.{ .io = std.testing.io, .arena = arena.allocator(), .out = &out.writer, .err = &err.writer }, argv);
    try std.testing.expectEqual(@as(u8, 2), status);
    try std.testing.expectEqualStrings("", out.written());
    try std.testing.expectEqualStrings(expected, err.written());
}

test "unknown command lists choices using Python 3.14 wording" {
    try expectUsageError(&.{"nonesuch"}, MAIN_USAGE ++ PROG ++ ": error: argument cmd: invalid choice: 'nonesuch' (choose from parse, validate, convert)\n");
}

test "invalid option choice lists choices before reading the module" {
    try expectUsageError(&.{ "validate", "--format", "xml", "missing.yang" }, COMMANDS[1].usage ++ PROG ++ " validate: error: argument --format: invalid choice: 'xml' (choose from text, json)\n");
}
