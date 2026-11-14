//! Statement parsers and the keyword -> handler tables (mirrors
//! `src/xyang/parser/statement_parsers.py`).
//!
//! `dispatch_registry.PARENTS` says which keywords each parent accepts. `DEFAULT_HANDLERS`
//! maps a keyword to its usual handler and `OVERRIDES` replaces it under specific parents.
//! `TABLES` merges the three at comptime; a keyword without a handler, or an override for a
//! keyword the registry does not allow, is a compile error.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const pyfmt = @import("../pyfmt.zig");
const Module = @import("../module.zig").Module;
const kw = @import("keywords.zig");
const registry = @import("dispatch_registry.zig");
const ts_mod = @import("token_stream.zig");
const type_parsers = @import("statements/type.zig");
const module_parsers = @import("statements/module.zig");
const data_parsers = @import("statements/data.zig");
const Loader = @import("yang_parser.zig").Loader;
const xpath = @import("../xpath/xpath.zig");

pub const TokenStream = ts_mod.TokenStream;
pub const ParentId = registry.ParentId;
const Error = errors.Error;
const repr = pyfmt.repr;

/// Python's `SimpleNamespace` holders (revision, feature, restriction and pattern bodies).
pub const Holder = struct {
    description: []const u8 = "",
    reference: []const u8 = "",
    if_features: ast.StringList = .empty,
    error_message: ?[]const u8 = null,
    error_app_tag: ?[]const u8 = null,
    invert_match: bool = false,
    /// `prefix` bound inside an `import` body.
    prefix: ?[]const u8 = null,
    /// `revision-date` inside an `import` or `include` body.
    revision_date: ?[]const u8 = null,
};

/// `ParserContext.current_parent`.
pub const Parent = union(enum) {
    module,
    stmt: *ast.Statement,
    type: *ast.TypeStmt,
    must: *ast.MustStmt,
    when: *ast.WhenStmt,
    holder: *Holder,
    bit: *ast.BitStmt,
    /// A throwaway parent: substatements are syntax-checked and dropped.
    discard,
};

pub const Handler = *const fn (p: *Parser, parent: Parent) Error!void;

pub const Parser = struct {
    ts: TokenStream,
    arena: std.mem.Allocator,
    module: *Module,
    /// Loads `import`ed modules and `include`d submodules (`YangParser`).
    loader: *Loader,
    /// Directory of the file being parsed; `import` and `include` search it first.
    source_dir: ?[]const u8 = null,
    context: []const u8 = "",

    pub fn new(p: *Parser, comptime T: type, value: T) Error!*T {
        const ptr = try p.arena.create(T);
        ptr.* = value;
        return ptr;
    }

    pub fn newStatement(p: *Parser, name: []const u8, data: ast.Data) Error!*ast.Statement {
        return p.new(ast.Statement, .{ .name = name, .data = data });
    }

    pub fn label(p: *Parser, comptime fmt: []const u8, args: anytype) Error![]const u8 {
        return std.fmt.allocPrint(p.arena, fmt, args);
    }

    /// A `must` / `when` expression parsed and bound to this module's prefixes. Python
    /// raises the XPath error unwrapped, so the message has no file or line.
    pub fn compileXPath(p: *Parser, expression: []const u8) Error!?*xpath.Expr {
        var failure: xpath.Failure = .{};
        return xpath.compile(p.arena, expression, p.module, &failure) catch |err| switch (err) {
            error.OutOfMemory => error.OutOfMemory,
            error.Invalid => p.ts.failUnlocated(if (failure.unsupported) .unsupported else .syntax, "{s}", .{failure.message}),
        };
    }

    /// A leafref `path` parsed as a schema path and bound to this module's prefixes.
    pub fn compileXPathPath(p: *Parser, path: []const u8) Error!*xpath.Expr {
        var failure: xpath.Failure = .{};
        return xpath.compilePath(p.arena, path, p.module, &failure) catch |err| switch (err) {
            error.OutOfMemory => error.OutOfMemory,
            error.Invalid => p.ts.failUnlocated(if (failure.unsupported) .unsupported else .syntax, "{s}", .{failure.message}),
        };
    }

    // ------------------------------------------------------------------
    // Dispatch
    // ------------------------------------------------------------------

    pub fn handlerFor(id: ParentId, keyword: []const u8) ?Handler {
        return TABLES[@backingInt(id)].get(keyword);
    }

    /// One substatement of `id`: its handler, else a `prefix:name` extension invocation,
    /// else `Invalid or unknown statement in {label}: ...`.
    pub fn dispatchSubstatement(p: *Parser, parent: Parent, id: ParentId, error_context: []const u8) Error!void {
        const tok = p.ts.peekToken() orelse return p.ts.fail("Unexpected end of input", .{});
        if (tok.type == .identifier) {
            if (handlerFor(id, tok.value)) |h| return h(p, parent);
        }
        if (p.isPrefixedExtensionStart()) return p.parsePrefixedExtension(parent);
        if (std.mem.eql(u8, tok.value, kw.INPUT) or std.mem.eql(u8, tok.value, kw.OUTPUT)) {
            return p.ts.fail("{f} is only valid as a substatement of 'rpc' or 'action' (RFC 7950)", .{repr(tok.value)});
        }
        return p.ts.fail("Invalid or unknown statement in {s}: {f}", .{ error_context, repr(tok.value) });
    }

    /// Every substatement until the closing `}` (not consumed).
    pub fn parseBody(p: *Parser, parent: Parent, id: ParentId, error_context: []const u8) Error!void {
        const saved = p.context;
        defer p.context = saved;
        if (parent == .stmt) p.context = try @import("../typedef_scope.zig").path(p.arena, saved, parent.stmt);
        while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
            try p.dispatchSubstatement(parent, id, error_context);
        }
    }

    /// `{ body }` when the next token is `{`; then an optional `;`.
    pub fn parseOptionalBlock(p: *Parser, parent: Parent, id: ParentId, error_context: []const u8) Error!void {
        if (p.ts.consumeIfType(.lbrace)) {
            try p.parseBody(parent, id, error_context);
            _ = try p.ts.consumeType(.rbrace);
        }
    }

    pub fn isPrefixedExtensionStart(p: *const Parser) bool {
        return p.ts.peekTypeAt(0) == .identifier and p.ts.peekTypeAt(1) == .colon and p.ts.peekTypeAt(2) == .identifier;
    }

    fn parsePrefixedExtension(p: *Parser, parent: Parent) Error!void {
        const prefix = try p.ts.consumeType(.identifier);
        _ = try p.ts.consumeType(.colon);
        const ext_name = try p.ts.consumeType(.identifier);
        const resolved = p.module.resolvePrefixedModule(prefix) orelse
            return p.ts.fail("Unknown extension prefix {f} in invocation {s}:{s}", .{ repr(prefix), prefix, ext_name });
        const ext = resolved.extensions.get(ext_name) orelse
            return p.ts.fail("Unknown extension {f} in module {f} for invocation {s}:{s}", .{ repr(ext_name), repr(resolved.name), prefix, ext_name });
        var arg: ?[]const u8 = null;
        if (p.ts.hasMore() and !p.ts.at(.lbrace) and !p.ts.at(.semicolon) and !p.ts.at(.rbrace)) {
            arg = try p.parseStringArgument();
        }
        const name = try p.label("{s}:{s}", .{ prefix, ext_name });
        const inv = try p.newStatement(name, .{ .extension_invocation = .{ .prefix = prefix, .argument = arg, .resolved_module = resolved.name, .resolved_extension = ext } });
        if (p.ts.consumeIfType(.lbrace)) {
            const ctx = try p.label("extension invocation '{s}'", .{name});
            while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
                try p.dispatchSubstatement(.{ .stmt = inv }, .extension_invocation, ctx);
            }
            _ = try p.ts.consumeType(.rbrace);
        }
        _ = p.ts.consumeIfType(.semicolon);
        try p.addToParentOrModule(parent, inv);
    }

    // ------------------------------------------------------------------
    // Parent helpers (`hasattr` / `isinstance` checks in Python)
    // ------------------------------------------------------------------

    pub fn addToParentOrModule(p: *Parser, parent: Parent, stmt: *ast.Statement) Error!void {
        switch (parent) {
            .stmt => |s| try s.statements.append(p.arena, stmt),
            else => try p.module.statements.append(p.arena, stmt),
        }
    }

    pub fn setDescription(p: *Parser, parent: Parent, value: []const u8) void {
        switch (parent) {
            .module => p.module.description = value,
            .stmt => |s| s.description = value,
            .must => |m| m.description = value,
            .when => |w| w.description = value,
            .holder => |h| h.description = value,
            .bit => |b| b.description = value,
            .type, .discard => {},
        }
    }

    fn setReference(p: *Parser, parent: Parent, value: []const u8) void {
        switch (parent) {
            .module => p.module.reference = value,
            .stmt => |s| s.reference = value,
            .must => |m| m.reference = value,
            .when => |w| w.reference = value,
            .holder => |h| h.reference = value,
            .bit => |b| b.reference = value,
            .type, .discard => {},
        }
    }

    // ------------------------------------------------------------------
    // Arguments
    // ------------------------------------------------------------------

    /// `consume_identifier_ref`: `name` or `prefix:name`.
    pub fn consumeIdentifierRef(p: *Parser) Error!ast.IdentifierRef {
        const first = std.mem.trim(u8, try p.ts.consumeType(.identifier), " \t\r\n");
        if (!p.ts.consumeIfType(.colon)) return .{ .name = first };
        const second = std.mem.trim(u8, try p.ts.consumeType(.identifier), " \t\r\n");
        return .{ .prefix = first, .name = second };
    }

    pub fn consumeQName(p: *Parser) Error![]const u8 {
        const ref = try p.consumeIdentifierRef();
        if (ref.prefix) |pre| return p.label("{s}:{s}", .{ pre, ref.name });
        return ref.name;
    }

    /// Quoted string with `+` concatenation, or one unquoted argument.
    pub fn parseStringConcatenation(p: *Parser) Error![]const u8 {
        if (!p.ts.at(.string)) return p.parseStringArgument();
        var out = try p.ts.consumeType(.string);
        while (p.ts.at(.plus)) {
            _ = try p.ts.consumeType(.plus);
            if (!p.ts.at(.string)) return p.ts.fail("Expected quoted string after '+'", .{});
            out = try std.mem.concat(p.arena, u8, &.{ out, try p.ts.consumeType(.string) });
        }
        return out;
    }

    /// One statement argument: a quoted string (with `+`) or an unquoted run of
    /// source-adjacent lexemes up to whitespace, `;`, `{` or `}` (RFC 7950 6.1.3).
    pub fn parseStringArgument(p: *Parser) Error![]const u8 {
        if (!p.ts.hasMore()) return p.ts.fail("Expected statement argument, got 'end'", .{});
        if (p.ts.at(.string)) return p.parseStringConcatenation();
        return p.readUnquotedArgument();
    }

    fn readUnquotedArgument(p: *Parser) Error![]const u8 {
        const start = p.ts.index;
        var prev_line: usize = 0;
        var prev_end: ?usize = null;
        var out: std.ArrayList(u8) = .empty;
        while (p.ts.peekToken()) |tok| {
            switch (tok.type) {
                .semicolon, .lbrace, .rbrace, .string => break,
                else => {},
            }
            if (prev_end) |e| {
                if (tok.line != prev_line or tok.col != e) break;
            }
            try out.appendSlice(p.arena, tok.value);
            prev_line = tok.line;
            prev_end = tok.col + tok.value.len;
            p.ts.index += 1;
        }
        if (p.ts.index == start) {
            const got = p.ts.peek() orelse "end";
            return p.ts.fail("Expected statement argument, got {f}", .{repr(got)});
        }
        return out.items;
    }

    /// Exactly `true` or `false`, quoted or unquoted.
    pub fn parseBooleanArgument(p: *Parser, statement: []const u8) Error!bool {
        if (!p.ts.hasMore() or p.ts.at(.semicolon) or p.ts.at(.lbrace) or p.ts.at(.rbrace)) {
            return p.ts.fail("{s} argument must be 'true' or 'false', got ''", .{statement});
        }
        const raw = try p.parseStringArgument();
        if (std.mem.eql(u8, raw, kw.TRUE)) return true;
        if (std.mem.eql(u8, raw, kw.FALSE)) return false;
        return p.ts.fail("{s} argument must be 'true' or 'false', got {f}", .{ statement, repr(raw) });
    }

    /// `min-elements` / `max-elements`: an integer or `unbounded` (stored as null).
    pub fn parseIntegerOrUnbounded(p: *Parser, statement: []const u8) Error!ast.Bound {
        const raw = try p.parseStringArgument();
        if (std.mem.eql(u8, raw, "unbounded")) return null;
        if (!isSignedDecimal(raw)) {
            return p.ts.fail("{s} argument must be an integer or 'unbounded', got {f}", .{ statement, repr(raw) });
        }
        return try p.parseInt(raw);
    }

    /// Python `int(text)` for text already known to be `[+-]?\d+`. Python integers are
    /// unbounded; a value outside i64 is refused instead of wrapped.
    pub fn parseInt(p: *Parser, text: []const u8) Error!i64 {
        return std.fmt.parseInt(i64, text, 10) catch
            p.ts.failKind(.unsupported, "xyang-zig does not support integer {f} outside the 64-bit range yet", .{repr(text)});
    }

    /// `default` value: one STRING, INTEGER or IDENTIFIER token.
    pub fn parseDefaultValueTokens(p: *Parser) Error![]const u8 {
        const tt = try p.ts.peekType();
        switch (tt) {
            .string, .integer, .identifier => return p.ts.consumeAny(),
            else => return p.ts.fail("Expected default value (string, integer, identifier, or true/false), got {s}", .{tt.pyName()}),
        }
    }

    /// `prefix` argument as a string or a bare identifier.
    pub fn consumePrefixArgument(p: *Parser) Error![]const u8 {
        const tt = if (p.ts.hasMore()) p.ts.tokens[p.ts.index].type else return p.ts.fail("Unexpected end of input", .{});
        return switch (tt) {
            .string, .identifier => p.ts.consumeAny(),
            else => p.ts.fail("Expected prefix string or identifier, got {s}", .{tt.pyName()}),
        };
    }
};

pub fn isSignedDecimal(raw: []const u8) bool {
    var s = raw;
    if (s.len > 0 and (s[0] == '+' or s[0] == '-')) s = s[1..];
    if (s.len == 0) return false;
    for (s) |c| if (c < '0' or c > '9') return false;
    return true;
}

// ----------------------------------------------------------------------
// Metadata handlers shared by many parents
// ----------------------------------------------------------------------

/// `description` (a braced extension body after it is skipped, like Python).
pub fn parseDescription(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DESCRIPTION);
    const desc = try p.ts.consumeType(.string);
    if (p.ts.at(.lbrace)) try consumeBalancedBraces(p);
    _ = p.ts.consumeIfType(.semicolon);
    p.setDescription(parent, desc);
}

fn parseDiscardedDescription(p: *Parser, _: Parent) Error!void {
    return parseDescription(p, .discard);
}

pub fn parseReference(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.REFERENCE);
    const ref = try p.ts.consumeType(.string);
    _ = p.ts.consumeIfType(.semicolon);
    p.setReference(parent, ref);
}

pub fn parseUnits(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.UNITS);
    const units = try p.parseStringArgument();
    _ = p.ts.consumeIfType(.semicolon);
    switch (parent) {
        .stmt => |s| s.units = units,
        .type => |t| t.units = units,
        else => {},
    }
}

/// `status current|deprecated|obsolete;` (not stored on the AST, like Python).
pub fn parseStatusIgnored(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.STATUS);
    if ((try p.ts.peekType()) == .identifier) _ = try p.ts.consumeType(.identifier);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn consumeBalancedBraces(p: *Parser) Error!void {
    var depth: usize = 0;
    while (p.ts.hasMore()) {
        const tt = try p.ts.peekType();
        if (tt == .lbrace) {
            depth += 1;
            p.ts.index += 1;
        } else if (tt == .rbrace) {
            depth -|= 1;
            p.ts.index += 1;
            if (depth == 0) return;
        } else {
            p.ts.index += 1;
        }
    }
}

// ----------------------------------------------------------------------
// Keyword -> handler tables
// ----------------------------------------------------------------------

const KV = struct { []const u8, Handler };

const DEFAULT_HANDLERS = [_]KV{
    .{ kw.LEAF, data_parsers.parseLeaf },
    .{ kw.LIST, data_parsers.parseList },
    .{ kw.LEAF_LIST, data_parsers.parseLeafList },
    .{ kw.CONTAINER, data_parsers.parseContainer },
    .{ kw.NOTIFICATION, data_parsers.parseNotification },
    .{ kw.RPC, data_parsers.parseRpc },
    .{ kw.ACTION, data_parsers.parseAction },
    .{ kw.ANYDATA, data_parsers.parseAnydata },
    .{ kw.ANYXML, data_parsers.parseAnyxml },
    .{ kw.TYPEDEF, data_parsers.parseTypedef },
    .{ kw.GROUPING, data_parsers.parseGrouping },
    .{ kw.IMPORT, module_parsers.parseImport },
    .{ kw.INCLUDE, module_parsers.parseInclude },
    .{ kw.REVISION, module_parsers.parseRevision },
    .{ kw.DESCRIPTION, parseDescription },
    .{ kw.REFERENCE, parseReference },
    .{ kw.FEATURE, module_parsers.parseFeature },
    .{ kw.IDENTITY, module_parsers.parseIdentity },
    .{ kw.EXTENSION, module_parsers.parseExtension },
    .{ kw.AUGMENT, module_parsers.parseAugment },
    .{ kw.DEVIATION, module_parsers.parseDeviation },
    .{ kw.YANG_VERSION, module_parsers.parseYangVersion },
    .{ kw.NAMESPACE, module_parsers.parseNamespace },
    .{ kw.PREFIX, module_parsers.parseModulePrefix },
    .{ kw.ORGANIZATION, module_parsers.parseOrganization },
    .{ kw.CONTACT, module_parsers.parseContact },
    .{ kw.TYPE, type_parsers.parseType },
    .{ kw.UNITS, parseUnits },
    .{ kw.DEFAULT, data_parsers.parseLeafDefault },
    .{ kw.STATUS, parseStatusIgnored },
    .{ kw.CONFIG, data_parsers.parseConfig },
    .{ kw.WHEN, data_parsers.parseWhen },
    .{ kw.MUST, data_parsers.parseMust },
    .{ kw.IF_FEATURE, module_parsers.parseIfFeature },
    .{ kw.PRESENCE, data_parsers.parsePresence },
    .{ kw.USES, data_parsers.parseUses },
    .{ kw.REFINE, data_parsers.parseRefine },
    .{ kw.CHOICE, data_parsers.parseChoice },
    .{ kw.CASE, data_parsers.parseCase },
    .{ kw.KEY, data_parsers.parseListKey },
    .{ kw.UNIQUE, data_parsers.parseListUnique },
    .{ kw.MIN_ELEMENTS, data_parsers.parseMinElements },
    .{ kw.MAX_ELEMENTS, data_parsers.parseMaxElements },
    .{ kw.ORDERED_BY, data_parsers.parseOrderedBy },
    .{ kw.MANDATORY, data_parsers.parseLeafMandatory },
    .{ kw.INPUT, data_parsers.parseInput },
    .{ kw.OUTPUT, data_parsers.parseOutput },
};

const Override = struct { ParentId, []const KV };

const OVERRIDES = [_]Override{
    .{ .import, &.{
        .{ kw.PREFIX, module_parsers.parseImportPrefix },
        .{ kw.DESCRIPTION, parseDiscardedDescription },
        .{ kw.REVISION_DATE, module_parsers.parseRevisionDate },
    } },
    .{ .include, &.{
        .{ kw.PREFIX, module_parsers.parsePrefixValue },
        .{ kw.DESCRIPTION, parseDiscardedDescription },
        .{ kw.REVISION_DATE, module_parsers.parseRevisionDate },
    } },
    .{ .belongs_to, &.{.{ kw.PREFIX, module_parsers.parsePrefixValue }} },
    .{ .typedef, &.{.{ kw.DEFAULT, data_parsers.parseTypedefDefault }} },
    .{ .choice, &.{
        .{ kw.MANDATORY, data_parsers.parseChoiceMandatory },
        .{ kw.DEFAULT, data_parsers.parseChoiceDefault },
    } },
    .{ .refine, &.{
        .{ kw.MANDATORY, data_parsers.parseRefineMandatory },
        .{ kw.DEFAULT, data_parsers.parseRefineDefault },
    } },
    .{ .identity, &.{.{ kw.BASE, module_parsers.parseIdentityBase }} },
    .{ .if_feature, &.{.{ kw.DESCRIPTION, parseDiscardedDescription }} },
    .{ .must, &.{.{ kw.ERROR_MESSAGE, data_parsers.parseMustErrorMessage }} },
    .{ .extension, &.{.{ kw.ARGUMENT, module_parsers.parseExtensionArgument }} },
    .{ .argument, &.{.{ kw.YIN_ELEMENT, module_parsers.parseYinElement }} },
    .{ .deviation, &.{.{ kw.DEVIATE, module_parsers.parseDeviate }} },
    .{ .pattern, &.{
        .{ kw.ERROR_MESSAGE, type_parsers.parseHolderErrorMessage },
        .{ kw.ERROR_APP_TAG, type_parsers.parseHolderErrorAppTag },
        .{ kw.MODIFIER, type_parsers.parsePatternModifier },
    } },
    .{ .@"enum", &.{
        .{ kw.VALUE, type_parsers.parseEnumValue },
        .{ kw.STATUS, type_parsers.parseEnumStatus },
    } },
    .{ .bit, &.{.{ kw.POSITION, type_parsers.parseBitPosition }} },
    .{ .length, &.{
        .{ kw.ERROR_MESSAGE, type_parsers.parseHolderErrorMessage },
        .{ kw.ERROR_APP_TAG, type_parsers.parseHolderErrorAppTag },
    } },
    .{ .range, &.{
        .{ kw.ERROR_MESSAGE, type_parsers.parseHolderErrorMessage },
        .{ kw.ERROR_APP_TAG, type_parsers.parseHolderErrorAppTag },
    } },
    .{ .type, &.{
        .{ kw.PATTERN, type_parsers.parsePattern },
        .{ kw.LENGTH, type_parsers.parseLength },
        .{ kw.RANGE, type_parsers.parseRange },
        .{ kw.FRACTION_DIGITS, type_parsers.parseFractionDigits },
        .{ kw.ENUM, type_parsers.parseEnum },
        .{ kw.BIT, type_parsers.parseBit },
        .{ kw.PATH, type_parsers.parsePath },
        .{ kw.REQUIRE_INSTANCE, type_parsers.parseRequireInstance },
        .{ kw.BASE, type_parsers.parseTypeBase },
    } },
};

fn lookup(comptime kvs: []const KV, comptime keyword: []const u8) ?Handler {
    for (kvs) |entry| {
        if (std.mem.eql(u8, entry[0], keyword)) return entry[1];
    }
    return null;
}

fn buildTable(comptime spec: registry.DispatchParent) std.StaticStringMap(Handler) {
    @setEvalBranchQuota(1_000_000);
    comptime {
        var over: []const KV = &.{};
        for (OVERRIDES) |o| {
            if (o[0] == spec.id) over = o[1];
        }
        for (over) |entry| {
            if (!spec.allows(entry[0])) @compileError("handler override for keyword not allowed under " ++ spec.name ++ ": " ++ entry[0]);
        }
        var kvs: [spec.keywords.len]KV = undefined;
        for (spec.keywords, 0..) |keyword, i| {
            const found: ?Handler = lookup(over, keyword) orelse lookup(&DEFAULT_HANDLERS, keyword);
            const h = found orelse @compileError("no handler for " ++ spec.name ++ ": " ++ keyword);
            kvs[i] = .{ keyword, h };
        }
        return std.StaticStringMap(Handler).initComptime(kvs);
    }
}

const TABLES = blk: {
    var tables: [registry.PARENTS.len]std.StaticStringMap(Handler) = undefined;
    for (registry.PARENTS, 0..) |spec, i| tables[i] = buildTable(spec);
    break :blk tables;
};

test "every registry keyword dispatches" {
    for (registry.PARENTS) |spec| {
        for (spec.keywords) |keyword| {
            try std.testing.expect(Parser.handlerFor(spec.id, keyword) != null);
        }
    }
    try std.testing.expect(Parser.handlerFor(.case, kw.MANDATORY) == null);
    try std.testing.expect(Parser.handlerFor(.type, kw.PATTERN).? == type_parsers.parsePattern);
    try std.testing.expect(Parser.handlerFor(.choice, kw.MANDATORY).? == data_parsers.parseChoiceMandatory);
    try std.testing.expect(Parser.handlerFor(.leaf, kw.MANDATORY).? == data_parsers.parseLeafMandatory);
}
