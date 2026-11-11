//! Entry points: parse a YANG file or string into a `Module` (mirrors
//! `src/xyang/parser/yang_parser.py`).
//!
//! Python finishes a load by expanding `uses`, merging `augment`, applying `deviation`
//! and running semantic checks. That is module resolution (phase 2 of #165). Until it
//! lands, a module whose top level depends on that work fails loudly instead of
//! reporting statement counts that differ from Python.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const Module = @import("../module.zig").Module;
const kw = @import("keywords.zig");
const tokenizer = @import("tokenizer.zig");
const sp = @import("statement_parsers.zig");
const module_parsers = @import("statements/module.zig");

pub const Diagnostic = errors.Diagnostic;
const Error = errors.Error;

/// Parse YANG source. `filename` is used in error messages, like Python's `filename=`.
/// Everything is allocated in `arena`.
pub fn parseString(arena: std.mem.Allocator, content: []const u8, filename: ?[]const u8, diag: *Diagnostic) Error!*Module {
    const tokens = tokenizer.tokenize(arena, content, diag) catch |err| {
        if (err == error.YangLoad) diag.filename = filename;
        return err;
    };
    const module = try arena.create(Module);
    module.* = .{};
    var p: sp.Parser = .{
        .ts = .{ .tokens = tokens, .arena = arena, .diag = diag, .filename = filename },
        .arena = arena,
        .module = module,
    };
    if (!p.ts.hasMore()) return p.ts.fail("Empty input", .{});
    if (p.ts.atValue(kw.MODULE)) {
        try module_parsers.parseModule(&p);
    } else if (p.ts.atValue(kw.SUBMODULE)) {
        try module_parsers.parseSubmodule(&p);
    } else {
        return p.ts.fail("Expected 'module' or 'submodule' statement at start of file", .{});
    }
    try propagateTypedefUnits(arena, module);
    try requireNoResolution(arena, module, filename, diag);
    return module;
}

/// Statements Python rewrites while finishing a load, which changes the top level.
fn requireNoResolution(arena: std.mem.Allocator, module: *const Module, filename: ?[]const u8, diag: *Diagnostic) Error!void {
    for (module.statements.items) |s| {
        const what: []const u8 = switch (s.kind()) {
            .uses => "a top-level 'uses'",
            .augment => "a top-level 'augment'",
            .deviation => "a top-level 'deviation'",
            else => continue,
        };
        diag.* = .{
            .kind = .unsupported,
            .message = try std.fmt.allocPrint(arena, "xyang-zig cannot expand {s} in module '{s}' yet (module resolution is phase 2 of #165)", .{ what, module.name }),
            .filename = filename,
        };
        return error.YangLoad;
    }
}

/// Copy typedef `units` onto leafs that use the typedef and set none of their own.
fn propagateTypedefUnits(arena: std.mem.Allocator, module: *Module) Error!void {
    const Walker = struct {
        arena: std.mem.Allocator,
        module: *Module,

        fn lookup(w: @This(), type_stmt: ?*ast.TypeStmt, seen: *std.StringHashMapUnmanaged(void)) Error![]const u8 {
            const t = type_stmt orelse return "";
            const key = try std.fmt.allocPrint(w.arena, "{s}\x00{s}", .{ t.prefix orelse "", t.name });
            if (seen.contains(key)) return "";
            try seen.put(w.arena, key, {});
            if (t.prefix) |pre| {
                if (w.module.resolvePrefixedModule(pre) == null) return "";
            }
            const td = w.module.typedefs.get(t.name) orelse return "";
            if (td.units.len > 0) return td.units;
            return w.lookup(td.data.typedef.type, seen);
        }

        fn walk(w: @This(), statements: []const *ast.Statement) Error!void {
            for (statements) |s| {
                switch (s.data) {
                    .leaf => |d| try w.fill(s, d.type),
                    .leaf_list => |d| try w.fill(s, d.type),
                    .choice => |d| for (d.cases.items) |c| try w.walk(c.statements.items),
                    .container => |d| for (d.groupings.values()) |g| try w.walk(g.statements.items),
                    else => {},
                }
                try w.walk(s.statements.items);
            }
        }

        fn fill(w: @This(), s: *ast.Statement, t: ?*ast.TypeStmt) Error!void {
            if (s.units.len > 0 or t == null) return;
            var seen: std.StringHashMapUnmanaged(void) = .empty;
            const found = try w.lookup(t, &seen);
            if (found.len > 0) s.units = found;
        }
    };
    const w: Walker = .{ .arena = arena, .module = module };
    try w.walk(module.statements.items);
    for (module.groupings.values()) |g| try w.walk(g.statements.items);
}

/// Read and parse a file like Python's `parse_yang_file`: the path is resolved, the text
/// is decoded as UTF-8 with universal newlines, and errors name the resolved path.
pub fn parseFile(arena: std.mem.Allocator, io: std.Io, path: []const u8, diag: *Diagnostic) Error!*Module {
    const cwd = std.Io.Dir.cwd();
    const resolved: []const u8 = cwd.realPathFileAlloc(io, path, arena) catch |err| return ioError(arena, diag, err, path);
    const raw = cwd.readFileAlloc(io, resolved, arena, .unlimited) catch |err| return ioError(arena, diag, err, resolved);
    if (firstUtf8Error(raw)) |bad| {
        diag.* = .{
            .kind = .io,
            .message = try std.fmt.allocPrint(arena, "'utf-8' codec can't decode byte 0x{x:0>2} in position {d}: {s}", .{ raw[bad.pos], bad.pos, bad.reason }),
        };
        return error.YangLoad;
    }
    return parseString(arena, try universalNewlines(arena, raw), resolved, diag);
}

fn ioError(arena: std.mem.Allocator, diag: *Diagnostic, err: anyerror, path: []const u8) Error {
    const errno_text: []const u8 = switch (err) {
        error.IsDir => "[Errno 21] Is a directory",
        error.AccessDenied, error.PermissionDenied => "[Errno 13] Permission denied",
        error.FileNotFound => "[Errno 2] No such file or directory",
        error.OutOfMemory => return error.OutOfMemory,
        else => @errorName(err),
    };
    diag.* = .{ .kind = .io, .message = try std.fmt.allocPrint(arena, "{s}: '{s}'", .{ errno_text, path }) };
    return error.YangLoad;
}

fn universalNewlines(arena: std.mem.Allocator, raw: []const u8) Error![]const u8 {
    if (std.mem.indexOfScalar(u8, raw, '\r') == null) return raw;
    var out = try std.ArrayList(u8).initCapacity(arena, raw.len);
    var i: usize = 0;
    while (i < raw.len) : (i += 1) {
        if (raw[i] == '\r') {
            out.appendAssumeCapacity('\n');
            if (i + 1 < raw.len and raw[i + 1] == '\n') i += 1;
        } else {
            out.appendAssumeCapacity(raw[i]);
        }
    }
    return out.items;
}

const Utf8Error = struct { pos: usize, reason: []const u8 };

/// The first byte Python's UTF-8 decoder rejects, with its reason text.
fn firstUtf8Error(s: []const u8) ?Utf8Error {
    var i: usize = 0;
    while (i < s.len) {
        const c = s[i];
        if (c < 0x80) {
            i += 1;
            continue;
        }
        const len = std.unicode.utf8ByteSequenceLength(c) catch return .{ .pos = i, .reason = "invalid start byte" };
        if (i + len > s.len) {
            for (s[i + 1 ..]) |cont| {
                if (cont & 0xc0 != 0x80) return .{ .pos = i, .reason = "invalid continuation byte" };
            }
            return .{ .pos = i, .reason = "unexpected end of data" };
        }
        _ = std.unicode.utf8Decode(s[i .. i + len]) catch return .{ .pos = i, .reason = "invalid continuation byte" };
        i += len;
    }
    return null;
}

test "parse a small module" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    const m = try parseString(arena.allocator(),
        \\module m {
        \\  yang-version 1.1;
        \\  namespace urn:m;
        \\  prefix m;
        \\  typedef t { type string { length "1..10"; } units "s"; }
        \\  container top {
        \\    leaf a { type t; mandatory "true"; }
        \\    choice c { leaf x { type string; } case y { leaf y { type int8; } } }
        \\  }
        \\}
    , "m.yang", &diag);
    try std.testing.expectEqualStrings("m", m.name);
    try std.testing.expectEqualStrings("urn:m", m.namespace);
    try std.testing.expectEqual(@as(usize, 1), m.typedefs.count());
    try std.testing.expectEqual(@as(usize, 1), m.statements.items.len);
    const top = m.statements.items[0];
    const leaf = top.statements.items[0];
    try std.testing.expect(leaf.data.leaf.mandatory);
    try std.testing.expectEqualStrings("s", leaf.units);
    const choice = top.statements.items[1];
    try std.testing.expectEqual(@as(usize, 2), choice.data.choice.cases.items.len);
    try std.testing.expectEqualStrings("x", choice.data.choice.cases.items[0].name);
}

fn expectError(source: []const u8, expected: []const u8) !void {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, parseString(arena.allocator(), source, "m.yang", &diag));
    var buf: [512]u8 = undefined;
    try std.testing.expectEqualStrings(expected, try std.fmt.bufPrint(&buf, "{f}", .{diag}));
}

test "syntax errors carry Python's text and line" {
    try expectError("module m {\n  leaf a {\n    type string;\n    mandatory yes;\n  }\n}", "m.yang: 4: mandatory argument must be 'true' or 'false', got 'yes'");
    try expectError("module m {\n  leaf a { foo; }\n}", "m.yang: 2: Invalid or unknown statement in leaf 'a': 'foo'");
    try expectError("module m {\n  input { }\n}", "m.yang: 2: 'input' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    try expectError("", "m.yang: 1: Empty input");
    try expectError("module m {\n  container c {\n", "m.yang: 2: Unexpected end of input");
    try expectError("module m { leaf a { type enumeration; } }", "m.yang: 1: enumeration type requires at least one \"enum\" statement (RFC 7950)");
    try expectError("module m { description foo; }", "m.yang: 1: Expected STRING, got IDENTIFIER ('foo')");
    try expectError("module m { choice c; }", "m.yang: 1: Invalid or unknown statement in module body: 'choice'");
    try expectError("module m { container t { choice c { leaf a { type string; } case b { leaf a { type string; } } } } }", "Choice 'c': schema node 'a' appears in case 'a' and again in case 'b' (RFC 7950: names of nodes in the cases of a choice must be unique).");
}

test "constructs needing module resolution fail loudly" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, parseString(arena.allocator(), "module m { prefix m; import n { prefix n; } }", "m.yang", &diag));
    try std.testing.expectEqual(errors.Kind.unsupported, diag.kind);
    try std.testing.expectError(error.YangLoad, parseString(arena.allocator(), "module m { prefix m; augment \"/m:x\" { leaf a { type string; } } }", "m.yang", &diag));
    try std.testing.expectEqual(errors.Kind.unsupported, diag.kind);
}

test "universal newlines" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    try std.testing.expectEqualStrings("a\nb\nc\n", try universalNewlines(arena.allocator(), "a\r\nb\rc\n"));
}
