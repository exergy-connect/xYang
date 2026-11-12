//! Conformance runner: executes the shared cases in `tests/cases/` against the Zig port,
//! following the contract of `tests/test_cases.py`.
//!
//! Every case either passes or is listed in `zig/conformance-pending.txt` with the phase
//! of #165 that delivers it. The run fails when an unlisted case fails, when a listed case
//! passes (remove it from the list), when the list names a missing case, or when the
//! parser rejects a module Python loads.
//!
//! What a case needs, and which phase provides it:
//! - `schema_error`: the load (parse and module resolution) fails with a message
//!   containing `code`. An `unsupported` failure never counts as the expected error.
//! - `instances`: RFC 7951 validation (phases 3 to 5). Each instance must give Python's
//!   `(path, code)` set, messages and `valid`; with `rpc` / `action` / `direction` /
//!   `context` it is an operation instance, and `usage_error` must be contained in the
//!   rejected call's message. The module must still parse or fail as `unsupported`.
//! - `json_form` / `export_error`: the native JSON form (phase 6).

const std = @import("std");
const xyang = @import("xyang");

const Outcome = union(enum) {
    pass,
    /// Not delivered yet; the reason names what is missing.
    pending: []const u8,
    /// The parser rejected a module that Python loads: always a failure.
    regression: []const u8,
};

const PendingEntry = struct { phase: u8, line: usize, seen: bool = false };

pub fn main(init: std.process.Init) !u8 {
    const arena = init.arena.allocator();
    const io = init.io;
    const argv = try init.minimal.args.toSlice(arena);

    var out_buf: [8192]u8 = undefined;
    var out_w: std.Io.File.Writer = .init(.stdout(), io, &out_buf);
    const out = &out_w.interface;
    defer out.flush() catch {};

    var cases_dir: []const u8 = "../tests/cases";
    var pending_path: []const u8 = "conformance-pending.txt";
    var verbose = false;
    var i: usize = 1;
    while (i < argv.len) : (i += 1) {
        const a: []const u8 = argv[i];
        if (std.mem.eql(u8, a, "--registry-snapshot")) {
            try xyang.dispatch_registry.writeParitySnapshot(out, arena);
            return 0;
        } else if (std.mem.eql(u8, a, "--dump-case") and i + 1 < argv.len) {
            return dumpCase(arena, io, cases_dir, argv[i + 1], out);
        } else if (std.mem.eql(u8, a, "--cases") and i + 1 < argv.len) {
            i += 1;
            cases_dir = argv[i];
        } else if (std.mem.eql(u8, a, "--pending") and i + 1 < argv.len) {
            i += 1;
            pending_path = argv[i];
        } else if (std.mem.eql(u8, a, "-v") or std.mem.eql(u8, a, "--verbose")) {
            verbose = true;
        } else {
            try out.print("usage: xyang-zig-conformance [--cases DIR] [--pending FILE] [-v] [--registry-snapshot] [--dump-case CASE]\nunknown argument: {s}\n", .{a});
            return 2;
        }
    }

    var failures: usize = 0;
    var pending = try loadPending(arena, io, pending_path, out, &failures);

    const case_ids = try findCases(arena, io, cases_dir);
    var passed: usize = 0;
    var pending_by_phase: [8]usize = @splat(0);
    for (case_ids) |cid| {
        const outcome = try runCase(arena, io, cases_dir, cid);
        const listed = pending.getPtr(cid);
        if (listed) |e| e.seen = true;
        switch (outcome) {
            .pass => {
                if (listed) |e| {
                    failures += 1;
                    try out.print("FAIL {s}: passes but is listed as pending (phase {d}) in {s}:{d}; remove it from the list\n", .{ cid, e.phase, pending_path, e.line });
                } else {
                    passed += 1;
                    if (verbose) try out.print("pass {s}\n", .{cid});
                }
            },
            .pending => |why| {
                if (listed) |e| {
                    pending_by_phase[e.phase] += 1;
                    if (verbose) try out.print("pending {s} (phase {d}): {s}\n", .{ cid, e.phase, why });
                } else {
                    failures += 1;
                    try out.print("FAIL {s}: {s} (not listed in {s})\n", .{ cid, why, pending_path });
                }
            },
            .regression => |why| {
                failures += 1;
                try out.print("FAIL {s}: {s}\n", .{ cid, why });
            },
        }
    }
    var it = pending.iterator();
    while (it.next()) |entry| {
        if (!entry.value_ptr.seen) {
            failures += 1;
            try out.print("FAIL {s}:{d}: no case {s} under {s}\n", .{ pending_path, entry.value_ptr.line, entry.key_ptr.*, cases_dir });
        }
    }

    var listed_total: usize = 0;
    for (pending_by_phase) |n| listed_total += n;
    try out.print("\n{d} cases: {d} pass, {d} pending", .{ case_ids.len, passed, listed_total });
    var first = true;
    for (pending_by_phase, 0..) |n, phase| {
        if (n == 0) continue;
        try out.print("{s}phase {d}: {d}", .{ if (first) " (" else ", ", phase, n });
        first = false;
    }
    try out.print("{s}\n", .{if (first) "" else ")"});
    if (failures > 0) {
        try out.print("{d} conformance failure(s)\n", .{failures});
        return 1;
    }
    return 0;
}

fn loadPending(arena: std.mem.Allocator, io: std.Io, path: []const u8, out: *std.Io.Writer, failures: *usize) !std.StringArrayHashMapUnmanaged(PendingEntry) {
    var map: std.StringArrayHashMapUnmanaged(PendingEntry) = .empty;
    const text = try std.Io.Dir.cwd().readFileAlloc(io, path, arena, .unlimited);
    var lines = std.mem.splitScalar(u8, text, '\n');
    var n: usize = 0;
    while (lines.next()) |raw| {
        n += 1;
        const line = std.mem.trim(u8, raw, " \t\r");
        if (line.len == 0 or line[0] == '#') continue;
        var fields = std.mem.tokenizeAny(u8, line, " \t");
        const cid = fields.next().?;
        const tag = fields.next() orelse "";
        const extra = fields.next();
        const phase: ?u8 = if (std.mem.startsWith(u8, tag, "phase-")) std.fmt.parseInt(u8, tag["phase-".len..], 10) catch null else null;
        if (phase == null or phase.? < 2 or phase.? > 7 or extra != null) {
            failures.* += 1;
            try out.print("FAIL {s}:{d}: expected '<case> phase-N' with N in 2..7, got {s}\n", .{ path, n, line });
            continue;
        }
        const gop = try map.getOrPut(arena, cid);
        if (gop.found_existing) {
            failures.* += 1;
            try out.print("FAIL {s}:{d}: {s} is listed twice\n", .{ path, n, cid });
            continue;
        }
        gop.value_ptr.* = .{ .phase = phase.?, .line = n };
    }
    return map;
}

fn findCases(arena: std.mem.Allocator, io: std.Io, cases_dir: []const u8) ![]const []const u8 {
    var dir = try std.Io.Dir.cwd().openDir(io, cases_dir, .{ .iterate = true });
    defer dir.close(io);
    var walker = try dir.walk(arena);
    defer walker.deinit();
    var ids: std.ArrayList([]const u8) = .empty;
    while (try walker.next(io)) |entry| {
        if (entry.kind != .file or !std.mem.eql(u8, entry.basename, "case.json")) continue;
        const parent = std.fs.path.dirname(entry.path) orelse continue;
        const cid = try arena.dupe(u8, parent);
        std.mem.replaceScalar(u8, cid, std.fs.path.sep, '/');
        try ids.append(arena, cid);
    }
    std.mem.sort([]const u8, ids.items, {}, struct {
        fn lt(_: void, a: []const u8, b: []const u8) bool {
            return std.mem.order(u8, a, b) == .lt;
        }
    }.lt);
    return ids.items;
}

fn field(obj: std.json.ObjectMap, name: []const u8) ?std.json.Value {
    return obj.get(name);
}

fn truthy(v: ?std.json.Value) bool {
    const value = v orelse return false;
    return switch (value) {
        .bool => |b| b,
        .null => false,
        .string => |s| s.len > 0,
        else => true,
    };
}

const Load = union(enum) {
    ok: *xyang.Module,
    failed: xyang.Diagnostic,
};

/// `_load_case_module`: one loader with the case directory on its include path. The case
/// module is loaded and cached, then every other non-submodule `.yang` file in the
/// directory, so their `augment` statements merge into the cached primary module. The
/// first failure wins.
fn loadCaseModules(arena: std.mem.Allocator, io: std.Io, case_dir: []const u8, module_name: []const u8) !Load {
    var diag: xyang.Diagnostic = .{};
    const primary = try std.fs.path.join(arena, &.{ case_dir, module_name });
    const include_path = try arena.dupe([]const u8, &.{case_dir});
    var loader = xyang.Loader.init(arena, io, &diag, include_path);
    const parsed = loader.parseFile(primary) catch |err| switch (err) {
        error.YangLoad => return .{ .failed = diag },
        else => return err,
    };
    try loader.cache(try std.Io.Dir.cwd().realPathFileAlloc(io, primary, arena), parsed);
    var dir = try std.Io.Dir.cwd().openDir(io, case_dir, .{ .iterate = true });
    defer dir.close(io);
    var names: std.ArrayList([]const u8) = .empty;
    var iter = dir.iterate();
    while (try iter.next(io)) |entry| {
        if (entry.kind != .file or !std.mem.endsWith(u8, entry.name, ".yang")) continue;
        if (std.mem.eql(u8, entry.name, module_name)) continue;
        try names.append(arena, try arena.dupe(u8, entry.name));
    }
    std.mem.sort([]const u8, names.items, {}, struct {
        fn lt(_: void, a: []const u8, b: []const u8) bool {
            return std.mem.order(u8, a, b) == .lt;
        }
    }.lt);
    for (names.items) |name| {
        const path = try std.fs.path.join(arena, &.{ case_dir, name });
        const text = try std.Io.Dir.cwd().readFileAlloc(io, path, arena, .unlimited);
        if (std.mem.startsWith(u8, std.mem.trimStart(u8, text, &std.ascii.whitespace), "submodule")) continue;
        _ = loader.parseFile(path) catch |err| switch (err) {
            error.YangLoad => return .{ .failed = diag },
            else => return err,
        };
    }
    return .{ .ok = parsed };
}

/// Print the resolved primary module of a case as JSON, or `{"error": message}` when the
/// load fails. `--cases` must come first.
fn dumpCase(arena: std.mem.Allocator, io: std.Io, cases_dir: []const u8, cid: []const u8, out: *std.Io.Writer) !u8 {
    const case_dir = try std.fs.path.join(arena, &.{ cases_dir, cid });
    const text = try std.Io.Dir.cwd().readFileAlloc(io, try std.fs.path.join(arena, &.{ case_dir, "case.json" }), arena, .unlimited);
    const root = try std.json.parseFromSliceLeaky(std.json.Value, arena, text, .{});
    switch (try loadCaseModules(arena, io, case_dir, root.object.get("module").?.string)) {
        .ok => |m| try xyang.schema_dump.writeModule(out, arena, m),
        .failed => |diag| {
            var s: std.json.Stringify = .{ .writer = out };
            try s.beginObject();
            try s.objectField("error");
            try s.write(try std.fmt.allocPrint(arena, "{f}", .{diag}));
            try s.endObject();
        },
    }
    try out.writeAll("\n");
    return 0;
}

fn runCase(arena: std.mem.Allocator, io: std.Io, cases_dir: []const u8, cid: []const u8) !Outcome {
    const case_dir = try std.fs.path.join(arena, &.{ cases_dir, cid });
    const case_path = try std.fs.path.join(arena, &.{ case_dir, "case.json" });
    const text = try std.Io.Dir.cwd().readFileAlloc(io, case_path, arena, .unlimited);
    const root = try std.json.parseFromSliceLeaky(std.json.Value, arena, text, .{});
    const case = root.object;
    const module_name = field(case, "module").?.string;

    if (truthy(field(case, "export_error"))) return .{ .pending = "needs the native JSON export (phase 6)" };

    const load = try loadCaseModules(arena, io, case_dir, module_name);
    const json_form = truthy(field(case, "json_form"));

    if (truthy(field(case, "schema_error"))) {
        const diag = switch (load) {
            .ok => return .{ .pending = "expected a load error; the module loads" },
            .failed => |d| d,
        };
        const msg = try std.fmt.allocPrint(arena, "{f}", .{diag});
        if (diag.kind == .unsupported) return .{ .pending = try std.fmt.allocPrint(arena, "unsupported: {s}", .{msg}) };
        if (field(case, "code")) |code| {
            if (code == .string and std.mem.indexOf(u8, msg, code.string) == null) {
                return .{ .pending = try std.fmt.allocPrint(arena, "load error {s} does not contain {s}", .{ msg, code.string }) };
            }
        }
        if (json_form) return .{ .pending = "needs the native JSON form (phase 6)" };
        return .pass;
    }

    switch (load) {
        .ok => {},
        .failed => |diag| {
            const msg = try std.fmt.allocPrint(arena, "{f}", .{diag});
            if (diag.kind != .unsupported) {
                return .{ .regression = try std.fmt.allocPrint(arena, "the module loads in Python but xyang-zig rejects it: {s}", .{msg}) };
            }
            return .{ .pending = try std.fmt.allocPrint(arena, "unsupported: {s}", .{msg}) };
        },
    }
    const instances = field(case, "instances") orelse return .{ .regression = "the case has no instances" };
    for (instances.array.items) |inst_value| {
        const outcome = try runInstance(arena, case, inst_value.object, load.ok);
        if (outcome != .pass) return outcome;
    }
    if (json_form) return .{ .pending = "needs the native JSON form (phase 6)" };
    return .pass;
}

/// One instance, as `test_case` in `tests/test_cases.py` checks it: the set of
/// `(path, code)` pairs, each expected `message` as a substring, and `valid`. xyang-zig
/// follows Python, so a `python` xfail (case or instance) is strict: the instance must
/// then not match.
fn runInstance(arena: std.mem.Allocator, case: std.json.ObjectMap, inst: std.json.ObjectMap, module: *xyang.Module) !Outcome {
    const name = if (inst.get("name")) |n| n.string else "?";
    const xfail = xfailReason(case, inst);
    var msg: []const u8 = "";
    const data = try jsonVal(arena, inst.get("data") orelse std.json.Value.null);
    const context: ?xyang.json_value.Val = if (inst.get("context")) |c| try jsonVal(arena, c) else null;
    var features: ?*xyang.yang_validator.EnabledFeatures = null;
    if (field(case, "features")) |f| {
        const f_text = try std.json.Stringify.valueAlloc(arena, f, .{});
        features = xyang.yang_validator.featureMap(arena, try xyang.json_value.parse(arena, f_text, &msg), &msg) catch |err| switch (err) {
            error.InvalidFeatures => return .{ .regression = try std.fmt.allocPrint(arena, "case features: {s}", .{msg}) },
            else => return err,
        };
    }
    const native = if (inst.get("encoding")) |e| e == .string and std.mem.eql(u8, e.string, "native") else false;
    var validator = xyang.YangValidator.init(arena, module);
    const options: xyang.yang_validator.Options = .{
        .native_json = native,
        .enabled_features_by_module = features,
        .rpc = if (inst.get("rpc")) |r| r.string else null,
        .action = if (inst.get("action")) |p| p.string else null,
        .direction = if (inst.get("direction")) |d| d.string else "input",
        .context = context,
    };
    const usage_error: ?[]const u8 = if (inst.get("usage_error")) |e| e.string else null;
    const result = validator.validate(data, options) catch |err| switch (err) {
        error.Unsupported => return .{ .pending = try std.fmt.allocPrint(arena, "instance {s}: unsupported: {s}", .{ name, validator.unsupported orelse "?" }) },
        error.Raised => return .{ .regression = try std.fmt.allocPrint(arena, "instance {s}: validation raised: {s}", .{ name, validator.unsupported orelse "?" }) },
        error.Usage => {
            const got = validator.usage orelse "";
            const want = usage_error orelse return .{ .pending = try std.fmt.allocPrint(arena, "instance {s}: unexpected usage error: {s}", .{ name, got }) };
            if (std.mem.indexOf(u8, got, want) == null) return .{ .pending = try std.fmt.allocPrint(arena, "instance {s}: usage error {s} does not contain {s}", .{ name, got, want }) };
            return .pass;
        },
        else => return err,
    };
    if (usage_error) |want| return .{ .pending = try std.fmt.allocPrint(arena, "instance {s}: expected a usage error containing {s}; the call validates", .{ name, want }) };
    const mismatch = try compareInstance(arena, inst, result);
    if (xfail) |why| {
        if (mismatch == null) return .{ .regression = try std.fmt.allocPrint(arena, "instance {s} passes but Python xfails it ({s})", .{ name, why }) };
        return .pass;
    }
    if (mismatch) |m| return .{ .pending = try std.fmt.allocPrint(arena, "instance {s}: {s}", .{ name, m }) };
    return .pass;
}

fn jsonVal(arena: std.mem.Allocator, value: std.json.Value) !xyang.json_value.Val {
    const text = try std.json.Stringify.valueAlloc(arena, value, .{});
    var msg: []const u8 = "";
    return xyang.json_value.parse(arena, text, &msg);
}

fn xfailReason(case: std.json.ObjectMap, inst: std.json.ObjectMap) ?[]const u8 {
    if (inst.get("xfail")) |x| if (x == .object) if (x.object.get("python")) |r| return r.string;
    if (case.get("xfail")) |x| if (x == .object) if (x.object.get("python")) |r| return r.string;
    return null;
}

/// Null when the result matches the instance, else what differs.
fn compareInstance(arena: std.mem.Allocator, inst: std.json.ObjectMap, result: xyang.yang_validator.Result) !?[]const u8 {
    var got: std.StringArrayHashMapUnmanaged(void) = .empty;
    for (result.errors) |e| try got.put(arena, try where(arena, e.document, e.pointer, e.code), {});
    var want: std.StringArrayHashMapUnmanaged(void) = .empty;
    const expected: []const std.json.Value = if (inst.get("errors")) |e| e.array.items else &.{};
    for (expected) |e| {
        const doc = if (e.object.get("document")) |d| d.string else "data";
        try want.put(arena, try where(arena, doc, e.object.get("path").?.string, e.object.get("code").?.string), {});
    }
    var same = got.count() == want.count();
    for (want.keys()) |k| {
        if (!got.contains(k)) same = false;
    }
    if (!same) return try std.fmt.allocPrint(arena, "errors {s} != expected {s}", .{ try std.mem.join(arena, ", ", got.keys()), try std.mem.join(arena, ", ", want.keys()) });
    for (expected) |e| {
        const m = e.object.get("message") orelse continue;
        if (m != .string or m.string.len == 0) continue;
        const code = e.object.get("code").?.string;
        const found = for (result.errors) |r| {
            if (std.mem.eql(u8, r.code, code) and std.mem.indexOf(u8, r.message, m.string) != null) break true;
        } else false;
        if (!found) return try std.fmt.allocPrint(arena, "no {s} error message contains {s}", .{ code, m.string });
    }
    const valid = if (inst.get("valid")) |v| v == .bool and v.bool else false;
    if (valid != result.valid()) return try std.fmt.allocPrint(arena, "valid is {}, expected {}", .{ result.valid(), valid });
    return null;
}

/// `_where`: `path`, or `document:path` for an issue about another document.
fn where(arena: std.mem.Allocator, document: []const u8, path: []const u8, code: []const u8) ![]const u8 {
    if (std.mem.eql(u8, document, "data")) return std.fmt.allocPrint(arena, "({s} {s})", .{ path, code });
    return std.fmt.allocPrint(arena, "({s}:{s} {s})", .{ document, path, code });
}
