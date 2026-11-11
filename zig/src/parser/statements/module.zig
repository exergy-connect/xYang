//! Module header, linkage and module-level definitions (mirrors `statements/module.py`,
//! `submodule.py`, `revision.py`, `feature.py`, `identity.py`, `extension.py`,
//! `augment.py` and `deviation.py`).

const std = @import("std");
const ast = @import("../../ast.zig");
const errors = @import("../../errors.zig");
const pyfmt = @import("../../pyfmt.zig");
const kw = @import("../keywords.zig");
const sp = @import("../statement_parsers.zig");

const Parser = sp.Parser;
const Parent = sp.Parent;
const Holder = sp.Holder;
const Error = errors.Error;
const repr = pyfmt.repr;

pub fn parseModule(p: *Parser) Error!void {
    _ = try p.ts.consume(kw.MODULE);
    p.module.name = try p.ts.consumeType(.identifier);
    _ = try p.ts.consumeType(.lbrace);
    while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
        try p.dispatchSubstatement(.module, .module, "module body");
    }
    _ = try p.ts.consumeType(.rbrace);
}

pub fn parseSubmodule(p: *Parser) Error!void {
    _ = try p.ts.consume(kw.SUBMODULE);
    p.module.name = try p.ts.consumeType(.identifier);
    _ = try p.ts.consumeType(.lbrace);
    while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
        if (p.ts.atValue(kw.BELONGS_TO)) {
            try parseBelongsTo(p);
        } else {
            try p.dispatchSubstatement(.module, .submodule, "submodule body");
        }
    }
    _ = try p.ts.consumeType(.rbrace);
}

fn parseBelongsTo(p: *Parser) Error!void {
    _ = try p.ts.consume(kw.BELONGS_TO);
    p.module.belongs_to_module = try p.ts.consumeType(.identifier);
    p.module.is_submodule = true;
    _ = try p.ts.consumeType(.lbrace);
    try p.parseBody(.discard, .belongs_to, "belongs-to");
    _ = try p.ts.consumeType(.rbrace);
    _ = p.ts.consumeIfType(.semicolon);
}

/// `import`: load the module and bind its prefix (`register_import`). An import without
/// a body binds nothing, like Python.
pub fn parseImport(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.IMPORT);
    const name = try p.ts.consumeType(.identifier);
    if (p.ts.consumeIfType(.semicolon)) return;
    if (!p.ts.consumeIfType(.lbrace)) return p.ts.fail("Expected '{{' or ';' after import module name", .{});
    var acc: Holder = .{};
    try p.parseBody(.{ .holder = &acc }, .import, "import");
    _ = try p.ts.consumeType(.rbrace);
    _ = p.ts.consumeIfType(.semicolon);
    if (acc.prefix) |prefix| {
        if (prefix.len > 0) try p.loader.registerImport(p, name, prefix, acc.revision_date);
    }
}

/// `include`: load the submodule and merge its definitions (`merge_included_submodule`).
pub fn parseInclude(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.INCLUDE);
    const name = try p.ts.consumeType(.identifier);
    var acc: Holder = .{};
    if (p.ts.consumeIfType(.lbrace)) {
        try p.parseBody(.{ .holder = &acc }, .include, "include");
        _ = try p.ts.consumeType(.rbrace);
    }
    _ = p.ts.consumeIfType(.semicolon);
    try p.loader.mergeIncludedSubmodule(p, name, acc.revision_date);
}

/// `prefix` inside `include` or `belongs-to`: syntax-checked, not stored.
pub fn parsePrefixValue(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.PREFIX);
    _ = try p.consumePrefixArgument();
    _ = p.ts.consumeIfType(.semicolon);
}

/// `prefix` inside `import`: the local prefix the imported module is bound to.
pub fn parseImportPrefix(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.PREFIX);
    const prefix = try p.consumePrefixArgument();
    switch (parent) {
        .holder => |h| h.prefix = prefix,
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// `revision-date` inside `import` or `include` (`parse_revision_date_statement`).
pub fn parseRevisionDate(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.REVISION_DATE);
    const tt0 = try p.ts.peekType();
    var date: []const u8 = undefined;
    if (tt0 == .string) {
        date = try p.ts.consumeType(.string);
    } else {
        var chunks: std.ArrayList(u8) = .empty;
        var n: usize = 0;
        while (p.ts.hasMore() and !p.ts.at(.semicolon)) {
            switch (try p.ts.peekType()) {
                .identifier, .dotted_number, .integer => {
                    try chunks.appendSlice(p.arena, try p.ts.consumeAny());
                    n += 1;
                },
                else => break,
            }
        }
        if (n == 0) return p.ts.fail("Expected revision-date value, got {s}", .{tt0.pyName()});
        date = chunks.items;
    }
    switch (parent) {
        .holder => |h| h.revision_date = date,
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseYangVersion(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.YANG_VERSION);
    const version = try p.parseStringArgument();
    if (!std.mem.eql(u8, version, "1") and !std.mem.eql(u8, version, "1.1")) {
        return p.ts.fail("yang-version argument must be '1' or '1.1', got {f}", .{repr(version)});
    }
    p.module.yang_version = version;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseNamespace(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.NAMESPACE);
    p.module.namespace = try p.parseStringArgument();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseModulePrefix(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.PREFIX);
    p.module.prefix = try p.consumePrefixArgument();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseOrganization(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.ORGANIZATION);
    p.module.organization = try p.ts.consumeType(.string);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseContact(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.CONTACT);
    p.module.contact = try p.ts.consumeType(.string);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRevision(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.REVISION);
    const tt0 = try p.ts.peekType();
    var date: []const u8 = undefined;
    if (tt0 == .string) {
        date = try p.ts.consumeType(.string);
    } else {
        var chunks: std.ArrayList(u8) = .empty;
        while (p.ts.hasMore() and !p.ts.at(.lbrace) and !p.ts.at(.semicolon)) {
            switch (try p.ts.peekType()) {
                .identifier, .dotted_number, .integer => try chunks.appendSlice(p.arena, try p.ts.consumeAny()),
                else => break,
            }
        }
        if (chunks.items.len == 0) return p.ts.fail("Expected revision date, got {s}", .{tt0.pyName()});
        date = chunks.items;
    }
    var body: Holder = .{};
    try p.parseOptionalBlock(.{ .holder = &body }, .revision, "revision");
    try p.module.revisions.append(p.arena, .{ .date = date, .description = body.description, .reference = body.reference });
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseFeature(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.FEATURE);
    const name = try p.ts.consumeType(.identifier);
    try p.module.features.put(p.arena, name, {});
    if (p.ts.consumeIfType(.lbrace)) {
        var holder: Holder = .{};
        try p.parseBody(.{ .holder = &holder }, .feature, try p.label("feature '{s}'", .{name}));
        _ = try p.ts.consumeType(.rbrace);
        if (holder.if_features.items.len > 0) {
            if (p.module.feature_if_features.contains(name)) {
                return p.ts.fail("Duplicate if-feature block for feature {f}", .{repr(name)});
            }
            try p.module.feature_if_features.put(p.arena, name, holder.if_features);
        }
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// `if-feature`: the expression is stored on the parent (evaluated in a later phase).
pub fn parseIfFeature(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.IF_FEATURE);
    var expression = try p.parseStringArgument();
    if (p.ts.at(.colon)) {
        _ = try p.ts.consumeType(.colon);
        expression = try p.label("{s}:{s}", .{ expression, try p.ts.consumeAny() });
    }
    switch (parent) {
        .stmt => |s| if (s.hasIfFeatures()) try s.if_features.append(p.arena, expression),
        .holder => |h| try h.if_features.append(p.arena, expression),
        else => {},
    }
    try p.parseOptionalBlock(parent, .if_feature, "if-feature substatement");
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseIdentity(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.IDENTITY);
    const name = try p.ts.consumeType(.identifier);
    const stmt = try p.newStatement(name, .{ .identity = .{} });
    try p.parseOptionalBlock(.{ .stmt = stmt }, .identity, try p.label("identity '{s}'", .{name}));
    try p.module.identities.put(p.arena, name, stmt);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseIdentityBase(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.BASE);
    const ref = try p.consumeIdentifierRef();
    switch (parent) {
        .stmt => |s| switch (s.data) {
            .identity => |*d| try d.bases.append(p.arena, ref),
            else => {},
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseExtension(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.EXTENSION);
    const name = try p.ts.consumeType(.identifier);
    const ext = try p.newStatement(name, .{ .extension = .{ .module_name = p.module.name } });
    try p.parseOptionalBlock(.{ .stmt = ext }, .extension, try p.label("extension '{s}'", .{name}));
    _ = p.ts.consumeIfType(.semicolon);
    try p.module.extensions.put(p.arena, name, ext);
    try p.addToParentOrModule(parent, ext);
}

pub fn parseExtensionArgument(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.ARGUMENT);
    const tt = try p.ts.peekType();
    const arg = switch (tt) {
        .string, .identifier => try p.ts.consumeAny(),
        else => return p.ts.fail("Expected extension argument identifier/string, got {s}", .{tt.pyName()}),
    };
    if (extensionOf(parent)) |d| d.argument_name = arg;
    try p.parseOptionalBlock(parent, .argument, "extension argument");
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseYinElement(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.YIN_ELEMENT);
    const value = try p.parseBooleanArgument(kw.YIN_ELEMENT);
    if (extensionOf(parent)) |d| d.argument_yin_element = value;
    _ = p.ts.consumeIfType(.semicolon);
}

fn extensionOf(parent: Parent) ?*@FieldType(ast.Data, "extension") {
    return switch (parent) {
        .stmt => |s| switch (s.data) {
            .extension => |*d| d,
            else => null,
        },
        else => null,
    };
}

/// `parse_absolute_schema_path`: `/prefix:a/prefix:b` into prefixed segments. Errors are
/// `YangSyntaxError(str(ValueError))` in Python, so they carry no location.
fn parseAbsoluteSchemaPath(p: *Parser, path: []const u8, out: *std.ArrayList(ast.IdentifierRef)) Error!void {
    const raw = std.mem.trim(u8, std.mem.trim(u8, std.mem.trim(u8, path, &std.ascii.whitespace), "\""), "'");
    if (!std.mem.startsWith(u8, raw, "/")) {
        return p.ts.failUnlocated(.syntax, "Schema path must be absolute, got {f}", .{repr(path)});
    }
    var it = std.mem.splitScalar(u8, raw[1..], '/');
    var count: usize = 0;
    while (it.next()) |part| {
        const seg = std.mem.trim(u8, part, &std.ascii.whitespace);
        if (seg.len == 0) continue;
        count += 1;
        const idx = std.mem.indexOfScalar(u8, seg, ':');
        if (idx == null or idx.? == 0 or idx.? >= seg.len - 1) {
            return p.ts.failUnlocated(.syntax, "Invalid schema path segment {f}: expected 'prefix:identifier'", .{repr(seg)});
        }
        try out.append(p.arena, .{ .prefix = seg[0..idx.?], .name = seg[idx.? + 1 ..] });
    }
    if (count == 0) return p.ts.failUnlocated(.syntax, "Empty schema path: {f}", .{repr(path)});
}

pub fn parseAugment(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.AUGMENT);
    const path = try p.parseStringConcatenation();
    const aug = try p.newStatement("augment", .{ .augment = .{ .augment_path = path } });
    const raw = std.mem.trim(u8, std.mem.trim(u8, std.mem.trim(u8, path, &std.ascii.whitespace), "\""), "'");
    if (std.mem.startsWith(u8, raw, "/")) try parseAbsoluteSchemaPath(p, path, &aug.data.augment.augment_path_segments);
    try p.parseOptionalBlock(.{ .stmt = aug }, .augment, "augment");
    switch (parent) {
        .stmt => |s| switch (s.data) {
            .uses => |*u| try u.augmentations.append(p.arena, aug),
            else => try p.addToParentOrModule(parent, aug),
        },
        else => try p.addToParentOrModule(parent, aug),
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseDeviation(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DEVIATION);
    if ((try p.ts.peekType()) != .string) return p.ts.fail("deviation argument must be a quoted absolute schema path", .{});
    const path = try p.parseStringConcatenation();
    const dev = try p.newStatement("deviation", .{ .deviation = .{ .target_path = path } });
    try parseAbsoluteSchemaPath(p, path, &dev.data.deviation.target_path_segments);
    try p.parseOptionalBlock(.{ .stmt = dev }, .deviation, "deviation");
    try p.addToParentOrModule(parent, dev);
    _ = p.ts.consumeIfType(.semicolon);
}

/// `deviate not-supported` is recorded. `add`, `replace` and `delete` are not applied:
/// like Python, the load warns `Ignoring unsupported 'deviate KIND' for PATH` and skips
/// the braced body.
pub fn parseDeviate(p: *Parser, parent: Parent) Error!void {
    const dev = switch (parent) {
        .stmt => |s| switch (s.data) {
            .deviation => |*d| d,
            else => return p.ts.fail("internal: deviate outside deviation", .{}),
        },
        else => return p.ts.fail("internal: deviate outside deviation", .{}),
    };
    _ = try p.ts.consume(kw.DEVIATE);
    if ((try p.ts.peekType()) != .identifier) return p.ts.fail("Expected deviate argument, got {f}", .{repr(p.ts.peek().?)});
    const kind = try p.ts.consumeType(.identifier);
    if (std.mem.eql(u8, kind, kw.NOT_SUPPORTED)) {
        dev.not_supported = true;
        _ = p.ts.consumeIfType(.semicolon);
        return;
    }
    for (kw.UNSUPPORTED_DEVIATE_KINDS) |k| {
        if (!std.mem.eql(u8, kind, k)) continue;
        try p.loader.warn("Ignoring unsupported 'deviate {s}' for {s}", .{ kind, dev.target_path });
        if (p.ts.at(.lbrace)) try sp.consumeBalancedBraces(p);
        _ = p.ts.consumeIfType(.semicolon);
        return;
    }
    return p.ts.fail("Unknown deviate argument {f}", .{repr(kind)});
}
