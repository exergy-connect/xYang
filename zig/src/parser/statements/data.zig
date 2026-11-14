//! Schema node statements and their substatements (mirrors `statements/leaf.py`,
//! `leaf_list.py`, `list.py`, `container.py`, `choice.py`, `grouping.py`, `typedef.py`,
//! `uses.py`, `refine.py`, `must.py`, `when.py`, `rpc.py`, `notification.py`,
//! `anydata.py`, `anyxml.py` and the leaf-level handlers in `statement_parsers.py`).

const std = @import("std");
const ast = @import("../../ast.zig");
const errors = @import("../../errors.zig");
const pyfmt = @import("../../pyfmt.zig");
const kw = @import("../keywords.zig");
const sp = @import("../statement_parsers.zig");
const registry = @import("../dispatch_registry.zig");
const refine_expand = @import("../../refine_expand.zig");
const xpath = @import("../../xpath/xpath.zig");

const Parser = sp.Parser;
const Parent = sp.Parent;
const Error = errors.Error;
const repr = pyfmt.repr;

/// `keyword name [{ body }] [;]` added to the parent: leaf, leaf-list, list, anydata,
/// anyxml, notification, rpc and action share this shape.
fn parseNamedNode(p: *Parser, parent: Parent, comptime keyword: []const u8, comptime id: registry.ParentId, data: ast.Data) Error!*ast.Statement {
    _ = try p.ts.consume(keyword);
    const name = try p.parseIdentifierArgument(keyword);
    const stmt = try p.newStatement(name, data);
    try p.parseOptionalBlock(.{ .stmt = stmt }, id, try p.label(keyword ++ " '{s}'", .{name}));
    try p.addToParentOrModule(parent, stmt);
    _ = p.ts.consumeIfType(.semicolon);
    return stmt;
}

pub fn parseLeaf(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.LEAF, .leaf, .{ .leaf = .{} });
}

pub fn parseLeafList(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.LEAF_LIST, .leaf_list, .{ .leaf_list = .{} });
}

pub fn parseList(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.LIST, .list, .{ .list = .{} });
}

pub fn parseAnydata(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.ANYDATA, .anydata, .{ .anydata = .{} });
}

pub fn parseAnyxml(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.ANYXML, .anyxml, .{ .anyxml = .{} });
}

pub fn parseNotification(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.NOTIFICATION, .notification, .{ .notification = .{} });
}

pub fn parseRpc(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.RPC, .rpc, .{ .rpc = {} });
}

pub fn parseAction(p: *Parser, parent: Parent) Error!void {
    _ = try parseNamedNode(p, parent, kw.ACTION, .action, .{ .action = {} });
}

fn parseIoBlock(p: *Parser, parent: Parent, comptime keyword: []const u8, comptime id: registry.ParentId, data: ast.Data) Error!void {
    _ = try p.ts.consume(keyword);
    const stmt = try p.newStatement(keyword, data);
    try p.parseOptionalBlock(.{ .stmt = stmt }, id, keyword ++ " block");
    try p.addToParentOrModule(parent, stmt);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseInput(p: *Parser, parent: Parent) Error!void {
    try parseIoBlock(p, parent, kw.INPUT, .input, .{ .input = .{} });
}

pub fn parseOutput(p: *Parser, parent: Parent) Error!void {
    try parseIoBlock(p, parent, kw.OUTPUT, .output, .{ .output = .{} });
}

pub fn parseContainer(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.CONTAINER);
    const name = try p.parseIdentifierArgument(kw.CONTAINER);
    const stmt = try p.newStatement(name, .{ .container = .{} });
    if (p.ts.consumeIfType(.lbrace)) {
        try p.parseBody(.{ .stmt = stmt }, .container, try p.label("container '{s}'", .{name}));
        // Python closes the container only when `}` is present; end of input is reported
        // by the enclosing statement.
        _ = p.ts.consumeIfType(.rbrace);
    }
    try p.addToParentOrModule(parent, stmt);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseTypedef(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.TYPEDEF);
    const name = try p.parseIdentifierArgument(kw.TYPEDEF);
    const stmt = try p.newStatement(name, .{ .typedef = .{} });
    try p.parseOptionalBlock(.{ .stmt = stmt }, .typedef, try p.label("typedef '{s}'", .{name}));
    stmt.data.typedef.scope = if (p.context.len > 0) p.context else null;
    try @import("../../typedef_scope.zig").register(&p.loader.reporter, p.module, stmt);
    switch (parent) {
        .stmt => |s| {
            try s.statements.append(p.arena, stmt);
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseGrouping(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.GROUPING);
    const name = try p.parseIdentifierArgument(kw.GROUPING);
    const stmt = try p.newStatement(name, .{ .grouping = .{} });
    try p.parseOptionalBlock(.{ .stmt = stmt }, .grouping, try p.label("grouping '{s}'", .{name}));
    const container: ?*ast.Container = switch (parent) {
        .stmt => |s| switch (s.data) {
            .container => |*c| c,
            else => null,
        },
        else => null,
    };
    if (container) |c| {
        try c.groupings.put(p.arena, name, stmt);
    } else {
        try p.module.groupings.put(p.arena, name, stmt);
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// Schema nodes directly under `choice` imply a `case` named like the node (RFC 7950 7.9.2).
const INLINE_CHOICE_SCHEMA_KEYS = [_][]const u8{ kw.LEAF, kw.LEAF_LIST, kw.CONTAINER, kw.LIST, kw.ANYDATA, kw.ANYXML, kw.CHOICE };

fn isInlineChoiceKey(p: *const Parser) bool {
    const tok = p.ts.peekToken() orelse return false;
    if (tok.type != .identifier) return false;
    for (INLINE_CHOICE_SCHEMA_KEYS) |k| if (std.mem.eql(u8, k, tok.value)) return true;
    return false;
}

pub fn parseChoice(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.CHOICE);
    const name = try p.parseIdentifierArgument(kw.CHOICE);
    const choice = try p.newStatement(name, .{ .choice = .{} });
    if (p.ts.consumeIfType(.lbrace)) {
        const ctx = try p.label("choice '{s}'", .{name});
        while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
            if (isInlineChoiceKey(p)) {
                try parseImplicitCase(p, choice);
            } else {
                try p.dispatchSubstatement(.{ .stmt = choice }, .choice, ctx);
            }
        }
        _ = try p.ts.consumeType(.rbrace);
        try validateCaseUniqueChildNames(p, choice);
    }
    try p.addToParentOrModule(parent, choice);
    _ = p.ts.consumeIfType(.semicolon);
}

fn parseImplicitCase(p: *Parser, choice: *ast.Statement) Error!void {
    const case = try p.newStatement("", .{ .case = {} });
    const keyword = p.ts.peek().?;
    const handler = Parser.handlerFor(.case, keyword) orelse
        return p.ts.fail("internal: unsupported implicit choice schema {f}", .{repr(keyword)});
    try handler(p, .{ .stmt = case });
    if (case.statements.items.len == 0) {
        return p.ts.fail("Expected a schema node in implicit choice case (RFC 7950 §7.9.2)", .{});
    }
    const first = case.statements.items[0];
    const case_name = if (first.name.len > 0) first.name else first.schemaNode() orelse "";
    if (case_name.len == 0) {
        return p.ts.fail("Implicit choice case requires a named schema node (RFC 7950 §7.9.2)", .{});
    }
    case.name = case_name;
    try choice.data.choice.cases.append(p.arena, case);
}

/// RFC 7950 7.9: the cases of a choice share one namespace.
fn validateCaseUniqueChildNames(p: *Parser, choice: *ast.Statement) Error!void {
    var seen: std.StringArrayHashMapUnmanaged([]const u8) = .empty;
    for (choice.data.choice.cases.items) |case| {
        for (case.statements.items) |sub| {
            const seg = sub.schemaNode() orelse continue;
            if (seen.get(seg)) |prev_case| {
                return p.ts.failUnlocated(
                    .semantic,
                    "Choice {f}: schema node {f} appears in case {f} and again in case {f} (RFC 7950: names of nodes in the cases of a choice must be unique).",
                    .{ repr(choice.name), repr(seg), repr(prev_case), repr(case.name) },
                );
            }
            try seen.put(p.arena, seg, case.name);
        }
    }
}

pub fn parseCase(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.CASE);
    const name = try p.parseIdentifierArgument(kw.CASE);
    const case = try p.newStatement(name, .{ .case = {} });
    try p.parseOptionalBlock(.{ .stmt = case }, .case, try p.label("case '{s}'", .{name}));
    switch (parent) {
        .stmt => |s| switch (s.data) {
            .choice => |*c| try c.cases.append(p.arena, case),
            else => try p.addToParentOrModule(parent, case),
        },
        else => try p.addToParentOrModule(parent, case),
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseChoiceMandatory(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MANDATORY);
    const value = try p.parseBooleanArgument(kw.MANDATORY);
    if (stmtData(parent, .choice)) |s| s.data.choice.mandatory = value;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseChoiceDefault(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DEFAULT);
    const name = try p.parseIdentifierArgument(kw.DEFAULT);
    if (stmtData(parent, .choice)) |s| s.data.choice.default = name;
    _ = p.ts.consumeIfType(.semicolon);
}

fn stmtData(parent: Parent, kind: ast.Kind) ?*ast.Statement {
    return switch (parent) {
        .stmt => |s| if (s.kind() == kind) s else null,
        else => null,
    };
}

pub fn parseUses(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.USES);
    const ref = try p.consumeIdentifierRef();
    const name = ref.name;
    const prefix = ref.prefix;
    const uses = try p.newStatement("uses", .{ .uses = .{ .grouping_name = name, .grouping_prefix = prefix } });
    const qname = if (prefix) |pre| try p.label("{s}:{s}", .{ pre, name }) else name;
    try p.parseOptionalBlock(.{ .stmt = uses }, .uses, try p.label("uses '{s}'", .{qname}));
    try p.addToParentOrModule(parent, uses);
    _ = p.ts.consumeIfType(.semicolon);
}

/// `refine` with a descendant path (`a/b`, `p:a/p:b`), parsed as an XPath schema path and
/// applied when `uses` is expanded.
pub fn parseRefine(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.REFINE);
    const path_arg = try p.parseStringArgument();
    // Python keeps the parsed path; matching and messages use its `to_string()`.
    var xp = try xpath.Parser.init(p.arena, path_arg);
    const parsed = xp.parsePath(true) catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        error.XPathSyntax => return p.ts.fail("{s}", .{xp.message}),
        error.UnknownFunction => return p.ts.failUnlocated(.syntax, "{s}", .{xp.message}),
        error.UnsupportedNumber => return p.ts.failUnlocated(.unsupported, "{s}", .{xp.message}),
    };
    const path = try parsed.path.toString(p.arena);
    const refine = try p.newStatement("refine", .{ .refine = .{ .target_path = path } });
    try p.parseOptionalBlock(.{ .stmt = refine }, .refine, try p.label("refine '{s}'", .{path}));
    if (stmtData(parent, .uses)) |s| try s.data.uses.refines.append(p.arena, refine);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRefineMandatory(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MANDATORY);
    const value = try p.parseBooleanArgument(kw.MANDATORY);
    if (stmtData(parent, .refine)) |s| s.data.refine.refined_mandatory = value;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRefineDefault(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DEFAULT);
    if (stmtData(parent, .refine)) |s| try s.data.refine.refined_defaults.append(p.arena, try p.parseDefaultValueTokens());
    _ = p.ts.consumeIfType(.semicolon);
}

/// `must`: the XPath is parsed and bound to this module's prefixes before the body.
pub fn parseMust(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MUST);
    const expression = try p.parseStringConcatenation();
    const must = try p.new(ast.MustStmt, .{ .expression = expression, .ast = try p.compileXPath(expression) });
    try p.parseOptionalBlock(.{ .must = must }, .must, "must");
    switch (parent) {
        .stmt => |s| if (s.hasMust()) try s.must_statements.append(p.arena, must),
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseMustErrorMessage(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.ERROR_MESSAGE);
    const value = try p.parseStringArgument();
    switch (parent) {
        .must => |m| m.error_message = value,
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseMustErrorAppTag(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.ERROR_APP_TAG);
    const value = try p.parseStringArgument();
    switch (parent) {
        .must => |m| m.error_app_tag = value,
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// `when`: the XPath is parsed and bound to this module's prefixes before the body.
pub fn parseWhen(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.WHEN);
    const expression = try p.parseStringConcatenation();
    const when = try p.new(ast.WhenStmt, .{ .expression = expression, .ast = try p.compileXPath(expression) });
    try p.parseOptionalBlock(.{ .when = when }, .when, "when");
    switch (parent) {
        .stmt => |s| if (s.hasWhen()) {
            s.when = when;
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parsePresence(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.PRESENCE);
    const value = try p.parseStringArgument();
    if (stmtData(parent, .container)) |s| s.data.container.presence = value;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseListKey(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.KEY);
    const key = try p.parseStringArgument();
    if (stmtData(parent, .list)) |s| s.data.list.key = key;
    _ = p.ts.consumeIfType(.semicolon);
}

/// `unique "<descendant-path> ..."` with prefixes stripped (RFC 7950 7.8.3).
pub fn parseListUnique(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.UNIQUE);
    const arg = try p.parseStringArgument();
    var paths: std.ArrayList([]const u8) = .empty;
    var it = std.mem.tokenizeAny(u8, arg, &std.ascii.whitespace);
    while (it.next()) |path| {
        var segs: std.ArrayList([]const u8) = .empty;
        var seg_it = std.mem.tokenizeScalar(u8, path, '/');
        while (seg_it.next()) |seg| {
            const local = if (std.mem.indexOfScalar(u8, seg, ':')) |i| seg[i + 1 ..] else seg;
            try segs.append(p.arena, local);
        }
        try paths.append(p.arena, try std.mem.join(p.arena, "/", segs.items));
    }
    if (paths.items.len == 0) return p.ts.fail("unique requires at least one descendant path", .{});
    if (stmtData(parent, .list)) |s| try s.data.list.unique.append(p.arena, paths.items);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseMinElements(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MIN_ELEMENTS);
    const value = try p.parseIntegerOrUnbounded(kw.MIN_ELEMENTS);
    switch (parent) {
        .stmt => |s| if (s.minElementsSlot()) |slot| {
            slot.* = value;
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseMaxElements(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MAX_ELEMENTS);
    const value = try p.parseIntegerOrUnbounded(kw.MAX_ELEMENTS);
    switch (parent) {
        .stmt => |s| if (s.maxElementsSlot()) |slot| {
            slot.* = value;
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// `ordered-by user|system` is checked and not stored, like Python.
pub fn parseOrderedBy(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.ORDERED_BY);
    _ = try p.parseKeywordArgument(kw.ORDERED_BY, &.{ "user", "system" });
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseLeafMandatory(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.MANDATORY);
    const value = try p.parseBooleanArgument(kw.MANDATORY);
    switch (parent) {
        .stmt => |s| switch (s.data) {
            .leaf => |*d| d.mandatory = value,
            .anydata => |*d| d.mandatory = value,
            .anyxml => |*d| d.mandatory = value,
            else => {},
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseLeafDefault(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DEFAULT);
    if (stmtData(parent, .leaf)) |s| s.data.leaf.default = try p.parseDefaultValueTokens();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseTypedefDefault(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.DEFAULT);
    if (stmtData(parent, .typedef)) |s| s.data.typedef.default = try p.parseDefaultValueTokens();
    _ = p.ts.consumeIfType(.semicolon);
}

/// `config true|false` (RFC 7950 7.21.1).
pub fn parseConfig(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.CONFIG);
    const value = try p.parseBooleanArgument(kw.CONFIG);
    switch (parent) {
        .stmt => |s| switch (s.data) {
            .refine => |*r| r.refined_config = value,
            else => if (s.hasWhen()) {
                s.config = value;
            },
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}
