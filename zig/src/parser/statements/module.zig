//! Module header, linkage and module-level definitions (mirrors `statements/module.py`,
//! `submodule.py`, `revision.py`, `feature.py`, `identity.py`, `extension.py`,
//! `augment.py` and `deviation.py`).

const std = @import("std");
const ast = @import("../../ast.zig");
const errors = @import("../../errors.zig");
const pyfmt = @import("../../pyfmt.zig");
const kw = @import("../keywords.zig");
const sp = @import("../statement_parsers.zig");
const data_parsers = @import("data.zig");
const type_parsers = @import("type.zig");

const Parser = sp.Parser;
const Parent = sp.Parent;
const Holder = sp.Holder;
const Error = errors.Error;
const repr = pyfmt.repr;

pub fn parseModule(p: *Parser) Error!void {
    _ = try p.ts.consume(kw.MODULE);
    p.module.name = try p.parseIdentifierArgument(kw.MODULE);
    _ = try p.ts.consumeType(.lbrace);
    while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
        try p.dispatchSubstatement(.module, .module, "module body");
    }
    _ = try p.ts.consumeType(.rbrace);
}

pub fn parseSubmodule(p: *Parser) Error!void {
    _ = try p.ts.consume(kw.SUBMODULE);
    p.module.name = try p.parseIdentifierArgument(kw.SUBMODULE);
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
    p.module.belongs_to_module = try p.parseIdentifierArgument(kw.BELONGS_TO);
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
    const name = try p.parseIdentifierArgument(kw.IMPORT);
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
    const name = try p.parseIdentifierArgument(kw.INCLUDE);
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
    const date = try p.parseStringArgument();
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
    p.module.organization = try p.parseStringArgument();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseContact(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.CONTACT);
    p.module.contact = try p.parseStringArgument();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRevision(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.REVISION);
    const date = try p.parseStringArgument();
    var body: Holder = .{};
    try p.parseOptionalBlock(.{ .holder = &body }, .revision, "revision");
    try p.module.revisions.append(p.arena, .{ .date = date, .description = body.description, .reference = body.reference });
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseFeature(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.FEATURE);
    const name = try p.parseIdentifierArgument(kw.FEATURE);
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
    const name = try p.parseIdentifierArgument(kw.IDENTITY);
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
    const name = try p.parseIdentifierArgument(kw.EXTENSION);
    const ext = try p.newStatement(name, .{ .extension = .{ .module_name = p.module.name } });
    try p.parseOptionalBlock(.{ .stmt = ext }, .extension, try p.label("extension '{s}'", .{name}));
    _ = p.ts.consumeIfType(.semicolon);
    try p.module.extensions.put(p.arena, name, ext);
    try p.addToParentOrModule(parent, ext);
}

pub fn parseExtensionArgument(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.ARGUMENT);
    const arg = try p.parseIdentifierArgument(kw.ARGUMENT);
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
    const path = try p.parseStringArgument();
    const dev = try p.newStatement("deviation", .{ .deviation = .{ .target_path = path } });
    try parseAbsoluteSchemaPath(p, path, &dev.data.deviation.target_path_segments);
    try p.parseOptionalBlock(.{ .stmt = dev }, .deviation, "deviation");
    if (dev.data.deviation.not_supported and dev.data.deviation.deviates.items.len > 0) {
        return p.ts.fail("deviation {f}: 'deviate not-supported' cannot be combined with other deviate statements (RFC 7950 \u{a7}7.20.3.2)", .{repr(path)});
    }
    try p.addToParentOrModule(parent, dev);
    _ = p.ts.consumeIfType(.semicolon);
}

/// `deviate not-supported` marks the deviation; `add`, `replace` and `delete` record the
/// properties they name (RFC 7950 7.20.3.2), applied after augments.
pub fn parseDeviate(p: *Parser, parent: Parent) Error!void {
    const dev = switch (parent) {
        .stmt => |s| switch (s.data) {
            .deviation => |*d| d,
            else => return p.ts.fail("internal: deviate outside deviation", .{}),
        },
        else => return p.ts.fail("internal: deviate outside deviation", .{}),
    };
    _ = try p.ts.consume(kw.DEVIATE);
    const kind = try p.parseStringArgument();
    if (std.mem.eql(u8, kind, kw.NOT_SUPPORTED)) {
        dev.not_supported = true;
        if (p.ts.consumeIfType(.lbrace)) _ = try p.ts.consumeType(.rbrace);
        _ = p.ts.consumeIfType(.semicolon);
        return;
    }
    const DeviateSpec = struct { name: []const u8, kind: ast.DeviateKind, allowed: []const []const u8 };
    const specs = [_]DeviateSpec{
        .{ .name = kw.ADD, .kind = .add, .allowed = &kw.DEVIATE_ADD_SUBSTATEMENTS },
        .{ .name = kw.REPLACE, .kind = .replace, .allowed = &kw.DEVIATE_REPLACE_SUBSTATEMENTS },
        .{ .name = kw.DELETE, .kind = .delete, .allowed = &kw.DEVIATE_DELETE_SUBSTATEMENTS },
    };
    const spec = for (specs) |sp_| {
        if (std.mem.eql(u8, kind, sp_.name)) break sp_;
    } else return p.ts.fail("Unknown deviate argument {f}", .{repr(kind)});
    const deviate = try p.new(ast.Deviate, .{ .kind = spec.kind });
    if (p.ts.consumeIfType(.lbrace)) {
        while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
            const keyword = p.ts.peek() orelse "";
            const allowed = for (spec.allowed) |a| {
                if (std.mem.eql(u8, a, keyword)) break true;
            } else false;
            if (!allowed) return p.ts.fail("{f} is not allowed in 'deviate {s}' (RFC 7950 \u{a7}7.20.3.2)", .{ repr(keyword), kind });
            try parseDeviateProperty(p, deviate, kind, keyword);
        }
        _ = try p.ts.consumeType(.rbrace);
    }
    _ = p.ts.consumeIfType(.semicolon);
    try dev.deviates.append(p.arena, deviate);
}

fn parseDeviateProperty(p: *Parser, deviate: *ast.Deviate, kind: []const u8, keyword: []const u8) Error!void {
    const eql = std.mem.eql;
    if (eql(u8, keyword, kw.MUST) or eql(u8, keyword, kw.TYPE)) {
        const scratch = try p.newStatement("", .{ .leaf = .{} });
        if (eql(u8, keyword, kw.MUST)) {
            try data_parsers.parseMust(p, .{ .stmt = scratch });
            try deviate.must_statements.appendSlice(p.arena, scratch.must_statements.items);
            return;
        }
        if (deviate.type != null) return p.ts.fail("duplicate 'type' in 'deviate {s}'", .{kind});
        try type_parsers.parseType(p, .{ .stmt = scratch });
        deviate.type = scratch.data.leaf.type;
        return;
    }
    if (eql(u8, keyword, kw.UNIQUE)) {
        const scratch = try p.newStatement("", .{ .list = .{} });
        try data_parsers.parseListUnique(p, .{ .stmt = scratch });
        try deviate.unique.appendSlice(p.arena, scratch.data.list.unique.items);
        return;
    }
    _ = try p.ts.consume(keyword);
    const duplicate = (eql(u8, keyword, kw.CONFIG) and deviate.config != null) or
        (eql(u8, keyword, kw.MANDATORY) and deviate.mandatory != null) or
        (eql(u8, keyword, kw.MIN_ELEMENTS) and deviate.min_elements != null) or
        (eql(u8, keyword, kw.MAX_ELEMENTS) and deviate.max_elements_set) or
        (eql(u8, keyword, kw.UNITS) and deviate.units != null);
    if (duplicate) return p.ts.fail("duplicate {f} in 'deviate {s}'", .{ repr(keyword), kind });
    if (eql(u8, keyword, kw.CONFIG)) {
        deviate.config = try p.parseBooleanArgument("config");
    } else if (eql(u8, keyword, kw.MANDATORY)) {
        deviate.mandatory = try p.parseBooleanArgument("mandatory");
    } else if (eql(u8, keyword, kw.MIN_ELEMENTS)) {
        deviate.min_elements = (try p.parseIntegerOrUnbounded("min-elements")) orelse
            return p.ts.fail("min-elements cannot be 'unbounded'", .{});
    } else if (eql(u8, keyword, kw.MAX_ELEMENTS)) {
        deviate.max_elements = try p.parseIntegerOrUnbounded("max-elements");
        deviate.max_elements_set = true;
    } else if (eql(u8, keyword, kw.UNITS)) {
        deviate.units = try p.parseStringArgument();
    } else if (eql(u8, keyword, kw.DEFAULT)) {
        try deviate.defaults.append(p.arena, try p.parseDefaultValueTokens());
    }
    _ = p.ts.consumeIfType(.semicolon);
}
