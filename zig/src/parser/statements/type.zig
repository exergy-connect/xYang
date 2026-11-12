//! `type` and its substatements (mirrors `statements/type.py` and `statements/bits.py`).

const std = @import("std");
const ast = @import("../../ast.zig");
const errors = @import("../../errors.zig");
const pyfmt = @import("../../pyfmt.zig");
const kw = @import("../keywords.zig");
const sp = @import("../statement_parsers.zig");
const xsd_regex = @import("../../xsd_regex.zig");

const Parser = sp.Parser;
const Parent = sp.Parent;
const Holder = sp.Holder;
const Error = errors.Error;
const repr = pyfmt.repr;

fn typeOf(p: *Parser, parent: Parent) Error!*ast.TypeStmt {
    return switch (parent) {
        .type => |t| t,
        else => p.ts.fail("internal: type substatement outside type", .{}),
    };
}

fn holderOf(p: *Parser, parent: Parent) Error!*Holder {
    return switch (parent) {
        .holder => |h| h,
        else => p.ts.fail("internal: restriction substatement outside its body", .{}),
    };
}

pub fn parseType(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.TYPE);
    var name: []const u8 = undefined;
    var prefix: ?[]const u8 = null;
    if ((try p.ts.peekType()) == .identifier) {
        const ref = try p.consumeIdentifierRef();
        name = ref.name;
        prefix = ref.prefix;
    } else {
        name = try p.ts.consumeAny();
    }
    const t = try p.new(ast.TypeStmt, .{ .name = name, .prefix = prefix, .scope = p.module });
    if (p.ts.consumeIfType(.lbrace)) {
        const ctx = try p.label("type '{s}'", .{name});
        while (p.ts.hasMore() and !p.ts.at(.rbrace)) {
            try p.dispatchSubstatement(.{ .type = t }, .type, ctx);
        }
        _ = try p.ts.consumeType(.rbrace);
    }
    if (std.mem.eql(u8, t.name, kw.ENUMERATION) and t.enums.items.len == 0) {
        return p.ts.fail("enumeration type requires at least one \"enum\" statement (RFC 7950)", .{});
    }
    if (std.mem.eql(u8, t.name, kw.BITS)) {
        if (t.bits.items.len == 0) return p.ts.fail("bits type requires at least one \"bit\" statement (RFC 7950)", .{});
        try finalizeBits(p, t);
    }
    if (std.mem.eql(u8, t.name, kw.IDENTITYREF) and t.identityref_bases.items.len == 0) {
        return p.ts.fail("identityref type requires at least one \"base\" statement (RFC 7950)", .{});
    }
    switch (parent) {
        .type => |outer| try outer.types.append(p.arena, t),
        .stmt => |s| if (s.typeSlot()) |slot| {
            if (slot.*) |existing| {
                try existing.types.append(p.arena, t);
            } else {
                slot.* = t;
            }
        },
        else => {},
    }
    _ = p.ts.consumeIfType(.semicolon);
}

/// Implicit positions in declaration order; unique names and positions (RFC 7950 9.7.4.2).
fn finalizeBits(p: *Parser, t: *ast.TypeStmt) Error!void {
    var names: std.StringHashMapUnmanaged(void) = .empty;
    var used: std.AutoHashMapUnmanaged(i64, void) = .empty;
    var max_used: ?i64 = null;
    for (t.bits.items) |*b| {
        if (names.contains(b.name)) return p.ts.fail("Duplicate bit name {f} in bits type", .{repr(b.name)});
        try names.put(p.arena, b.name, {});
        if (b.position) |pos| {
            if (pos < 0) return p.ts.fail("Invalid negative position {d} for bit {f}", .{ pos, repr(b.name) });
            if (used.contains(pos)) return p.ts.fail("Duplicate position {d} for bit {f} in bits type", .{ pos, repr(b.name) });
            try used.put(p.arena, pos, {});
            max_used = if (max_used) |m| @max(m, pos) else pos;
        } else {
            const pos: i64 = if (max_used) |m| m + 1 else 0;
            b.position = pos;
            try used.put(p.arena, pos, {});
            max_used = if (max_used) |m| @max(m, pos) else pos;
        }
    }
}

pub fn parseTypeBase(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.BASE);
    try t.identityref_bases.append(p.arena, try p.consumeIdentifierRef());
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parsePattern(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.PATTERN);
    const pattern = try p.parseStringConcatenation();
    var acc: Holder = .{};
    try p.parseOptionalBlock(.{ .holder = &acc }, .pattern, "pattern");
    _ = p.ts.consumeIfType(.semicolon);
    var compiled: ?*const xsd_regex.Regex = null;
    if (pattern.len > 0) {
        var failure: xsd_regex.Failure = .{};
        compiled = xsd_regex.translate(p.arena, pattern, &failure) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.InvalidPattern => return p.ts.failUnlocated(if (failure.unsupported) .unsupported else .semantic, "{s}", .{failure.message}),
        };
    }
    try t.patterns.append(p.arena, .{
        .pattern = pattern,
        .invert_match = acc.invert_match,
        .error_message = acc.error_message,
        .error_app_tag = acc.error_app_tag,
        .compiled = compiled,
    });
}

pub fn parsePatternModifier(p: *Parser, parent: Parent) Error!void {
    const h = try holderOf(p, parent);
    _ = try p.ts.consume(kw.MODIFIER);
    const modifier = try p.ts.consumeAny();
    h.invert_match = std.mem.eql(u8, modifier, "invert-match");
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseHolderErrorMessage(p: *Parser, parent: Parent) Error!void {
    const h = try holderOf(p, parent);
    _ = try p.ts.consume(kw.ERROR_MESSAGE);
    h.error_message = try p.parseStringConcatenation();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseHolderErrorAppTag(p: *Parser, parent: Parent) Error!void {
    const h = try holderOf(p, parent);
    _ = try p.ts.consume(kw.ERROR_APP_TAG);
    h.error_app_tag = try p.parseStringConcatenation();
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseLength(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.LENGTH);
    t.length = try p.parseStringArgument();
    var meta: Holder = .{};
    try p.parseOptionalBlock(.{ .holder = &meta }, .length, "length");
    t.length_error_message = meta.error_message;
    t.length_error_app_tag = meta.error_app_tag;
    t.length_description = meta.description;
    t.length_reference = meta.reference;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRange(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.RANGE);
    t.range = try p.parseStringArgument();
    var meta: Holder = .{};
    try p.parseOptionalBlock(.{ .holder = &meta }, .range, "range");
    t.range_error_message = meta.error_message;
    t.range_error_app_tag = meta.error_app_tag;
    t.range_description = meta.description;
    t.range_reference = meta.reference;
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseFractionDigits(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.FRACTION_DIGITS);
    t.fraction_digits = try p.parseInt(try p.ts.consumeType(.integer));
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseEnum(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.ENUM);
    // One argument: `100GE` lexes as INTEGER + IDENTIFIER (RFC 7950 9.6.4).
    const name = try p.parseStringArgument();
    try t.enums.append(p.arena, name);
    if (p.ts.consumeIfType(.lbrace)) {
        try p.parseBody(.discard, .@"enum", try p.label("enum '{s}'", .{name}));
        _ = try p.ts.consumeType(.rbrace);
    }
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseEnumValue(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.VALUE);
    const raw = try p.parseStringArgument();
    if (!sp.isSignedDecimal(raw)) return p.ts.fail("value argument must be an integer, got {f}", .{repr(raw)});
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseEnumStatus(p: *Parser, _: Parent) Error!void {
    _ = try p.ts.consume(kw.STATUS);
    _ = try p.ts.consumeType(.identifier);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseBit(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.BIT);
    var bit: ast.BitStmt = .{ .name = try p.ts.consumeAny() };
    try p.parseOptionalBlock(.{ .bit = &bit }, .bit, "bit");
    try t.bits.append(p.arena, bit);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseBitPosition(p: *Parser, parent: Parent) Error!void {
    _ = try p.ts.consume(kw.POSITION);
    const bit: ?*ast.BitStmt = switch (parent) {
        .bit => |b| b,
        else => null,
    };
    if (bit) |b| {
        if (b.position != null) return p.ts.fail("Duplicate position in bit statement", .{});
    }
    const pos = try p.parseInt(try p.ts.consumeType(.integer));
    if (bit) |b| b.position = pos;
    _ = p.ts.consumeIfType(.semicolon);
}

/// leafref `path`, parsed as a schema path and bound to this module's prefixes.
pub fn parsePath(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.PATH);
    const path = try p.parseStringArgument();
    t.path = path;
    t.path_ast = try p.compileXPathPath(path);
    _ = p.ts.consumeIfType(.semicolon);
}

pub fn parseRequireInstance(p: *Parser, parent: Parent) Error!void {
    const t = try typeOf(p, parent);
    _ = try p.ts.consume(kw.REQUIRE_INSTANCE);
    t.require_instance = try p.parseBooleanArgument(kw.REQUIRE_INSTANCE);
    _ = p.ts.consumeIfType(.semicolon);
}
