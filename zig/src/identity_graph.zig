//! Identity derivation across modules (RFC 7950 7.18), including `import` prefixes
//! (mirrors `src/xyang/identity_graph.py`). Identityref validation and `derived-from()`
//! use it from the validation and XPath phases.

const std = @import("std");
const ast = @import("ast.zig");
const Module = @import("module.zig").Module;

const IdentifierRef = ast.IdentifierRef;

/// An identity: the module that defines it and its local name.
pub const Pair = struct {
    module: *Module,
    name: []const u8,

    fn eql(a: Pair, b: Pair) bool {
        return a.module == b.module and std.mem.eql(u8, a.name, b.name);
    }
};

/// `parse_identifier_ref_atom`: `prefix:name`, or `name` when there is no inner colon.
pub fn parseIdentifierRefAtom(atom: []const u8) IdentifierRef {
    const idx = std.mem.indexOfScalar(u8, atom, ':') orelse return .{ .name = atom };
    if (idx == 0 or idx >= atom.len - 1) return .{ .name = atom };
    return .{ .prefix = atom[0..idx], .name = atom[idx + 1 ..] };
}

/// `resolve_identity_base_ref`: a `base` (possibly prefixed) in `from` scope.
pub fn resolveBaseRef(from: *Module, ref: IdentifierRef) ?Pair {
    if (ref.prefix) |pre| {
        const m = from.resolvePrefixedModule(pre) orelse return null;
        if (!m.identities.contains(ref.name)) return null;
        return .{ .module = m, .name = ref.name };
    }
    if (from.identities.contains(ref.name)) return .{ .module = from, .name = ref.name };
    return null;
}

/// `resolve_identity_qname_pair`: a schema literal `prefix:name`; unprefixed is unresolved.
pub fn resolveQNamePair(importer: *Module, qname: []const u8) ?Pair {
    const ref = parseIdentifierRefAtom(qname);
    if (ref.prefix == null) return null;
    return resolveBaseRef(importer, ref);
}

/// `resolve_identity_value`: an RFC 7951 identityref value (section 6.8). `modname:name`
/// uses the module *name* of this module or of a module it imports.
pub fn resolveValue(module: *Module, value: []const u8) ?Pair {
    if (value.len == 0) return null;
    var target: *Module = module;
    var name = value;
    if (std.mem.indexOfScalar(u8, value, ':')) |i| {
        const mod_name = value[0..i];
        name = value[i + 1 ..];
        if (!std.mem.eql(u8, mod_name, module.name)) {
            target = for (module.import_prefixes.values()) |m| {
                if (std.mem.eql(u8, m.name, mod_name)) break m;
            } else return null;
        }
    }
    if (!target.identities.contains(name)) return null;
    return .{ .module = target, .name = name };
}

/// `identity_ancestor_closure`: the identity and everything reachable over `base` edges.
pub fn ancestorClosure(a: std.mem.Allocator, start: Pair) error{OutOfMemory}![]const Pair {
    var out: std.ArrayList(Pair) = .empty;
    var stack: std.ArrayList(Pair) = .empty;
    try stack.append(a, start);
    while (stack.pop()) |pair| {
        if (contains(out.items, pair)) continue;
        try out.append(a, pair);
        const stmt = pair.module.identities.get(pair.name) orelse continue;
        for (stmt.data.identity.bases.items) |b| {
            if (resolveBaseRef(pair.module, b)) |nxt| try stack.append(a, nxt);
        }
    }
    return out.items;
}

/// `descendant_closure`: identities of `module` that derive from `base_local` over
/// same-module unprefixed `base` edges (used by the native JSON form).
pub fn descendantClosure(a: std.mem.Allocator, module: *const Module, base_local: []const u8) error{OutOfMemory}!std.StringArrayHashMapUnmanaged(void) {
    var children: std.StringArrayHashMapUnmanaged(std.ArrayList([]const u8)) = .empty;
    for (module.identities.keys(), module.identities.values()) |name, stmt| {
        for (stmt.data.identity.bases.items) |b| {
            if (b.prefix) |p| if (p.len > 0) continue;
            const gop = try children.getOrPut(a, b.name);
            if (!gop.found_existing) gop.value_ptr.* = .empty;
            try gop.value_ptr.append(a, name);
        }
    }
    var out: std.StringArrayHashMapUnmanaged(void) = .empty;
    try out.put(a, base_local, {});
    var stack: std.ArrayList([]const u8) = .empty;
    try stack.append(a, base_local);
    while (stack.pop()) |cur| {
        const kids = children.get(cur) orelse continue;
        for (kids.items) |ch| {
            if (out.contains(ch)) continue;
            try out.put(a, ch, {});
            try stack.append(a, ch);
        }
    }
    return out;
}

fn contains(pairs: []const Pair, p: Pair) bool {
    for (pairs) |x| if (x.eql(p)) return true;
    return false;
}

/// `is_derived_from_strict_qnames`: `derived-from(value, target)`.
pub fn isDerivedFromStrict(a: std.mem.Allocator, importer: *Module, value: []const u8, target: []const u8) error{OutOfMemory}!bool {
    const pv = resolveValue(importer, value) orelse return false;
    const pt = resolveQNamePair(importer, target) orelse return false;
    return contains(try ancestorClosure(a, pv), pt) and !pt.eql(pv);
}

/// `is_derived_from_or_self_qnames`: `derived-from-or-self(value, target)`.
pub fn isDerivedFromOrSelf(a: std.mem.Allocator, importer: *Module, value: []const u8, target: []const u8) error{OutOfMemory}!bool {
    const pv = resolveValue(importer, value) orelse return false;
    const pt = resolveQNamePair(importer, target) orelse return false;
    return contains(try ancestorClosure(a, pv), pt);
}

/// `identityref_value_valid`: the value derives from (or is) every base. The bases
/// resolve in `base_scope` (the module that wrote the `type`), default `importer`.
pub fn identityrefValueValid(a: std.mem.Allocator, importer: *Module, value: []const u8, bases: []const IdentifierRef, base_scope: ?*Module) error{OutOfMemory}!bool {
    if (bases.len == 0) return false;
    const pv = resolveValue(importer, value) orelse return false;
    const closure = try ancestorClosure(a, pv);
    for (bases) |b| {
        const br = resolveBaseRef(base_scope orelse importer, b) orelse return false;
        if (!contains(closure, br)) return false;
    }
    return true;
}

test "identities derive across imports" {
    const yang_parser = @import("parser/yang_parser.zig");
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: @import("errors.zig").Diagnostic = .{};
    const base = try yang_parser.parseString(a, "module base { prefix b; identity animal; identity dog { base animal; } }", "base.yang", &diag);
    const m = try yang_parser.parseString(a, "module m { prefix m; identity puppy { base x:dog; } }", "m.yang", &diag);
    try m.import_prefixes.put(a, "x", base);
    try std.testing.expect(try isDerivedFromStrict(a, m, "m:puppy", "x:animal"));
    try std.testing.expect(try isDerivedFromStrict(a, m, "base:dog", "x:animal"));
    try std.testing.expect(!try isDerivedFromStrict(a, m, "base:animal", "x:animal"));
    try std.testing.expect(try isDerivedFromOrSelf(a, m, "base:animal", "x:animal"));
    try std.testing.expect(!try isDerivedFromOrSelf(a, m, "nope:animal", "x:animal"));
    const bases = [_]IdentifierRef{.{ .prefix = "x", .name = "animal" }};
    try std.testing.expect(try identityrefValueValid(a, m, "puppy", &bases, null));
    try std.testing.expect(!try identityrefValueValid(a, m, "base:animal", &.{.{ .prefix = "x", .name = "dog" }}, null));
}
