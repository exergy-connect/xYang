//! Entry points and module resolution: parse a YANG file or string into a `Module`
//! (mirrors `src/xyang/parser/yang_parser.py`).
//!
//! `Loader` is Python's `YangParser`: it loads `import`ed modules (cached per resolved
//! path, so every importer shares one module object) and merges `include`d submodules.
//! A finished load expands `uses` and `refine`, merges `augment`, applies `deviation`,
//! applies extension invocations and runs the semantic checks, in Python's order.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const pyfmt = @import("../pyfmt.zig");
const Module = @import("../module.zig").Module;
const kw = @import("keywords.zig");
const tokenizer = @import("tokenizer.zig");
const sp = @import("statement_parsers.zig");
const module_parsers = @import("statements/module.zig");
const uses_expand = @import("../uses_expand.zig");
const augment_expand = @import("../augment_expand.zig");
const capabilities = @import("../ext/capabilities.zig");
const semantic_validate = @import("../semantic_validate.zig");

pub const Diagnostic = errors.Diagnostic;
const Error = errors.Error;
const repr = pyfmt.repr;

/// Same submodule and same statement, reached again through another include, is one definition.
fn skipSameInclude(existing: ?*ast.Statement, stmt: *ast.Statement, sub_name: []const u8) bool {
    const origin = stmt.included_from orelse sub_name;
    stmt.included_from = origin;
    const prior = existing orelse return false;
    if (prior == stmt) return true;
    const tagged = prior.included_from orelse return false;
    return std.mem.eql(u8, tagged, origin);
}

pub const Loader = struct {
    arena: std.mem.Allocator,
    /// Needed to read files; `parseString` without a source path never touches it.
    io: ?std.Io,
    reporter: errors.Reporter,
    /// Extra directories searched for `import` and `include` after the importing file's.
    include_path: []const []const u8 = &.{},
    /// Python's `expand_uses`: false keeps `uses`, `augment` and `deviation` as written.
    expand_uses: bool = true,
    /// Imported modules by resolved path. `parseFile` does not add to it; `cache` does.
    module_cache: std.StringArrayHashMapUnmanaged(*Module) = .empty,
    import_pending: std.StringArrayHashMapUnmanaged(void) = .empty,
    include_stack: std.ArrayList([]const u8) = .empty,

    pub fn init(arena: std.mem.Allocator, io: ?std.Io, diag: *Diagnostic, include_path: []const []const u8) Loader {
        return .{ .arena = arena, .io = io, .reporter = .{ .arena = arena, .diag = diag }, .include_path = include_path };
    }

    pub fn warnings(self: *const Loader) []const []const u8 {
        return self.reporter.warnings.items;
    }

    pub fn warn(self: *Loader, comptime fmt: []const u8, args: anytype) Error!void {
        return self.reporter.warn(fmt, args);
    }

    /// Record `module` as the load of `path` (resolved), so a later import of that file
    /// gets this object.
    pub fn cache(self: *Loader, path: []const u8, module: *Module) Error!void {
        try self.module_cache.put(self.arena, path, module);
    }

    /// `parse_file`: resolve the path, return the cached module for it, else parse and
    /// finish the load. `include` resolves relative to the file's directory.
    pub fn parseFile(self: *Loader, path: []const u8) Error!*Module {
        const io = self.io.?;
        const resolved = std.Io.Dir.cwd().realPathFileAlloc(io, path, self.arena) catch |err| return ioError(self.arena, self.reporter.diag, err, path);
        if (self.module_cache.get(resolved)) |cached| return cached;
        self.import_pending.clearRetainingCapacity();
        const saved = self.include_stack;
        self.include_stack = .empty;
        try self.include_stack.append(self.arena, resolved);
        defer self.include_stack = saved;
        const content = try readSource(self.arena, io, resolved, self.reporter.diag);
        const module = try self.parseString(content, resolved, resolved, false);
        try self.finish(module);
        return module;
    }

    /// `parse_string`. `source_path` (resolved) locates `import` and `include`; without it
    /// they fail like Python. `finalize` finishes the load.
    pub fn parseString(self: *Loader, content: []const u8, filename: ?[]const u8, source_path: ?[]const u8, finalize: bool) Error!*Module {
        const tokens = tokenizer.tokenize(self.arena, content, self.reporter.diag) catch |err| {
            if (err == error.YangLoad) self.reporter.diag.filename = filename;
            return err;
        };
        const module = try self.arena.create(Module);
        module.* = .{};
        var p: sp.Parser = .{
            .ts = .{ .tokens = tokens, .arena = self.arena, .diag = self.reporter.diag, .filename = filename },
            .arena = self.arena,
            .module = module,
            .loader = self,
            .source_dir = if (source_path) |s| std.fs.path.dirname(s) orelse "/" else null,
        };
        if (!p.ts.hasMore()) return p.ts.fail("Empty input", .{});
        if (p.ts.atValue(kw.MODULE)) {
            try module_parsers.parseModule(&p);
        } else if (p.ts.atValue(kw.SUBMODULE)) {
            try module_parsers.parseSubmodule(&p);
        } else {
            return p.ts.fail("Expected 'module' or 'submodule' statement at start of file", .{});
        }
        try propagateTypedefUnits(self.arena, module);
        if (finalize) try self.finish(module);
        return module;
    }

    /// `_expand_and_augment`.
    fn finish(self: *Loader, module: *Module) Error!void {
        if (!self.expand_uses) return;
        const r = &self.reporter;
        try uses_expand.expandAllUsesInModule(r, module);
        try augment_expand.applyAugmentations(r, module);
        try augment_expand.applyDeviations(r, module);
        try capabilities.applyExtensionInvocations(r, module);
        try semantic_validate.validateSemantics(r, module);
    }

    /// `register_import`: load the module and bind `local_prefix` to it on the parser's module.
    pub fn registerImport(self: *Loader, p: *sp.Parser, name: []const u8, local_prefix: []const u8, revision_date: ?[]const u8) Error!void {
        const source_dir = p.source_dir orelse return p.ts.fail(
            "import requires a filesystem location: use parse_file(), or parse_string(..., source_path=Path('module.yang'))",
            .{},
        );
        const parent = p.module;
        if (std.mem.eql(u8, local_prefix, parent.ownPrefix())) {
            return p.ts.fail("Import prefix {f} must differ from this module's prefix", .{repr(local_prefix)});
        }
        if (parent.import_prefixes.contains(local_prefix)) return p.ts.fail("Duplicate import prefix {f}", .{repr(local_prefix)});
        const mod = try self.loadImportedModule(p, name, revision_date, source_dir);
        if (!std.mem.eql(u8, mod.name, name)) {
            return p.ts.fail("imported file defines module {f}, import expects {f}", .{ repr(mod.name), repr(name) });
        }
        try parent.import_prefixes.put(self.arena, local_prefix, mod);
    }

    fn loadImportedModule(self: *Loader, p: *sp.Parser, name: []const u8, revision_date: ?[]const u8, source_dir: []const u8) Error!*Module {
        const path = try self.resolveModuleFile(p, name, revision_date, source_dir, "module");
        if (self.module_cache.get(path)) |cached| return cached;
        if (self.import_pending.contains(path)) {
            self.reporter.diag.* = .{ .message = try std.fmt.allocPrint(self.arena, "Circular import: {s}", .{path}), .filename = path };
            return error.YangLoad;
        }
        try self.import_pending.put(self.arena, path, {});
        defer _ = self.import_pending.swapRemove(path);
        // The inner Python parser starts with its own empty include stack.
        const saved = self.include_stack;
        self.include_stack = .empty;
        defer self.include_stack = saved;
        const content = try readSource(self.arena, self.io.?, path, self.reporter.diag);
        const mod = try self.parseString(content, path, path, false);
        try self.finish(mod);
        try self.module_cache.put(self.arena, path, mod);
        return mod;
    }

    /// `_resolve_module_file`: `name@revision.yang` then `name.yang` in each directory, then
    /// the last `name@*.yang` of the first directory that has one. A requested revision
    /// that is not the file opened is a warning.
    fn resolveModuleFile(self: *Loader, p: *sp.Parser, name: []const u8, revision_date: ?[]const u8, source_dir: []const u8, kind: []const u8) Error![]const u8 {
        const io = self.io.?;
        const cwd = std.Io.Dir.cwd();
        var dirs: std.ArrayList([]const u8) = .empty;
        try dirs.append(self.arena, source_dir);
        try dirs.appendSlice(self.arena, self.include_path);
        var candidates: std.ArrayList([]const u8) = .empty;
        if (revision_date) |rev| try candidates.append(self.arena, try std.fmt.allocPrint(self.arena, "{s}@{s}.yang", .{ name, rev }));
        try candidates.append(self.arena, try std.fmt.allocPrint(self.arena, "{s}.yang", .{name}));

        var found: ?[]const u8 = null;
        search: for (dirs.items) |dir| {
            for (candidates.items) |candidate| {
                const path = try std.fs.path.join(self.arena, &.{ dir, candidate });
                const st = cwd.statFile(io, path, .{}) catch continue;
                if (st.kind != .file) continue;
                found = cwd.realPathFileAlloc(io, path, self.arena) catch |err| return ioError(self.arena, self.reporter.diag, err, path);
                break :search;
            }
        }
        if (found == null) {
            const glob_prefix = try std.fmt.allocPrint(self.arena, "{s}@", .{name});
            for (dirs.items) |dir| {
                var d = cwd.openDir(io, dir, .{ .iterate = true }) catch continue;
                defer d.close(io);
                var best: ?[]const u8 = null;
                var it = d.iterate();
                while (it.next(io) catch null) |entry| {
                    if (!std.mem.startsWith(u8, entry.name, glob_prefix) or !std.mem.endsWith(u8, entry.name, ".yang")) continue;
                    if (entry.name.len < glob_prefix.len + ".yang".len) continue;
                    if (best == null or std.mem.order(u8, entry.name, best.?) == .gt) best = try self.arena.dupe(u8, entry.name);
                }
                if (best) |b| {
                    const path = try std.fs.path.join(self.arena, &.{ dir, b });
                    found = cwd.realPathFileAlloc(io, path, self.arena) catch |err| return ioError(self.arena, self.reporter.diag, err, path);
                    break;
                }
            }
        }
        const path = found orelse {
            var tried: std.Io.Writer.Allocating = .init(self.arena);
            const w = &tried.writer;
            w.writeByte('[') catch return error.OutOfMemory;
            for (candidates.items, 0..) |c, i| {
                if (i != 0) w.writeAll(", ") catch return error.OutOfMemory;
                w.print("{f}", .{repr(c)}) catch return error.OutOfMemory;
            }
            w.writeByte(']') catch return error.OutOfMemory;
            const searched = try std.mem.join(self.arena, ", ", dirs.items);
            return p.ts.fail("Could not find {s} {f} (tried filenames {s}) under [{s}]", .{ kind, repr(name), tried.written(), searched });
        };
        if (revision_date) |rev| {
            const expected = candidates.items[0];
            const base = std.fs.path.basename(path);
            if (!std.mem.eql(u8, base, expected)) {
                const statement = if (std.mem.eql(u8, kind, "module")) "import" else "include";
                try self.warn("{s} {f} revision-date {s} not found; using {s}", .{ statement, repr(name), rev, base });
            }
        }
        return path;
    }

    /// `merge_included_submodule`: load the submodule and merge its definitions.
    pub fn mergeIncludedSubmodule(self: *Loader, p: *sp.Parser, name: []const u8, revision_date: ?[]const u8) Error!void {
        const source_dir = p.source_dir orelse return p.ts.fail(
            "include requires a filesystem location for the submodule: use parse_file(), or parse_string(..., source_path=Path('module.yang'))",
            .{},
        );
        const path = try self.resolveModuleFile(p, name, revision_date, source_dir, "submodule");
        const sub = try self.parseSubmoduleFromPath(path);
        if (!std.mem.eql(u8, sub.name, name)) {
            return p.ts.fail("submodule file defines name {f}, include expects {f}", .{ repr(sub.name), repr(name) });
        }
        const parent = p.module;
        const owner = if (parent.belongs_to_module.len > 0) parent.belongs_to_module else parent.name;
        if (sub.belongs_to_module.len > 0 and !std.mem.eql(u8, sub.belongs_to_module, owner)) {
            return p.ts.fail("submodule belongs-to {f} does not match module {f}", .{ repr(sub.belongs_to_module), repr(owner) });
        }
        try self.mergeSubmoduleDefinitions(p, parent, sub);
    }

    fn parseSubmoduleFromPath(self: *Loader, path: []const u8) Error!*Module {
        for (self.include_stack.items) |open| {
            if (std.mem.eql(u8, open, path)) {
                self.reporter.diag.* = .{ .message = try std.fmt.allocPrint(self.arena, "Circular submodule include: {s}", .{path}), .filename = path };
                return error.YangLoad;
            }
        }
        try self.include_stack.append(self.arena, path);
        defer _ = self.include_stack.pop();
        const content = try readSource(self.arena, self.io.?, path, self.reporter.diag);
        return self.parseString(content, path, path, false);
    }

    /// `_merge_submodule_definitions`: one submodule reached through two includes is one
    /// definition. Two distinct definitions of the same name still fail.
    fn mergeSubmoduleDefinitions(self: *Loader, p: *sp.Parser, parent: *Module, sub: *Module) Error!void {
        const a = self.arena;
        for (sub.typedefs.keys(), sub.typedefs.values()) |n, td| {
            const origin = td.data.typedef.included_from orelse sub.name;
            td.data.typedef.included_from = origin;
            if (parent.typedefs.get(n)) |existing| {
                const same_origin = if (existing.data.typedef.included_from) |o| std.mem.eql(u8, o, origin) else false;
                if (existing == td or same_origin) continue;
                return p.ts.fail("Duplicate typedef {f} from include of {f}", .{ repr(n), repr(sub.name) });
            }
            try @import("../typedef_scope.zig").register(&self.reporter, parent, td);
        }
        for (sub.identities.keys(), sub.identities.values()) |n, ident| {
            if (skipSameInclude(parent.identities.get(n), ident, sub.name)) continue;
            if (parent.identities.contains(n)) return p.ts.fail("Duplicate identity {f} from include of {f}", .{ repr(n), repr(sub.name) });
            try parent.identities.put(a, n, ident);
        }
        for (sub.groupings.keys(), sub.groupings.values()) |n, grp| {
            if (skipSameInclude(parent.groupings.get(n), grp, sub.name)) continue;
            if (parent.groupings.contains(n)) return p.ts.fail("Duplicate grouping {f} from include of {f}", .{ repr(n), repr(sub.name) });
            try parent.groupings.put(a, n, grp);
        }
        for (sub.features.keys()) |fname| {
            const origin = sub.feature_included_from.get(fname) orelse sub.name;
            if (parent.features.contains(fname)) {
                const existing = parent.feature_included_from.get(fname);
                if (existing != null and std.mem.eql(u8, existing.?, origin)) continue;
                return p.ts.fail("Duplicate feature {f} from include of {f}", .{ repr(fname), repr(sub.name) });
            }
            try parent.features.put(a, fname, {});
            try parent.feature_included_from.put(a, fname, origin);
        }
        for (sub.feature_if_features.keys(), sub.feature_if_features.values()) |fname, ifs| {
            const origin = sub.feature_if_included_from.get(fname) orelse sub.name;
            if (parent.feature_if_features.contains(fname)) {
                const existing = parent.feature_if_included_from.get(fname);
                if (existing != null and std.mem.eql(u8, existing.?, origin)) continue;
                return p.ts.fail("Duplicate feature if-feature for {f} from include of {f}", .{ repr(fname), repr(sub.name) });
            }
            try parent.feature_if_features.put(a, fname, try ifs.clone(a));
            try parent.feature_if_included_from.put(a, fname, origin);
        }
        const own = parent.ownPrefix();
        for (sub.import_prefixes.keys(), sub.import_prefixes.values()) |pref, im| {
            if (std.mem.eql(u8, pref, own)) continue;
            if (parent.import_prefixes.get(pref)) |existing| {
                if (!std.mem.eql(u8, existing.name, im.name)) {
                    return p.ts.fail("Import prefix {f} from include of {f} conflicts with existing import of {f}", .{ repr(pref), repr(sub.name), repr(existing.name) });
                }
                continue;
            }
            try parent.import_prefixes.put(a, pref, im);
        }
        for (sub.statements.items) |stmt| {
            const origin = stmt.included_from orelse sub.name;
            stmt.included_from = origin;
            if (parent.included_submodules.contains(origin)) continue;
            try parent.statements.append(a, stmt);
            try parent.included_submodules.put(a, origin, {});
        }
        try parent.included_submodules.put(a, sub.name, {});
        sub.included_parent = parent;
        sub.statements = .empty;
        sub.typedefs = .empty;
        sub.identities = .empty;
        sub.groupings = .empty;
        sub.features = .empty;
        sub.feature_if_features = .empty;
        sub.feature_included_from = .empty;
        sub.feature_if_included_from = .empty;
        sub.import_prefixes = .empty;
    }
};

/// Parse YANG source with no file location (`parse_yang_string` without `source_path`):
/// `import` and `include` fail. `filename` is used in error messages.
pub fn parseString(arena: std.mem.Allocator, content: []const u8, filename: ?[]const u8, diag: *Diagnostic) Error!*Module {
    var loader = Loader.init(arena, null, diag, &.{});
    return loader.parseString(content, filename, null, true);
}

/// Read and parse a file like Python's `parse_yang_file`: the path is resolved, the text
/// is decoded as UTF-8 with universal newlines, and errors name the resolved path.
pub fn parseFile(arena: std.mem.Allocator, io: std.Io, path: []const u8, diag: *Diagnostic) Error!*Module {
    var loader = Loader.init(arena, io, diag, &.{});
    return loader.parseFile(path);
}

/// Copy typedef `units` onto leafs that use the typedef and set none of their own.
fn propagateTypedefUnits(arena: std.mem.Allocator, module: *Module) Error!void {
    const Walker = struct {
        arena: std.mem.Allocator,
        module: *Module,

        fn lookup(w: @This(), type_stmt: ?*ast.TypeStmt, mod: *Module, seen: *std.StringHashMapUnmanaged(void)) Error![]const u8 {
            const t = type_stmt orelse return "";
            const key = try std.fmt.allocPrint(w.arena, "{x}\x00{s}\x00{s}", .{ @intFromPtr(mod), t.prefix orelse "", t.name });
            if (seen.contains(key)) return "";
            try seen.put(w.arena, key, {});
            const resolved = @import("../module.zig").resolveTypedef(t, mod) orelse return "";
            const target = resolved.module;
            const td = resolved.typedef;
            if (td.units.len > 0) return td.units;
            return w.lookup(td.data.typedef.type, target, seen);
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
            const found = try w.lookup(t, w.module, &seen);
            if (found.len > 0) s.units = found;
        }
    };
    const w: Walker = .{ .arena = arena, .module = module };
    try w.walk(module.statements.items);
    for (module.groupings.values()) |g| try w.walk(g.statements.items);
}

/// The file as Python's `read_text(encoding="utf-8")` returns it.
fn readSource(arena: std.mem.Allocator, io: std.Io, path: []const u8, diag: *Diagnostic) Error![]const u8 {
    const raw = std.Io.Dir.cwd().readFileAlloc(io, path, arena, .unlimited) catch |err| return ioError(arena, diag, err, path);
    if (firstUtf8Error(raw)) |bad| {
        diag.* = .{
            .kind = .io,
            .message = try std.fmt.allocPrint(arena, "'utf-8' codec can't decode byte 0x{x:0>2} in position {d}: {s}", .{ raw[bad.pos], bad.pos, bad.reason }),
        };
        return error.YangLoad;
    }
    return universalNewlines(arena, raw);
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
    try expectError("module m { leaf \"a b\"; }", "m.yang: 1: leaf argument must be an identifier, got 'a b'");
    try expectError("module m { choice c; }", "m.yang: 1: Invalid or unknown statement in module body: 'choice'");
    try expectError("module m { container t { choice c { leaf a { type string; } case b { leaf a { type string; } } } } }", "Choice 'c': schema node 'a' appears in case 'a' and again in case 'b' (RFC 7950: names of nodes in the cases of a choice must be unique).");
}

test "import and include without a file location fail like Python" {
    try expectError("module m { prefix m; import n { prefix n; } }", "m.yang: 1: import requires a filesystem location: use parse_file(), or parse_string(..., source_path=Path('module.yang'))");
    try expectError("module m {\n  prefix m;\n  include s;\n}", "m.yang: 4: include requires a filesystem location for the submodule: use parse_file(), or parse_string(..., source_path=Path('module.yang'))");
}

test "deviate add is a warning, not applied" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    var loader = Loader.init(arena.allocator(), null, &diag, &.{});
    const m = try loader.parseString(
        \\module m { prefix m;
        \\  leaf a { type string; }
        \\  deviation "/m:a" { deviate add { default "x"; } }
        \\}
    , "m.yang", null, true);
    try std.testing.expectEqual(@as(usize, 1), m.statements.items.len);
    try std.testing.expect(m.statements.items[0].data.leaf.default == null);
    try std.testing.expectEqual(@as(usize, 1), loader.warnings().len);
    try std.testing.expectEqualStrings("Ignoring unsupported 'deviate add' for /m:a", loader.warnings()[0]);
}

test "imports are shared; foreign augment edits the import, foreign deviation a copy" {
    const io = std.testing.io;
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();
    try tmp.dir.writeFile(io, .{ .sub_path = "base.yang", .data =
        \\module base { prefix b;
        \\  typedef name-t { type string; units "chars"; }
        \\  grouping g { typedef inner-t { type string; } leaf a { type name-t; } leaf i { type inner-t; } }
        \\  container box { leaf gone { type string; } leaf kept { type string; } }
        \\}
    });
    try tmp.dir.writeFile(io, .{ .sub_path = "m.yang", .data =
        \\module m { prefix m;
        \\  import base { prefix x; }
        \\  include m-sub;
        \\  container top { uses x:g; uses sub-g; }
        \\  augment "/x:box" { leaf extra { type string; } }
        \\  deviation "/x:box/x:gone" { deviate not-supported; }
        \\}
    });
    try tmp.dir.writeFile(io, .{ .sub_path = "m-sub.yang", .data =
        \\submodule m-sub { belongs-to m { prefix m; }
        \\  feature f;
        \\  identity id;
        \\  grouping sub-g { leaf s { if-feature f; type string; } }
        \\}
    });
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const dir = try tmp.dir.realPathFileAlloc(io, ".", a);
    var diag: Diagnostic = .{};
    var loader = Loader.init(a, io, &diag, &.{});
    const m = loader.parseFile(try std.fs.path.join(a, &.{ dir, "m.yang" })) catch |err| {
        std.debug.print("{f}\n", .{diag});
        return err;
    };
    const cached = loader.module_cache.get(try std.fs.path.join(a, &.{ dir, "base.yang" })).?;
    const box = cached.statements.items[0];
    // The augment lands in the cached module; the deviation does not.
    try std.testing.expectEqual(@as(usize, 3), box.statements.items.len);
    try std.testing.expectEqualStrings("m", box.statements.items[2].defining_module.?);
    const private = m.import_prefixes.get("x").?;
    try std.testing.expect(private != cached);
    try std.testing.expectEqual(@as(usize, 2), private.statements.items[0].statements.items.len);
    try std.testing.expectEqualStrings("kept", private.statements.items[0].statements.items[0].name);
    // uses of an imported grouping and of a submodule grouping.
    const top = m.statements.items[0];
    try std.testing.expectEqualStrings("a", top.statements.items[0].name);
    try std.testing.expectEqualStrings("chars", top.statements.items[0].units);
    // Imported grouping types retain their declaration module instead of leaking here.
    try std.testing.expect(!m.typedefs.contains("inner-t"));
    try std.testing.expect(!m.typedefs.contains("name-t"));
    try std.testing.expectEqualStrings("f", top.statements.items[2].if_features.items[0]);
    try std.testing.expect(m.features.contains("f"));
    try std.testing.expect(m.identities.contains("id"));
    try std.testing.expectEqual(@as(usize, 1), m.statements.items.len);
}

test "universal newlines" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    try std.testing.expectEqualStrings("a\nb\nc\n", try universalNewlines(arena.allocator(), "a\r\nb\rc\n"));
}

test "length restriction retains all source metadata in its specialized payload" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    const m = try parseString(arena.allocator(),
        \\module m { namespace "urn:m"; prefix m;
        \\  leaf value { type string { length "1..4" {
        \\    error-message "bad length"; error-app-tag "length-tag";
        \\    description "length description"; reference "length reference";
        \\  } } }
        \\}
    , "m.yang", &diag);
    const t = m.statements.items[0].data.leaf.type.?;
    try std.testing.expectEqual(ast.TypeKind.string, t.kind());
    const restriction = t.lengthRestriction();
    try std.testing.expectEqualStrings("1..4", restriction.expression.?);
    try std.testing.expectEqualStrings("bad length", restriction.error_message.?);
    try std.testing.expectEqualStrings("length-tag", restriction.error_app_tag.?);
    try std.testing.expectEqualStrings("length description", restriction.description);
    try std.testing.expectEqualStrings("length reference", restriction.reference);
}

test "range restriction retains all source metadata in its specialized payload" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: Diagnostic = .{};
    const m = try parseString(arena.allocator(),
        \\module m { namespace "urn:m"; prefix m;
        \\  leaf value { type uint8 { range "1..4" {
        \\    error-message "bad range"; error-app-tag "range-tag";
        \\    description "range description"; reference "range reference";
        \\  } } }
        \\}
    , "m.yang", &diag);
    const t = m.statements.items[0].data.leaf.type.?;
    try std.testing.expectEqual(ast.TypeKind.numeric, t.kind());
    const restriction = t.rangeRestriction();
    try std.testing.expectEqualStrings("1..4", restriction.expression.?);
    try std.testing.expectEqualStrings("bad range", restriction.error_message.?);
    try std.testing.expectEqualStrings("range-tag", restriction.error_app_tag.?);
    try std.testing.expectEqualStrings("range description", restriction.description);
    try std.testing.expectEqualStrings("range reference", restriction.reference);
}
