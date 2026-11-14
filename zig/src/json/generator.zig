//! Generate the native JSON form (JSON Schema 2020-12 with `x-yang`) from a module
//! (mirrors `src/xyang/json/generator.py`).
//!
//! The output is a `json_value.Val` tree whose objects keep Python's dict insertion order;
//! `json_value.dumpIndented` writes it as `json.dumps(indent=2, ensure_ascii=False)`.
//! Built-in types are encoded by the `to_schema` column of `types/registry.zig`. A
//! construct the form cannot carry fails the export (`error.Export`, Python's
//! `YangExportError`) instead of being dropped.

const std = @import("std");
const ast = @import("../ast.zig");
const errors = @import("../errors.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const K = @import("schema_keys.zig");
const registry = @import("../types/registry.zig");
const identity_graph = @import("../identity_graph.zig");
const refine_expand = @import("../refine_expand.zig");
const uses_expand = @import("../uses_expand.zig");
const augment_expand = @import("../augment_expand.zig");
const capabilities = @import("../ext/capabilities.zig");
const xast = @import("../xpath/ast.zig");
const schema_nav = @import("../xpath/schema_nav.zig");
const xutils = @import("../xpath/utils.zig");
const pyfmt = @import("../pyfmt.zig");

const Allocator = std.mem.Allocator;
const Module = module_mod.Module;
const Statement = ast.Statement;
const Val = jv.Val;
const Object = jv.Object;
pub const Schema = @import("../xpath/node.zig").Schema;
const repr = pyfmt.repr;

/// `Export`: `YangExportError` (the CLI exits 2). `YangLoad`: an error Python raises from
/// `uses` expansion, `augment` merging or `copy_yang_statement` (the CLI exits 1).
pub const Error = error{ OutOfMemory, Export, YangLoad };

/// `typedef_names`: the typedef names a `type` may reference as `$ref`.
pub const Names = std.StringHashMapUnmanaged(void);

const ScopedTypedef = struct { typedef: *Statement, module: *Module };
const ExtUse = struct { owner: *Module, name: []const u8 };

/// One export: the module, the identities and extensions it resolved outside itself
/// (`_IdentityExport` and `_ExtensionUse`), and where a failure is reported.
pub const Gen = struct {
    a: Allocator,
    root: *Module,
    reporter: errors.Reporter,
    identities_used: std.ArrayList(identity_graph.Pair) = .empty,
    extensions_used: std.ArrayList(ExtUse) = .empty,
    scoped_typedefs: std.StringArrayHashMapUnmanaged(ScopedTypedef) = .empty,

    pub fn fail(g: *Gen, comptime fmt: []const u8, args: anytype) Error {
        g.reporter.diag.* = .{ .kind = .semantic, .message = try std.fmt.allocPrint(g.a, fmt, args) };
        return error.Export;
    }
};

fn collectScopedTypedefs(g: *Gen, module: *Module, visited: *std.AutoHashMapUnmanaged(*Module, void)) Error!void {
    if (visited.contains(module)) return;
    try visited.put(g.a, module, {});
    for (module.typedefs.keys(), module.typedefs.values()) |key, td| {
        if (td.data.typedef.scope == null) continue;
        const exported = if (module == g.root) key else try std.fmt.allocPrint(g.a, "@{s}:{s}", .{ module.name, key });
        if (g.scoped_typedefs.contains(exported)) return g.fail("Conflicting scoped typedef key '{s}'", .{exported});
        try g.scoped_typedefs.put(g.a, exported, .{ .typedef = td, .module = module });
    }
    for (module.import_prefixes.values()) |imported| try collectScopedTypedefs(g, imported, visited);
}

/// Scoped references retain their lexical context even after grouping expansion.
pub fn scopedTypeSchema(e: Emit, t: *const ast.TypeStmt) Error!?*Object {
    const resolved = @import("../module.zig").resolveTypedef(t, e.module) orelse return null;
    if (resolved.typedef.data.typedef.scope == null) return null;
    if (t.rangeRestriction().expression != null or t.lengthRestriction().expression != null or t.patterns().len > 0)
        return e.g.fail("cannot export restrictions on scoped typedef '{s}' in the native JSON form", .{resolved.typedef.name});
    for (e.g.scoped_typedefs.keys(), e.g.scoped_typedefs.values()) |key, entry| {
        if (entry.typedef != resolved.typedef) continue;
        const out = try newObject(e.g.a);
        try out.put(e.g.a, K.REF, str(try @import("../typedef_scope.zig").defsUri(e.g.a, key)));
        const xy = try newObject(e.g.a);
        try xy.put(e.g.a, K.xy.TYPE_CONTEXT, str(t.context orelse ""));
        try out.put(e.g.a, K.X_YANG, objVal(xy));
        return out;
    }
    return e.g.fail("Scoped typedef '{s}' is absent from the export catalog", .{resolved.typedef.name});
}

/// What `type_to_schema` emits with (Python's `_EMIT` context): the typedef names that
/// become `$ref`, the module the type is read in, and the leafref anchor.
pub const Emit = struct {
    g: *Gen,
    typedef_names: *const Names,
    module: *Module,
    anchor: Schema,
};

// ---------------------------------------------------------------------------
// Values

pub fn newObject(a: Allocator) error{OutOfMemory}!*Object {
    const o = try a.create(Object);
    o.* = .empty;
    return o;
}

pub fn str(s: []const u8) Val {
    return .{ .string = s };
}

pub fn objVal(o: *Object) Val {
    return .{ .object = o };
}

pub fn strList(a: Allocator, items: []const []const u8) error{OutOfMemory}!Val {
    const out = try a.alloc(Val, items.len);
    for (items, 0..) |s, i| out[i] = str(s);
    return .{ .array = out };
}

/// `dict(o)`: a shallow copy.
pub fn cloneObject(a: Allocator, o: *const Object) error{OutOfMemory}!*Object {
    const out = try a.create(Object);
    out.* = try o.clone(a);
    return out;
}

fn getObject(o: *const Object, key: []const u8) ?*Object {
    const v = o.get(key) orelse return null;
    return if (v == .object) v.object else null;
}

/// `_with_description`: `description` only when the text is not empty.
pub fn withDescription(a: Allocator, out: *Object, text: []const u8) error{OutOfMemory}!void {
    if (text.len > 0) try out.put(a, K.DESCRIPTION, str(text));
}

fn lessString(_: void, x: []const u8, y: []const u8) bool {
    return std.mem.order(u8, x, y) == .lt;
}

fn sortedStrings(a: Allocator, items: []const []const u8) error{OutOfMemory}![]const []const u8 {
    const out = try a.dupe([]const u8, items);
    std.mem.sort([]const u8, out, {}, lessString);
    return out;
}

/// `dict(sorted(o.items()))`.
fn sortedObject(a: Allocator, o: *const Object) error{OutOfMemory}!*Object {
    const out = try newObject(a);
    for (try sortedStrings(a, o.keys())) |k| try out.put(a, k, o.get(k).?);
    return out;
}

/// `str.strip()` on the whitespace Python strips.
pub fn pyStrip(s: []const u8) []const u8 {
    return std.mem.trim(u8, s, &refine_expand.pyWhitespace);
}

// ---------------------------------------------------------------------------
// Defaults

/// `_try_int_literal`.
fn tryIntLiteral(v: Val) ?i128 {
    switch (v) {
        .int => |i| return i,
        .string => |s| {
            const digits = if (s.len > 0 and s[0] == '-') s[1..] else s;
            if (digits.len == 0) return null;
            for (digits) |c| if (!std.ascii.isDigit(c)) return null;
            return std.fmt.parseInt(i128, s, 10) catch null;
        },
        else => return null,
    }
}

const Coerced = struct { value: Val, changed: bool };

/// `coerce_default_value` on any JSON value. `changed` is Python's `coerced is not value`.
fn coerceDefault(v: Val, type_name: ?[]const u8) Coerced {
    const unchanged: Coerced = .{ .value = v, .changed = false };
    const t = type_name orelse return unchanged;
    if (std.mem.eql(u8, t, registry.BOOLEAN)) {
        const is_true = jv.pyEql(v, .{ .bool = true }) or (v == .string and std.mem.eql(u8, v.string, "true"));
        const is_false = jv.pyEql(v, .{ .bool = false }) or (v == .string and std.mem.eql(u8, v.string, "false"));
        if (is_true) return .{ .value = .{ .bool = true }, .changed = !(v == .bool and v.bool) };
        if (is_false) return .{ .value = .{ .bool = false }, .changed = !(v == .bool and !v.bool) };
    }
    if (registry.get(t)) |b| if (b.bounds != null) {
        switch (v) {
            .int, .bool => return unchanged,
            .string => |s| if (xutils.pyInt(s)) |i| return .{ .value = .{ .int = i }, .changed = true },
            .float => |f| if (std.math.isFinite(f)) return .{ .value = .{ .int = @intFromFloat(@trunc(f)) }, .changed = true },
            else => {},
        }
    };
    if (registry.isDecimalName(t)) {
        switch (v) {
            .float => return unchanged,
            .int => |i| return .{ .value = .{ .float = @floatFromInt(i) }, .changed = true },
            .bool => |b| return .{ .value = .{ .float = if (b) 1.0 else 0.0 }, .changed = true },
            .string => |s| if (xutils.pyFloatText(s)) |f| return .{ .value = .{ .float = f }, .changed = true },
            else => {},
        }
    }
    return unchanged;
}

/// `_json_schema_default_value`: a YANG default as the JSON Schema literal of its type.
pub fn jsonSchemaDefaultValue(default: Val, yang_type_name: ?[]const u8, json_schema_type: ?[]const u8) Val {
    const type_name = yang_type_name orelse json_schema_type;
    const is_boolean = (if (type_name) |t| std.mem.eql(u8, t, "boolean") else false) or
        (if (json_schema_type) |t| std.mem.eql(u8, t, "boolean") else false);
    if (is_boolean) {
        if ((default == .bool and default.bool) or (default == .string and std.ascii.eqlIgnoreCase(default.string, "true"))) return .{ .bool = true };
        if ((default == .bool and !default.bool) or (default == .string and std.ascii.eqlIgnoreCase(default.string, "false"))) return .{ .bool = false };
    }
    if (yang_type_name) |y| if (std.mem.eql(u8, y, registry.UNION)) {
        if (tryIntLiteral(default)) |n| return .{ .int = n };
        return default;
    };
    var coerce_type = yang_type_name;
    const jst = json_schema_type orelse "";
    if (std.mem.eql(u8, jst, "integer") and (coerce_type == null or std.mem.eql(u8, coerce_type.?, "integer"))) coerce_type = registry.INT32;
    if (std.mem.eql(u8, jst, "number") and coerce_type == null) coerce_type = registry.DECIMAL64;
    const coerced = coerceDefault(default, coerce_type);
    if (coerced.changed) return coerced.value;
    if (std.mem.eql(u8, jst, "integer")) {
        if (tryIntLiteral(default)) |n| return .{ .int = n };
    }
    return default;
}

fn schemaTypeName(o: *const Object) ?[]const u8 {
    const v = o.get(K.TYPE) orelse return null;
    return if (v == .string) v.string else null;
}

// ---------------------------------------------------------------------------
// XPath

fn collectPrefixes(a: Allocator, e: ?*const xast.Expr, found: *std.StringArrayHashMapUnmanaged([]const u8)) error{OutOfMemory}!void {
    const node = e orelse return;
    switch (node.*) {
        .path => |p| for (p.segments) |seg| {
            if (seg.prefix()) |pre| if (seg.module) |m| try found.put(a, pre, m);
            try collectPrefixes(a, seg.predicate, found);
        },
        .binary => |b| {
            try collectPrefixes(a, b.left, found);
            try collectPrefixes(a, b.right, found);
        },
        .call => |c| for (c.args) |arg| try collectPrefixes(a, arg, found),
        .literal => {},
    }
}

/// `_with_xpath_prefixes`: the module each prefixed step is bound to.
pub fn withXpathPrefixes(a: Allocator, out: *Object, e: ?*const xast.Expr) error{OutOfMemory}!void {
    var found: std.StringArrayHashMapUnmanaged([]const u8) = .empty;
    try collectPrefixes(a, e, &found);
    if (found.count() == 0) return;
    const m = try newObject(a);
    for (try sortedStrings(a, found.keys())) |k| try m.put(a, k, str(found.get(k).?));
    try out.put(a, K.xy.XPATH_PREFIXES, objVal(m));
}

fn mustToJson(a: Allocator, m: *const ast.MustStmt) Error!Val {
    const out = try newObject(a);
    try out.put(a, K.must_entry.MUST, str(m.expression));
    try out.put(a, K.must_entry.ERROR_MESSAGE, str(m.error_message));
    if (m.error_app_tag.len > 0) try out.put(a, K.must_entry.ERROR_APP_TAG, str(m.error_app_tag));
    try withXpathPrefixes(a, out, m.ast);
    try withDescription(a, out, m.description);
    return objVal(out);
}

fn mustList(a: Allocator, musts: []const *ast.MustStmt) Error!Val {
    const out = try a.alloc(Val, musts.len);
    for (musts, 0..) |m, i| out[i] = try mustToJson(a, m);
    return .{ .array = out };
}

fn whenToJson(a: Allocator, w: *const ast.WhenStmt) Error!Val {
    const out = try newObject(a);
    try out.put(a, K.when_entry.CONDITION, str(w.expression));
    try withXpathPrefixes(a, out, w.ast);
    if (pyStrip(w.description).len > 0) try out.put(a, K.DESCRIPTION, str(w.description));
    if (w.evaluate_with_parent_context) try out.put(a, K.when_entry.EVALUATE_WITH_PARENT_CONTEXT, .{ .bool = true });
    return objVal(out);
}

/// `_leafref_path_string`.
pub fn leafrefPathString(a: Allocator, t: *const ast.TypeStmt) error{OutOfMemory}![]const u8 {
    if (t.pathAst()) |e| if (e.* == .path) return e.path.toString(a);
    return t.leafrefPath() orelse "";
}

// ---------------------------------------------------------------------------
// Schema tree navigation (leafref targets)

fn statementsOf(node: Schema) []const *Statement {
    return switch (node) {
        .none => &.{},
        .module => |m| m.statements.items,
        .stmt => |s| s.statements.items,
    };
}

/// `_locate_stmt_with_parent`.
fn locateParent(stmts: []const *Statement, parent: Schema, target: *const Statement) ?Schema {
    for (stmts) |s| {
        if (s == target) return parent;
        switch (s.kind()) {
            .choice => for (s.data.choice.cases.items) |case| {
                if (case == target) return .{ .stmt = s };
                if (locateParent(case.statements.items, .{ .stmt = case }, target)) |found| return found;
            },
            .leaf, .leaf_list, .anydata, .anyxml => {},
            else => if (locateParent(s.statements.items, .{ .stmt = s }, target)) |found| return found,
        }
    }
    return null;
}

/// `_schema_parent_of`: null for the module root.
fn schemaParentOf(module: *Module, node: Schema) ?Schema {
    return switch (node) {
        .stmt => |s| locateParent(module.statements.items, .{ .module = module }, s),
        else => null,
    };
}

/// `_leafref_context_parent`: a case parent is lifted past its choice.
fn leafrefContextParent(module: *Module, parent: Schema) Schema {
    if (parent == .stmt and parent.stmt.kind() == .case) {
        const choice = schemaParentOf(module, parent) orelse return .none;
        return schemaParentOf(module, choice) orelse .none;
    }
    return parent;
}

/// `_resolve_leafref_target_leaf`: the leaf a predicate-free leafref path names.
pub fn resolveLeafrefTargetLeaf(module: *Module, t: *const ast.TypeStmt, anchor: Schema) ?*Statement {
    const e = t.pathAst() orelse return null;
    if (e.* != .path) return null;
    const path = e.path;
    if (path.segments.len == 0) return null;
    for (path.segments) |seg| if (seg.predicate != null) return null;
    var current: Schema = if (path.is_absolute) .{ .module = module } else switch (anchor) {
        .none => return null,
        else => anchor,
    };
    for (path.segments) |seg| {
        if (std.mem.eql(u8, seg.step, ".")) continue;
        if (std.mem.eql(u8, seg.step, "..")) {
            if (current == .module and current.module == module) return null;
            current = schemaParentOf(module, current) orelse return null;
            continue;
        }
        const nxt = switch (current) {
            .none => null,
            else => schema_nav.child(current, seg.step),
        } orelse return null;
        current = .{ .stmt = nxt };
    }
    return if (current == .stmt and current.stmt.kind() == .leaf) current.stmt else null;
}

// ---------------------------------------------------------------------------
// Types

fn mergeUnits(a: Allocator, schema: *Object, units: []const u8) error{OutOfMemory}!void {
    if (units.len == 0) return;
    const xy = if (getObject(schema, K.X_YANG)) |o| try cloneObject(a, o) else try newObject(a);
    try xy.put(a, K.xy.UNITS, str(units));
    try schema.put(a, K.X_YANG, objVal(xy));
}

/// `_type_to_schema`: `{"type": "string"}` for no type, else the registry's schema plus
/// the type's `units`.
pub fn typeToSchema(g: *Gen, t: ?*const ast.TypeStmt, names: *const Names, module: *Module, anchor: Schema) Error!*Object {
    const ts = t orelse {
        const o = try newObject(g.a);
        try o.put(g.a, K.TYPE, str("string"));
        return o;
    };
    const out = try registry.typeToSchema(.{ .g = g, .typedef_names = names, .module = module, .anchor = anchor }, ts);
    try mergeUnits(g.a, out, ts.units);
    return out;
}

/// `identity_base_for_json`: `(base, $ref)` of one identityref base written in `scope`,
/// re-expressed in `module`'s scope. A base of another module is recorded for
/// `x-yang.imports`.
pub fn identityBaseForJson(g: *Gen, base: ast.IdentifierRef, scope: *Module, module: *Module) Error![2][]const u8 {
    const a = g.a;
    const pair = identity_graph.resolveBaseRef(scope, base) orelse
        return g.fail("cannot export identity base {f}: it does not resolve in module {f}", .{ repr(try formatRef(a, base)), repr(scope.name) });
    if (std.mem.eql(u8, pair.module.name, module.name)) {
        return .{ pair.name, try std.fmt.allocPrint(a, "#/{s}/{s}", .{ K.DEFS, pair.name }) };
    }
    try g.identities_used.append(a, pair);
    const key = try importKey(g, g.root, pair.module);
    return .{
        try std.fmt.allocPrint(a, "{s}:{s}", .{ key, pair.name }),
        try std.fmt.allocPrint(a, "#/{s}/{s}/{s}/{s}/{s}", .{ K.X_YANG, K.xy.IMPORTS, key, K.xy.IDENTITIES, pair.name }),
    };
}

/// `format_identifier_ref`.
pub fn formatRef(a: Allocator, ref: ast.IdentifierRef) error{OutOfMemory}![]const u8 {
    if (ref.prefix) |p| if (p.len > 0) return std.fmt.allocPrint(a, "{s}:{s}", .{ p, ref.name });
    return ref.name;
}

// ---------------------------------------------------------------------------
// Identities and `x-yang.imports`

/// `_import_key`: the prefix that imports `module`, else its name.
fn importKey(g: *Gen, root: *Module, module: *const Module) Error![]const u8 {
    for (root.import_prefixes.keys(), root.import_prefixes.values()) |prefix, imported| {
        if (imported == module or std.mem.eql(u8, imported.name, module.name)) return prefix;
    }
    if (root.import_prefixes.contains(module.name) or std.mem.eql(u8, module.name, root.ownPrefix())) {
        return g.fail("cannot export identities of module {f}: the name is also a prefix of module {f}", .{ repr(module.name), repr(root.name) });
    }
    return module.name;
}

const NameSet = std.StringArrayHashMapUnmanaged(void);
const NamesByModule = std.StringArrayHashMapUnmanaged(NameSet);

fn qualifiedIdentityName(a: Allocator, module: *const Module, local: []const u8) error{OutOfMemory}![]const u8 {
    return std.fmt.allocPrint(a, "{s}:{s}", .{ std.mem.trim(u8, module.prefix, "\"'"), local });
}

/// `_identity_to_def`: the identity's `$defs` entry. `only` limits the enum to the
/// identities an `x-yang.imports` stub carries.
fn identityToDef(g: *Gen, name: []const u8, identity: *Statement, module: *Module, only: ?*const NameSet) Error!Val {
    const a = g.a;
    var closure = try identity_graph.descendantClosure(a, module, name);
    var picked: std.ArrayList([]const u8) = .empty;
    for (closure.keys()) |n| {
        if (only) |o| if (!o.contains(n)) continue;
        try picked.append(a, n);
    }
    closure.deinit(a);
    const sorted = try sortedStrings(a, picked.items);
    const enum_vals = try a.alloc(Val, sorted.len);
    for (sorted, 0..) |n, i| enum_vals[i] = str(try qualifiedIdentityName(a, module, n));
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("string"));
    try out.put(a, K.ENUM, .{ .array = enum_vals });
    try withDescription(a, out, identity.description);
    const xy = try newObject(a);
    try xy.put(a, K.xy.TYPE, str(K.types.IDENTITY));
    const bases = identity.data.identity.bases.items;
    const base_vals = try a.alloc(Val, bases.len);
    for (bases, 0..) |b, i| base_vals[i] = str(try formatRef(a, b));
    try xy.put(a, K.xy.BASES, .{ .array = base_vals });
    if (identity.if_features.items.len > 0) try xy.put(a, K.xy.IF_FEATURES, try strList(a, identity.if_features.items));
    try out.put(a, K.X_YANG, objVal(xy));
    if (only == null) {
        const names = try typedefNameSet(a, module);
        try stampExtensions(g, xy, identity.statements.items, &names, module);
    }
    return objVal(out);
}

fn typedefNameSet(a: Allocator, module: *const Module) error{OutOfMemory}!Names {
    var names: Names = .empty;
    for (module.typedefs.keys()) |k| try names.put(a, k, {});
    return names;
}

/// `_identity_stub`: an `x-yang.imports` entry with the identities in `names` and the
/// modules their bases name.
fn identityStub(g: *Gen, module: *Module, names: *const NamesByModule) Error!*Object {
    const a = g.a;
    const identities = try newObject(a);
    const imports = try newObject(a);
    const empty: NameSet = .empty;
    const mine = names.getPtr(module.name) orelse &empty;
    for (try sortedStrings(a, mine.keys())) |name| {
        const identity = module.identities.get(name) orelse continue;
        try identities.put(a, name, try identityToDef(g, name, identity, module, mine));
        for (identity.data.identity.bases.items) |base| {
            const pair = identity_graph.resolveBaseRef(module, base) orelse {
                return g.fail("cannot export identity {f} of module {f}: base {f} does not resolve there", .{ repr(name), repr(module.name), repr(try formatRef(a, base)) });
            };
            if (!std.mem.eql(u8, pair.module.name, module.name)) {
                try imports.put(a, base.prefix orelse "", objVal(try identityStub(g, pair.module, names)));
            }
        }
    }
    const stub = try newObject(a);
    try stub.put(a, K.xy.MODULE, str(module.name));
    try stub.put(a, K.xy.NAMESPACE, str(module.namespace));
    try stub.put(a, K.xy.PREFIX, str(module.prefix));
    if (imports.count() > 0) try stub.put(a, K.xy.IMPORTS, objVal(try sortedObject(a, imports)));
    try stub.put(a, K.xy.IDENTITIES, objVal(identities));
    return stub;
}

fn need(a: Allocator, names: *NamesByModule, pairs: []const identity_graph.Pair) error{OutOfMemory}!void {
    for (pairs) |p| {
        const gop = try names.getOrPut(a, p.module.name);
        if (!gop.found_existing) gop.value_ptr.* = .empty;
        try gop.value_ptr.put(a, p.name, {});
    }
}

/// `_imports_for_json`: the imported identities the module needs, so the form resolves
/// them without `import`.
fn importsForJson(g: *Gen, root: *Module) Error!*Object {
    const a = g.a;
    for (root.identities.keys(), root.identities.values()) |name, identity| {
        for (identity.data.identity.bases.items) |base| {
            if (identity_graph.resolveBaseRef(root, base) == null) {
                return g.fail("cannot export identity {f}: base {f} does not resolve in module {f}", .{ repr(name), repr(try formatRef(a, base)), repr(root.name) });
            }
        }
    }
    const used = g.identities_used.items;
    var names: NamesByModule = .empty;
    const Candidate = struct { module: *Module, name: []const u8 };
    var candidates: std.ArrayList(Candidate) = .empty;
    for (root.identities.keys()) |n| try candidates.append(a, .{ .module = root, .name = n });
    for (root.import_prefixes.values()) |m| for (m.identities.keys()) |n| try candidates.append(a, .{ .module = m, .name = n });
    for (candidates.items) |c| {
        const closure = try identity_graph.ancestorClosure(a, .{ .module = c.module, .name = c.name });
        var wanted = c.module == root;
        if (!wanted) for (closure) |p| {
            for (used) |u| if (std.mem.eql(u8, u.module.name, p.module.name) and std.mem.eql(u8, u.name, p.name)) {
                wanted = true;
            };
        };
        if (wanted) try need(a, &names, closure);
    }
    try need(a, &names, used);
    _ = names.orderedRemove(root.name);
    const out = try newObject(a);
    var modules: std.ArrayList(*Module) = .empty;
    try modules.appendSlice(a, root.import_prefixes.values());
    for (used) |u| try modules.append(a, u.module);
    for (modules.items) |m| {
        if (names.contains(m.name)) try out.put(a, try importKey(g, root, m), objVal(try identityStub(g, m, &names)));
    }
    return sortedObject(a, out);
}

// ---------------------------------------------------------------------------
// Extensions

fn extensionDefJson(a: Allocator, ext: *const Statement) error{OutOfMemory}!Val {
    const d = ext.data.extension;
    const out = try newObject(a);
    if (d.argument_name.len > 0) try out.put(a, K.xy.ARGUMENT, str(d.argument_name));
    if (d.argument_yin_element) |y| try out.put(a, K.xy.YIN_ELEMENT, .{ .bool = y });
    if (ext.description.len > 0) try out.put(a, K.DESCRIPTION, str(ext.description));
    if (ext.reference.len > 0) try out.put(a, K.xy.REFERENCE, str(ext.reference));
    return objVal(out);
}

/// Extensions with callbacks need a reversible form. RFC 8791 has one (#164).
fn rejectSemanticExtension(g: *Gen, inv: *const Statement) Error!void {
    const d = inv.data.extension_invocation;
    const ext = d.resolved_extension;
    if (capabilities.isRfc8791(inv, "structure") or capabilities.isRfc8791(inv, "augment-structure")) return;
    if (capabilities.find(ext.data.extension.module_name, ext.name) == null) return;
    return g.fail("cannot export extension invocation {f}: extension {s}:{s} is applied when the module is parsed and is not re-applied when the native JSON form is loaded", .{ repr(inv.name), d.resolved_module, ext.name });
}

/// The loaded module named `name`: the root or a module it reaches through `import`.
fn findModule(a: Allocator, root: *Module, name: []const u8) error{OutOfMemory}!?*Module {
    var seen: std.AutoArrayHashMapUnmanaged(*Module, void) = .empty;
    try seen.put(a, root, {});
    var i: usize = 0;
    while (i < seen.count()) : (i += 1) {
        const m = seen.keys()[i];
        if (std.mem.eql(u8, m.name, name)) return m;
        for (m.import_prefixes.values()) |im| try seen.put(a, im, {});
    }
    return null;
}

/// `_record_imported_extension`: an extension of another module travels on its stub.
fn recordImportedExtension(g: *Gen, inv: *const Statement) Error!void {
    const d = inv.data.extension_invocation;
    if (std.mem.eql(u8, d.resolved_module, g.root.name)) return;
    const owner = try findModule(g.a, g.root, d.resolved_module) orelse
        return g.fail("cannot export extension invocation {f}: module {f} is not loaded", .{ repr(inv.name), repr(d.resolved_module) });
    for (g.extensions_used.items) |u| {
        if (std.mem.eql(u8, u.owner.name, owner.name) and std.mem.eql(u8, u.name, d.resolved_extension.name)) return;
    }
    try g.extensions_used.append(g.a, .{ .owner = owner, .name = d.resolved_extension.name });
}

fn isContainerLike(k: ast.Kind) bool {
    return switch (k) {
        .container, .notification, .input, .output => true,
        else => false,
    };
}

/// `_one_extension_invocation`: `{name, argument?, ...}` plus a nested body, in source order.
fn oneExtensionInvocation(g: *Gen, inv: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    try rejectSemanticExtension(g, inv);
    try recordImportedExtension(g, inv);
    const d = inv.data.extension_invocation;
    const out = try newObject(a);
    try out.put(a, K.NAME, str(inv.name));
    if (d.argument) |arg| try out.put(a, K.xy.ARGUMENT, str(arg));
    if (inv.description.len > 0) try out.put(a, K.DESCRIPTION, str(inv.description));
    if (inv.reference.len > 0) try out.put(a, K.xy.REFERENCE, str(inv.reference));
    if (inv.if_features.items.len > 0) try out.put(a, K.xy.IF_FEATURES, try strList(a, inv.if_features.items));
    if (inv.when) |w| if (w.expression.len > 0) try out.put(a, K.xy.WHEN, try whenToJson(a, w));
    if (inv.must_statements.items.len > 0) try out.put(a, K.xy.MUST, try mustList(a, inv.must_statements.items));
    if (inv.config) |c| try out.put(a, K.xy.CONFIG, .{ .bool = c });
    var body: std.ArrayList(Val) = .empty;
    for (inv.statements.items) |s| {
        switch (s.kind()) {
            .extension_invocation => {
                const item = try newObject(a);
                try item.put(a, K.xy.EXTENSION, try oneExtensionInvocation(g, s, names, module));
                try body.append(a, objVal(item));
            },
            .container, .notification, .input, .output, .list, .leaf, .leaf_list, .choice, .anydata, .anyxml => {
                const prop = try statementToProperty(g, s, names, module, .{ .stmt = inv }) orelse
                    return g.fail("cannot export extension invocation {f}: nested statement {f} is not representable in the native JSON form", .{ repr(inv.name), repr(s.name) });
                const item = try newObject(a);
                try item.put(a, "node", str(try propertyKey(a, s, module)));
                try item.put(a, "schema", prop);
                try body.append(a, objVal(item));
            },
            else => return g.fail("cannot export extension invocation {f}: nested statement {s} {f} is not representable in the native JSON form", .{ repr(inv.name), ast.pythonClassName(s.kind()), repr(s.name) }),
        }
    }
    if (body.items.len > 0) try out.put(a, K.xy.BODY, .{ .array = body.items });
    return objVal(out);
}

/// `_stamp_extensions`: `x-yang.extensions` for the invocations among `statements`.
fn stampExtensions(g: *Gen, xyang: *Object, statements: []const *Statement, names: *const Names, module: *Module) Error!void {
    if (try extensionInvocationsJson(g, statements, names, module)) |v| try xyang.put(g.a, K.xy.EXTENSIONS, v);
}

fn extensionInvocationsJson(g: *Gen, statements: []const *Statement, names: *const Names, module: *Module) Error!?Val {
    var out: std.ArrayList(Val) = .empty;
    for (statements) |s| {
        if (s.kind() == .extension_invocation) try out.append(g.a, try oneExtensionInvocation(g, s, names, module));
    }
    if (out.items.len == 0) return null;
    return .{ .array = out.items };
}

/// `_merge_extension_imports`: invoked imported extensions on the import stubs.
fn mergeExtensionImports(g: *Gen, root: *Module, imports: *Object) Error!*Object {
    const a = g.a;
    var owners: std.ArrayList(*Module) = .empty;
    var by_owner: std.StringArrayHashMapUnmanaged(std.ArrayList([]const u8)) = .empty;
    for (g.extensions_used.items) |u| {
        const gop = try by_owner.getOrPut(a, u.owner.name);
        if (!gop.found_existing) {
            gop.value_ptr.* = .empty;
            try owners.append(a, u.owner);
        }
        const already = for (gop.value_ptr.items) |n| {
            if (std.mem.eql(u8, n, u.name)) break true;
        } else false;
        if (!already) try gop.value_ptr.append(a, u.name);
    }
    for (owners.items) |owner| {
        const key = try importKey(g, root, owner);
        const stub = getObject(imports, key) orelse blk: {
            const s = try newObject(a);
            try s.put(a, K.xy.MODULE, str(owner.name));
            try s.put(a, K.xy.NAMESPACE, str(owner.namespace));
            try s.put(a, K.xy.PREFIX, str(owner.prefix));
            try imports.put(a, key, objVal(s));
            break :blk s;
        };
        const ext_map = try newObject(a);
        for (try sortedStrings(a, by_owner.get(owner.name).?.items)) |name| {
            const ext = owner.extensions.get(name) orelse
                return g.fail("cannot export extension {s}:{s}: the extension definition is not in that module", .{ owner.name, name });
            try ext_map.put(a, name, try extensionDefJson(a, ext));
        }
        try stub.put(a, K.xy.EXTENSION, objVal(ext_map));
    }
    return sortedObject(a, imports);
}

fn findExtensionInvocation(s: *Statement) ?*Statement {
    if (s.kind() == .extension_invocation) return s;
    for (s.statements.items) |child| if (findExtensionInvocation(child)) |found| return found;
    if (s.kind() == .choice) {
        for (s.data.choice.cases.items) |case| if (findExtensionInvocation(case)) |found| return found;
    }
    return null;
}

/// `_placement_node`: a node the form carries, so an invocation on it has a place.
fn placementNode(s: *const Statement) bool {
    return switch (s.kind()) {
        .container, .notification, .input, .output, .list, .leaf, .leaf_list, .choice, .case, .anydata, .anyxml, .rpc, .action, .typedef, .identity => true,
        else => false,
    };
}

fn usesQName(a: Allocator, u: *const Statement) error{OutOfMemory}![]const u8 {
    const d = u.data.uses;
    if (d.grouping_prefix) |p| if (p.len > 0) return std.fmt.allocPrint(a, "{s}:{s}", .{ p, d.grouping_name });
    return d.grouping_name;
}

fn failInsideUses(g: *Gen, uses: *Statement) Error!void {
    for (uses.statements.items) |child| if (findExtensionInvocation(child)) |found| {
        return g.fail("cannot export extension invocation {f}: it is inside uses {f}, which the native JSON form does not carry", .{ repr(found.name), repr(try usesQName(g.a, uses)) });
    };
}

fn walkPlaced(g: *Gen, owner: *Statement, placed: bool) Error!void {
    for (owner.statements.items) |child| {
        switch (child.kind()) {
            .extension_invocation => {
                try rejectSemanticExtension(g, child);
                if (!placed) {
                    return g.fail("cannot export extension invocation {f}: it is on {s} {f}, which the native JSON form does not carry", .{ repr(child.name), ast.pythonClassName(owner.kind()), repr(owner.name) });
                }
                try walkPlaced(g, child, true);
            },
            .grouping, .extension => {},
            .uses => try failInsideUses(g, child),
            else => try walkPlaced(g, child, placementNode(child)),
        }
    }
    if (owner.kind() == .choice) {
        for (owner.data.choice.cases.items) |case| try walkPlaced(g, case, true);
    }
}

/// `_assert_extensions_placed`: fail when an invocation sits on a construct the form does
/// not carry.
fn assertExtensionsPlaced(g: *Gen, module: *Module) Error!void {
    for (module.statements.items) |s| {
        switch (s.kind()) {
            .extension_invocation => {
                try rejectSemanticExtension(g, s);
                try walkPlaced(g, s, true);
            },
            .grouping, .extension => {},
            .uses => try failInsideUses(g, s),
            else => try walkPlaced(g, s, placementNode(s)),
        }
    }
    for (module.typedefs.values()) |td| try walkPlaced(g, td, true);
    for (module.identities.values()) |id| try walkPlaced(g, id, true);
}

// ---------------------------------------------------------------------------
// Statement copies and `uses`

/// `copy_yang_statement` dispatches on the exact Python class; a class it has no copier
/// for raises `TypeError` (the first one met, children before their parent).
fn uncopyable(s: *const Statement) ?ast.Kind {
    for (s.statements.items) |child| if (uncopyable(child)) |k| return k;
    switch (s.kind()) {
        .choice => for (s.data.choice.cases.items) |case| if (uncopyable(case)) |k| return k,
        .uses => for (s.data.uses.augmentations.items) |aug| if (uncopyable(aug)) |k| return k,
        else => {},
    }
    return switch (s.kind()) {
        .notification, .deviation, .grouping, .identity, .refine => s.kind(),
        else => null,
    };
}

fn copyStatement(g: *Gen, s: *const Statement) Error!*Statement {
    if (uncopyable(s)) |k| return g.reporter.fail(.semantic, "Unsupported statement type for copy: {s}", .{ast.pythonClassName(k)});
    return refine_expand.copyStatement(&g.reporter, s);
}

/// `_expand_uses_for_json`: expand `uses` on a copy so the module tree is not changed.
fn expandForJson(g: *Gen, statements: []const *Statement, module: *Module) Error![]const *Statement {
    var copies: std.ArrayList(*Statement) = .empty;
    for (statements) |s| try copies.append(g.a, try copyStatement(g, s));
    const out = try uses_expand.expandUsesInStatementsOf(&g.reporter, module, copies.items);
    return out.items;
}

fn copyAll(g: *Gen, statements: []const *Statement) Error![]const *Statement {
    var copies: std.ArrayList(*Statement) = .empty;
    for (statements) |s| try copies.append(g.a, try copyStatement(g, s));
    return copies.items;
}

// ---------------------------------------------------------------------------
// Data nodes

const XyangOpts = struct {
    key: ?[]const u8 = null,
    musts: []const *ast.MustStmt = &.{},
    when: ?*const ast.WhenStmt = null,
    presence: ?[]const u8 = null,
    mandatory: bool = false,
    config: ?bool = null,
    if_features: []const []const u8 = &.{},
    units: []const u8 = "",
};

/// `_build_xyang`.
fn buildXyang(a: Allocator, node_type: []const u8, o: XyangOpts) Error!*Object {
    const out = try newObject(a);
    try out.put(a, K.xy.TYPE, str(node_type));
    if (o.key) |k| if (k.len > 0) try out.put(a, K.xy.KEY, str(k));
    if (o.musts.len > 0) try out.put(a, K.xy.MUST, try mustList(a, o.musts));
    if (o.when) |w| if (w.expression.len > 0) try out.put(a, K.xy.WHEN, try whenToJson(a, w));
    if (o.presence) |p| if (p.len > 0) try out.put(a, K.xy.PRESENCE, str(p));
    if (o.mandatory) try out.put(a, K.xy.MANDATORY, .{ .bool = true });
    if (o.config) |c| try out.put(a, K.xy.CONFIG, .{ .bool = c });
    if (o.if_features.len > 0) try out.put(a, K.xy.IF_FEATURES, try strList(a, o.if_features));
    if (o.units.len > 0) try out.put(a, K.xy.UNITS, str(o.units));
    return out;
}

/// `_property_key`: `module:name` for a node another module defines (augment).
pub fn propertyKey(a: Allocator, s: *const Statement, module: *const Module) error{OutOfMemory}![]const u8 {
    if (s.defining_module) |owner| if (owner.len > 0 and !std.mem.eql(u8, owner, module.name)) {
        return std.fmt.allocPrint(a, "{s}:{s}", .{ owner, s.name });
    };
    return s.name;
}

fn mandatorySchemaChild(s: *const Statement) bool {
    return switch (s.data) {
        .leaf => |d| d.mandatory,
        .anydata => |d| d.mandatory,
        .anyxml => |d| d.mandatory,
        else => false,
    };
}

const PropertyMap = struct { props: *Object, required: std.ArrayList([]const u8) };

/// `_child_property_map`: `properties` and the mandatory leaves for `required`.
fn childPropertyMap(g: *Gen, children: []const *Statement, names: *const Names, module: *Module, parent: Schema) Error!PropertyMap {
    var out: PropertyMap = .{ .props = try newObject(g.a), .required = .empty };
    for (children) |child| {
        const prop = try statementToProperty(g, child, names, module, parent) orelse continue;
        const key = try propertyKey(g.a, child, module);
        try out.props.put(g.a, key, prop);
        if (mandatorySchemaChild(child)) try out.required.append(g.a, key);
    }
    return out;
}

/// `_partition_choice_sibling_statements`: the non-choice siblings and the sole choice.
fn partitionChoice(a: Allocator, statements: []const *Statement) error{OutOfMemory}!struct { others: []const *Statement, choice: ?*Statement } {
    var choices: usize = 0;
    var the_choice: ?*Statement = null;
    var others: std.ArrayList(*Statement) = .empty;
    for (statements) |s| {
        if (s.kind() == .choice) {
            choices += 1;
            the_choice = s;
        } else try others.append(a, s);
    }
    if (choices == 1) return .{ .others = others.items, .choice = the_choice };
    return .{ .others = statements, .choice = null };
}

fn dedupe(a: Allocator, items: []const []const u8) error{OutOfMemory}![]const []const u8 {
    var seen: NameSet = .empty;
    for (items) |s| try seen.put(a, s, {});
    return seen.keys();
}

fn sortedUnion(a: Allocator, x: []const []const u8, y: []const []const u8) error{OutOfMemory}![]const []const u8 {
    var seen: NameSet = .empty;
    for (x) |s| try seen.put(a, s, {});
    for (y) |s| try seen.put(a, s, {});
    return sortedStrings(a, seen.keys());
}

fn stringItems(a: Allocator, v: ?Val) error{OutOfMemory}![]const []const u8 {
    const value = v orelse return &.{};
    if (value != .array) return &.{};
    var out: std.ArrayList([]const u8) = .empty;
    for (value.array) |item| if (item == .string) try out.append(a, item.string);
    return out.items;
}

fn isEmptyBranch(o: *const Object) bool {
    const t = o.get(K.TYPE) orelse return false;
    const mp = o.get(K.MAX_PROPERTIES) orelse return false;
    return t == .string and std.mem.eql(u8, t.string, "object") and mp == .int and mp.int == 0;
}

/// `_merge_oneof_branches_with_base`: each `oneOf` branch with the common properties.
fn mergeOneOfWithBase(a: Allocator, one_of: []const Val, base_props: *const Object, base_required: []const []const u8) Error!Val {
    var merged: std.ArrayList(Val) = .empty;
    const base_req_unique = try dedupe(a, base_required);
    for (one_of) |bv| {
        const branch = bv.object;
        if (isEmptyBranch(branch)) {
            if (base_props.count() > 0 or base_required.len > 0) {
                const o = try newObject(a);
                try o.put(a, K.TYPE, str("object"));
                try o.put(a, K.PROPERTIES, objVal(try cloneObject(a, base_props)));
                try o.put(a, K.REQUIRED, try strList(a, base_req_unique));
                try o.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
                try merged.append(a, objVal(o));
            } else {
                try merged.append(a, objVal(try cloneObject(a, branch)));
            }
            continue;
        }
        const props = try cloneObject(a, base_props);
        if (getObject(branch, K.PROPERTIES)) |bp| for (bp.keys(), bp.values()) |k, v| try props.put(a, k, v);
        const o = try newObject(a);
        try o.put(a, K.TYPE, str("object"));
        try o.put(a, K.PROPERTIES, objVal(props));
        try o.put(a, K.REQUIRED, try strList(a, try sortedUnion(a, base_required, try stringItems(a, branch.get(K.REQUIRED)))));
        try o.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
        if (branch.get(K.DESCRIPTION)) |d| if (d == .string and d.string.len > 0) try o.put(a, K.DESCRIPTION, d);
        if (getObject(branch, K.X_YANG)) |xy| if (xy.count() > 0) try o.put(a, K.X_YANG, objVal(try cloneObject(a, xy)));
        try merged.append(a, objVal(o));
    }
    return .{ .array = merged.items };
}

/// `_choice_meta_xyang`: `x-yang.choice` of a hoisted choice.
fn choiceMetaXyang(g: *Gen, choice: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const meta = try newObject(a);
    try meta.put(a, K.NAME, str(choice.name));
    try withDescription(a, meta, choice.description);
    try meta.put(a, K.xy.MANDATORY, .{ .bool = choice.data.choice.mandatory });
    if (choice.if_features.items.len > 0) try meta.put(a, K.xy.IF_FEATURES, try strList(a, choice.if_features.items));
    if (choice.config) |c| try meta.put(a, K.xy.CONFIG, .{ .bool = c });
    try stampExtensions(g, meta, choice.statements.items, names, module);
    return objVal(meta);
}

/// `_choice_to_object_body`: the choice as `oneOf`, one full object branch per case.
fn choiceToObjectBody(g: *Gen, choice: *Statement, names: *const Names, module: *Module, leafref_parent: Schema) Error!*Object {
    const a = g.a;
    var branches: std.ArrayList(Val) = .empty;
    var entries: usize = 0;
    for (choice.data.choice.cases.items) |case| {
        const case_props = try newObject(a);
        var case_keys: std.ArrayList([]const u8) = .empty;
        for (case.statements.items) |s| {
            const prop = try statementToProperty(g, s, names, module, leafref_parent) orelse continue;
            const key = try propertyKey(a, s, module);
            try case_props.put(a, key, prop);
            try case_keys.append(a, key);
        }
        if (case_keys.items.len == 0) continue;
        entries += 1;
        const case_xy = try newObject(a);
        try case_xy.put(a, K.NAME, str(case.name));
        if (case.if_features.items.len > 0) try case_xy.put(a, K.xy.IF_FEATURES, try strList(a, case.if_features.items));
        try stampExtensions(g, case_xy, case.statements.items, names, module);
        const case_obj = try newObject(a);
        try case_obj.put(a, K.TYPE, str("object"));
        try withDescription(a, case_obj, case.description);
        try case_obj.put(a, K.PROPERTIES, objVal(case_props));
        try case_obj.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
        try case_obj.put(a, K.REQUIRED, try strList(a, case_keys.items));
        try case_obj.put(a, K.X_YANG, objVal(case_xy));
        try branches.append(a, objVal(case_obj));
    }
    const out = try newObject(a);
    try withDescription(a, out, choice.description);
    const mandatory = choice.data.choice.mandatory;
    if (mandatory and entries > 0) {
        try out.put(a, K.ONE_OF, .{ .array = branches.items });
    } else if (!mandatory and entries > 1) {
        const empty = try newObject(a);
        try empty.put(a, K.TYPE, str("object"));
        try empty.put(a, K.MAX_PROPERTIES, .{ .int = 0 });
        var all: std.ArrayList(Val) = .empty;
        try all.append(a, objVal(empty));
        try all.appendSlice(a, branches.items);
        try out.put(a, K.ONE_OF, .{ .array = all.items });
    }
    return out;
}

fn containerXyang(g: *Gen, s: *Statement) Error!*Object {
    return buildXyang(g.a, "container", .{
        .musts = s.must_statements.items,
        .when = s.when,
        .presence = presenceOf(s),
        .if_features = s.if_features.items,
        .config = s.config,
    });
}

fn presenceOf(s: *const Statement) ?[]const u8 {
    return switch (s.data) {
        .container, .notification, .input, .output => |c| c.presence,
        else => null,
    };
}

fn containerToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const children = try expandForJson(g, s.statements.items, module);
    const part = try partitionChoice(a, children);
    if (part.choice) |ch| if (part.others.len > 0) {
        const base = try childPropertyMap(g, part.others, names, module, .{ .stmt = s });
        const body = try choiceToObjectBody(g, ch, names, module, .{ .stmt = s });
        const xy = try containerXyang(g, s);
        try xy.put(a, K.xy.CHOICE, try choiceMetaXyang(g, ch, names, module));
        try stampExtensions(g, xy, children, names, module);
        const out = try newObject(a);
        try out.put(a, K.TYPE, str("object"));
        try withDescription(a, out, s.description);
        try out.put(a, K.X_YANG, objVal(xy));
        if (body.get(K.ONE_OF)) |one_of| {
            try out.put(a, K.ONE_OF, try mergeOneOfWithBase(a, one_of.array, base.props, base.required.items));
        }
        return objVal(out);
    };
    if (children.len == 1 and children[0].kind() == .choice) {
        const ch = children[0];
        const body = try choiceToObjectBody(g, ch, names, module, .{ .stmt = s });
        const xy = try containerXyang(g, s);
        try xy.put(a, K.xy.CHOICE, try choiceMetaXyang(g, ch, names, module));
        try stampExtensions(g, xy, children, names, module);
        const out = try newObject(a);
        try out.put(a, K.TYPE, str("object"));
        try withDescription(a, out, s.description);
        try out.put(a, K.X_YANG, objVal(xy));
        if (body.get(K.ONE_OF)) |one_of| try out.put(a, K.ONE_OF, one_of);
        return objVal(out);
    }
    const map = try childPropertyMap(g, children, names, module, .{ .stmt = s });
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("object"));
    try withDescription(a, out, s.description);
    const xy = try containerXyang(g, s);
    try out.put(a, K.X_YANG, objVal(xy));
    try stampExtensions(g, xy, children, names, module);
    if (map.props.count() > 0) try out.put(a, K.PROPERTIES, objVal(map.props));
    try out.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
    if (map.required.items.len > 0) try out.put(a, K.REQUIRED, try strList(a, map.required.items));
    return objVal(out);
}

/// `_list_items_object_schema`: one list entry, and `x-yang.choice` of a hoisted choice.
fn listItems(g: *Gen, children: []const *Statement, s: *Statement, names: *const Names, module: *Module) Error!struct { items: *Object, choice: ?Val } {
    const a = g.a;
    const part = try partitionChoice(a, children);
    if (part.choice) |ch| if (part.others.len > 0) {
        const base = try childPropertyMap(g, part.others, names, module, .{ .stmt = s });
        const body = try choiceToObjectBody(g, ch, names, module, .{ .stmt = s });
        const items = try newObject(a);
        try items.put(a, K.TYPE, str("object"));
        if (body.get(K.ONE_OF)) |one_of| {
            try items.put(a, K.ONE_OF, try mergeOneOfWithBase(a, one_of.array, base.props, base.required.items));
        } else {
            try items.put(a, K.PROPERTIES, objVal(try cloneObject(a, base.props)));
            try items.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
            if (base.required.items.len > 0) try items.put(a, K.REQUIRED, try strList(a, base.required.items));
        }
        return .{ .items = items, .choice = try choiceMetaXyang(g, ch, names, module) };
    };
    if (children.len == 1 and children[0].kind() == .choice) {
        const ch = children[0];
        const body = try choiceToObjectBody(g, ch, names, module, .{ .stmt = s });
        const items = try newObject(a);
        try items.put(a, K.TYPE, str("object"));
        if (body.get(K.ONE_OF)) |one_of| {
            try items.put(a, K.ONE_OF, one_of);
        } else {
            try items.put(a, K.PROPERTIES, objVal(try newObject(a)));
            try items.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
        }
        return .{ .items = items, .choice = try choiceMetaXyang(g, ch, names, module) };
    }
    const map = try childPropertyMap(g, children, names, module, .{ .stmt = s });
    const items = try newObject(a);
    try items.put(a, K.TYPE, str("object"));
    try items.put(a, K.PROPERTIES, objVal(map.props));
    try items.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
    if (map.required.items.len > 0) try items.put(a, K.REQUIRED, try strList(a, map.required.items));
    return .{ .items = items, .choice = null };
}

fn listToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const d = s.data.list;
    // Like the parser, lists refined to max-elements 0 keep their `uses` (the xFrame
    // meta-model breaks composite recursion that way).
    const children = if (d.max_elements != null and d.max_elements.? == 0)
        try copyAll(g, s.statements.items)
    else
        try expandForJson(g, s.statements.items, module);
    const xy = try buildXyang(a, "list", .{
        .key = d.key,
        .musts = s.must_statements.items,
        .when = s.when,
        .if_features = s.if_features.items,
        .config = s.config,
    });
    const li = try listItems(g, children, s, names, module);
    if (li.choice) |c| try xy.put(a, K.xy.CHOICE, c);
    if (d.unique.items.len > 0) {
        const uniq = try a.alloc(Val, d.unique.items.len);
        for (d.unique.items, 0..) |paths, i| uniq[i] = try strList(a, paths);
        try xy.put(a, K.xy.UNIQUE, .{ .array = uniq });
    }
    try stampExtensions(g, xy, children, names, module);
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("array"));
    try out.put(a, K.ITEMS, objVal(li.items));
    try withDescription(a, out, s.description);
    try out.put(a, K.X_YANG, objVal(xy));
    if (d.min_elements) |n| try out.put(a, K.MIN_ITEMS, .{ .int = n });
    if (d.max_elements) |n| try out.put(a, K.MAX_ITEMS, .{ .int = n });
    return objVal(out);
}

/// `_leaf_yang_type_name`: the built-in a default is coerced to.
fn leafYangTypeName(t: ?*const ast.TypeStmt, names: *const Names, module: *Module) ?[]const u8 {
    const ts = t orelse return null;
    if (names.contains(ts.name)) {
        const resolved = @import("../module.zig").resolveTypedef(ts, module) orelse return null;
        const td = resolved.typedef;
        if (td.kind() != .typedef) return null;
        const inner = td.data.typedef.type orelse return null;
        return inner.name;
    }
    return ts.name;
}

fn leafToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module, parent: Schema) Error!Val {
    const a = g.a;
    const d = s.data.leaf;
    const t = d.type;
    const opts: XyangOpts = .{
        .musts = s.must_statements.items,
        .when = s.when,
        .mandatory = d.mandatory,
        .if_features = s.if_features.items,
        .units = s.units,
        .config = s.config,
    };
    var out: *Object = undefined;
    const local_td = if (t) |ts| module.typedefs.get(ts.name) else null;
    const resolved = if (t) |ts| @import("../module.zig").resolveTypedef(ts, module) else null;
    if (t != null and local_td != null and local_td.?.data.typedef.scope == null and resolved != null and resolved.?.typedef == local_td.?) {
        out = try newObject(a);
        try out.put(a, K.REF, str(try @import("../typedef_scope.zig").defsUri(a, t.?.name)));
        try withDescription(a, out, s.description);
        const xy = try buildXyang(a, "leaf", opts);
        try out.put(a, K.X_YANG, objVal(xy));
        try stampExtensions(g, xy, s.statements.items, names, module);
    } else {
        const anchor = leafrefContextParent(module, parent);
        const type_schema = try typeToSchema(g, t, names, module, anchor);
        const xy = try buildXyang(a, "leaf", opts);
        if (getObject(type_schema, K.X_YANG)) |txy| if (txy.count() > 0) {
            for (txy.keys(), txy.values()) |k, v| try xy.put(a, k, v);
        };
        out = try newObject(a);
        for (type_schema.keys(), type_schema.values()) |k, v| {
            if (std.mem.eql(u8, k, K.X_YANG) or std.mem.eql(u8, k, K.DESCRIPTION)) continue;
            try out.put(a, k, v);
        }
        try withDescription(a, out, s.description);
        try stampExtensions(g, xy, s.statements.items, names, module);
        try out.put(a, K.X_YANG, objVal(xy));
    }
    if (d.default) |def| {
        try out.put(a, K.DEFAULT, jsonSchemaDefaultValue(str(def), leafYangTypeName(t, names, module), schemaTypeName(out)));
    }
    return objVal(out);
}

fn anyToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const out = try newObject(a);
    try out.put(a, K.TYPE, try strList(a, &.{ "array", "boolean", "integer", "null", "number", "object", "string" }));
    try withDescription(a, out, s.description);
    const mandatory = switch (s.data) {
        .anydata => |d| d.mandatory,
        .anyxml => |d| d.mandatory,
        else => false,
    };
    const xy = try buildXyang(a, if (s.kind() == .anydata) K.types.ANYDATA else K.types.ANYXML, .{
        .musts = s.must_statements.items,
        .when = s.when,
        .mandatory = mandatory,
        .if_features = s.if_features.items,
    });
    try out.put(a, K.X_YANG, objVal(xy));
    try stampExtensions(g, xy, s.statements.items, names, module);
    return objVal(out);
}

fn leafListToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module, parent: Schema) Error!Val {
    const a = g.a;
    const d = s.data.leaf_list;
    const items = try typeToSchema(g, d.type, names, module, leafrefContextParent(module, parent));
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("array"));
    try out.put(a, K.ITEMS, objVal(items));
    try withDescription(a, out, s.description);
    const xy = try buildXyang(a, "leaf-list", .{
        .musts = s.must_statements.items,
        .when = s.when,
        .if_features = s.if_features.items,
        .units = s.units,
        .config = s.config,
    });
    try out.put(a, K.X_YANG, objVal(xy));
    try stampExtensions(g, xy, s.statements.items, names, module);
    if (d.min_elements) |n| try out.put(a, K.MIN_ITEMS, .{ .int = n });
    if (d.max_elements) |n| try out.put(a, K.MAX_ITEMS, .{ .int = n });
    if (d.default_values) |vals| {
        if (vals.len > 0) try out.put(a, K.DEFAULT, .{ .array = try a.dupe(Val, vals) });
    } else if (d.defaults.items.len > 0) {
        try out.put(a, K.DEFAULT, try strList(a, d.defaults.items));
    }
    return objVal(out);
}

fn choiceToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module, parent: Schema) Error!Val {
    const a = g.a;
    const anchor: Schema = if (parent == .none) .{ .module = module } else parent;
    const body = try choiceToObjectBody(g, s, names, module, anchor);
    const xy = try newObject(a);
    try xy.put(a, K.xy.TYPE, str("choice"));
    try xy.put(a, K.xy.MANDATORY, .{ .bool = s.data.choice.mandatory });
    if (s.config) |c| try xy.put(a, K.xy.CONFIG, .{ .bool = c });
    if (s.if_features.items.len > 0) try xy.put(a, K.xy.IF_FEATURES, try strList(a, s.if_features.items));
    try stampExtensions(g, xy, s.statements.items, names, module);
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("object"));
    if (body.get(K.DESCRIPTION)) |dv| try withDescription(a, out, dv.string);
    try out.put(a, K.X_YANG, objVal(xy));
    if (getObject(body, K.PROPERTIES)) |p| if (p.count() > 0) try out.put(a, K.PROPERTIES, objVal(p));
    if (body.get(K.ONE_OF)) |o| try out.put(a, K.ONE_OF, o);
    return objVal(out);
}

/// `_io_block_to_property`: rpc / action `input` or `output`.
fn ioBlockToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const children = try expandForJson(g, s.statements.items, module);
    const map = try childPropertyMap(g, children, names, module, .{ .stmt = s });
    const out = try newObject(a);
    try out.put(a, K.TYPE, str("object"));
    try withDescription(a, out, s.description);
    const xy = try buildXyang(a, if (s.kind() == .input) K.types.INPUT else K.types.OUTPUT, .{
        .musts = s.must_statements.items,
        .when = s.when,
        .if_features = s.if_features.items,
    });
    try out.put(a, K.X_YANG, objVal(xy));
    try stampExtensions(g, xy, children, names, module);
    try out.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
    if (map.props.count() > 0) try out.put(a, K.PROPERTIES, objVal(map.props));
    if (map.required.items.len > 0) try out.put(a, K.REQUIRED, try strList(a, map.required.items));
    return objVal(out);
}

/// `_with_actions`: `x-yang.actions` of a container or list (RFC 7950 7.15).
fn withActions(g: *Gen, prop: Val, s: *Statement, names: *const Names, module: *Module) Error!Val {
    const a = g.a;
    const actions = try newObject(a);
    for (try expandForJson(g, s.statements.items, module)) |child| {
        if (child.kind() != .action or child.name.len == 0) continue;
        try actions.put(a, try propertyKey(a, child, module), try rpcToJson(g, child, names, module, K.types.ACTION));
    }
    if (actions.count() > 0) try getObject(prop.object, K.X_YANG).?.put(a, K.xy.ACTIONS, objVal(actions));
    return prop;
}

fn findChildNamed(s: *const Statement, name: []const u8) ?*Statement {
    for (s.statements.items) |c| if (std.mem.eql(u8, c.name, name)) return c;
    return null;
}

/// `_rpc_to_json`: one `x-yang.rpcs` entry, or one `x-yang.actions` entry.
fn rpcToJson(g: *Gen, s: *Statement, names: *const Names, module: *Module, kind: []const u8) Error!Val {
    const a = g.a;
    const xy = try buildXyang(a, kind, .{ .musts = s.must_statements.items, .when = s.when, .if_features = s.if_features.items });
    try stampExtensions(g, xy, s.statements.items, names, module);
    const out = try newObject(a);
    try out.put(a, K.X_YANG, objVal(xy));
    if (findChildNamed(s, "input")) |inp| if (inp.kind() == .input) try out.put(a, "input", try ioBlockToProperty(g, inp, names, module));
    if (findChildNamed(s, "output")) |outp| if (outp.kind() == .output) try out.put(a, "output", try ioBlockToProperty(g, outp, names, module));
    return objVal(out);
}

/// `_statement_to_property`: one schema node, or null for a statement that is not one.
fn statementToProperty(g: *Gen, s: *Statement, names: *const Names, module: *Module, parent: Schema) Error!?Val {
    const property: ?Val = switch (s.kind()) {
        .container, .notification, .input, .output => try withActions(g, try containerToProperty(g, s, names, module), s, names, module),
        .list => try withActions(g, try listToProperty(g, s, names, module), s, names, module),
        .leaf => try leafToProperty(g, s, names, module, parent),
        .anydata, .anyxml => try anyToProperty(g, s, names, module),
        .leaf_list => try leafListToProperty(g, s, names, module, parent),
        .choice => try choiceToProperty(g, s, names, module, parent),
        else => null,
    };
    if (property) |prop| if (s.augment_structure) |path| {
        if (getObject(prop.object, K.X_YANG)) |xy| try xy.put(g.a, K.xy.AUGMENT_STRUCTURE, str(path));
    };
    return property;
}

/// `_typedef_to_def`: a typedef's `$defs` entry (no `$ref` inside).
fn typedefToDef(g: *Gen, td: *Statement, module: *Module) Error!Val {
    const a = g.a;
    const d = td.data.typedef;
    const none: Names = .empty;
    const schema = try typeToSchema(g, d.type, &none, module, .none);
    _ = schema.orderedRemove(K.DESCRIPTION);
    try withDescription(a, schema, td.description);
    try mergeUnits(a, schema, td.units);
    const default: ?Val = d.default_value orelse if (d.default) |s| str(s) else null;
    if (default) |dv| {
        const yang_type = if (d.type) |t| t.name else null;
        try schema.put(a, K.DEFAULT, jsonSchemaDefaultValue(dv, yang_type, schemaTypeName(schema)));
    }
    if (d.scope) |scope| {
        const xy = getObject(schema, K.X_YANG) orelse blk: {
            const value = try newObject(a);
            try schema.put(a, K.X_YANG, objVal(value));
            break :blk value;
        };
        try xy.put(a, K.xy.SCOPE, str(scope));
        try xy.put(a, K.NAME, str(td.name));
    }
    const names = try typedefNameSet(a, module);
    if (try extensionInvocationsJson(g, td.statements.items, &names, module)) |inv| {
        const xy = getObject(schema, K.X_YANG) orelse blk: {
            const o = try newObject(a);
            try schema.put(a, K.X_YANG, objVal(o));
            break :blk o;
        };
        try xy.put(a, K.xy.EXTENSIONS, inv);
    }
    return objVal(schema);
}

/// `_apply_own_augments`: merge the module's augments into its own expanded tree. An
/// augment of another module's tree has no place in this module's JSON.
fn applyOwnAugments(g: *Gen, schema_module: *Module) Error!void {
    for (schema_module.statements.items) |s| {
        if (s.kind() != .augment) continue;
        const d = s.data.augment;
        const first_prefix: []const u8 = if (d.augment_path_segments.items.len > 0)
            d.augment_path_segments.items[0].prefix orelse ""
        else
            firstPathPrefix(d.augment_path);
        if (schema_module.resolvePrefixedModule(first_prefix) != schema_module) {
            return g.fail("cannot export augment {f}: its target belongs to another module, which the native JSON form of module {f} does not carry", .{ repr(d.augment_path), repr(schema_module.name) });
        }
    }
    try augment_expand.applyAugmentations(&g.reporter, schema_module);
}

fn firstPathPrefix(path: []const u8) []const u8 {
    const raw = std.mem.trimStart(u8, std.mem.trim(u8, path, &std.ascii.whitespace), "/");
    const end = std.mem.indexOfScalar(u8, raw, '/') orelse raw.len;
    const seg = raw[0..end];
    const colon = std.mem.indexOfScalar(u8, seg, ':') orelse return "";
    return seg[0..colon];
}

/// Preserve foreign augment positions even after callbacks removed them from the tree.
fn orderedExtensionInvocations(g: *Gen, module: *Module, names: *const Names) Error!?Val {
    var out: std.ArrayList(Val) = .empty;
    var slot: usize = 0;
    for (module.statements.items) |node| {
        if (node.kind() != .extension_invocation) continue;
        for (module.foreign_structure_augments.items, module.foreign_structure_slots.items) |inv, at| {
            if (at == slot) try out.append(g.a, try oneExtensionInvocation(g, inv, names, module));
        }
        try out.append(g.a, try oneExtensionInvocation(g, node, names, module));
        slot += 1;
    }
    for (module.foreign_structure_augments.items, module.foreign_structure_slots.items) |inv, at| {
        if (at >= slot) try out.append(g.a, try oneExtensionInvocation(g, inv, names, module));
    }
    return if (out.items.len == 0) null else .{ .array = out.items };
}

fn featuresJson(a: Allocator, module: *Module) Error!*Object {
    const out = try newObject(a);
    for (try sortedStrings(a, module.features.keys())) |name| {
        const body = try newObject(a);
        if (module.feature_if_features.get(name)) |guards| {
            if (guards.items.len > 0) try body.put(a, K.xy.IF_FEATURES, try strList(a, guards.items));
        }
        try out.put(a, name, objVal(body));
    }
    return out;
}

/// Strip this exporter's additions recursively, since its foreign invocation is
/// applied separately on reload. Work only on detached copies.
fn stripAugmentedBy(g: *Gen, node: *Statement, exporter: []const u8) Error!?*Statement {
    if (node.augment_structure_module) |owner| if (std.mem.eql(u8, owner, exporter)) return null;
    const copy = try copyStatement(g, node);
    copy.statements = .empty;
    for (node.statements.items) |child| {
        if (try stripAugmentedBy(g, child, exporter)) |kept| try copy.statements.append(g.a, kept);
    }
    if (node.kind() == .choice) {
        copy.data.choice.cases = .empty;
        for (node.data.choice.cases.items) |case| {
            if (try stripAugmentedBy(g, case, exporter)) |kept| try copy.data.choice.cases.append(g.a, kept);
        }
    }
    return copy;
}

fn extensionStub(g: *Gen, module: *Module) Error!*Object {
    const stub = try newObject(g.a);
    try stub.put(g.a, K.xy.MODULE, str(module.name));
    try stub.put(g.a, K.xy.NAMESPACE, str(module.namespace));
    try stub.put(g.a, K.xy.PREFIX, str(module.prefix));
    const defs = try newObject(g.a);
    for (module.extensions.keys(), module.extensions.values()) |name, ext| {
        try defs.put(g.a, name, try extensionDefJson(g.a, ext));
    }
    try stub.put(g.a, K.xy.EXTENSION, objVal(defs));
    return stub;
}

fn addImportedStructures(g: *Gen, root: *Module, imports: *Object) Error!void {
    var invocations: std.ArrayList(*Statement) = .empty;
    for (root.statements.items) |node| if (capabilities.isRfc8791(node, "augment-structure")) {
        try invocations.append(g.a, node);
    };
    try invocations.appendSlice(g.a, root.foreign_structure_augments.items);
    var seen: std.AutoArrayHashMapUnmanaged(*Module, void) = .empty;
    for (invocations.items) |inv| {
        const owner = capabilities.augmentOwner(root, inv.data.extension_invocation.argument orelse "") orelse continue;
        if (owner == root or std.mem.eql(u8, owner.name, root.name) or seen.contains(owner)) continue;
        try seen.put(g.a, owner, {});
        const key = try importKey(g, root, owner);
        const stub = getObject(imports, key) orelse blk: {
            const item = try newObject(g.a);
            try item.put(g.a, K.xy.MODULE, str(owner.name));
            try item.put(g.a, K.xy.NAMESPACE, str(owner.namespace));
            try item.put(g.a, K.xy.PREFIX, str(owner.prefix));
            try imports.put(g.a, key, objVal(item));
            break :blk item;
        };
        const view = try owner.cowCopy(g.a);
        view.statements = try refine_expand.copyStatements(&g.reporter, owner.statements.items);
        try capabilities.applyForExport(&g.reporter, view);
        var structures = try view.statements.clone(g.a);
        for (view.structures.values()) |structure| {
            if (std.mem.indexOfScalar(*Statement, structures.items, structure) == null) try structures.append(g.a, structure);
        }
        var bodies: std.ArrayList(Val) = .empty;
        const none: Names = .empty;
        for (structures.items) |structure| {
            if (!capabilities.isRfc8791(structure, "structure")) continue;
            const shadow = (try stripAugmentedBy(g, structure, root.name)).?;
            try bodies.append(g.a, try oneExtensionInvocation(g, shadow, &none, root));
            const defining = view.resolvePrefixedModule(structure.data.extension_invocation.prefix) orelse
                return g.fail("cannot export imported structure: extension module is not loaded", .{});
            const nested = getObject(stub, K.xy.IMPORTS) orelse blk: {
                const item = try newObject(g.a);
                try stub.put(g.a, K.xy.IMPORTS, objVal(item));
                break :blk item;
            };
            const prefix = structure.data.extension_invocation.prefix;
            if (!nested.contains(prefix)) try nested.put(g.a, prefix, objVal(try extensionStub(g, defining)));
        }
        // Python writes extensions before the nested import map.
        const nested = stub.fetchOrderedRemove(K.xy.IMPORTS);
        if (bodies.items.len > 0) try stub.put(g.a, K.xy.EXTENSIONS, .{ .array = bodies.items });
        if (nested) |entry| try stub.put(g.a, K.xy.IMPORTS, entry.value);
    }
    const sorted = try sortedObject(g.a, imports);
    imports.* = sorted.*;
}

/// `generate_json_schema`: the module's native JSON form. On `error.Export` or
/// `error.YangLoad`, `diag` holds the message.
pub fn generate(a: Allocator, module: *Module, diag: *errors.Diagnostic) Error!Val {
    var g: Gen = .{ .a = a, .root = module, .reporter = .{ .arena = a, .diag = diag } };
    var visited: std.AutoHashMapUnmanaged(*Module, void) = .empty;
    try collectScopedTypedefs(&g, module, &visited);
    const names = try typedefNameSet(a, module);
    const root_xy = try newObject(a);
    try root_xy.put(a, K.xy.MODULE, str(if (module.name.len > 0) module.name else "unknown"));
    try root_xy.put(a, K.xy.YANG_VERSION, str(module.yang_version));
    try root_xy.put(a, K.xy.NAMESPACE, str(module.namespace));
    try root_xy.put(a, K.xy.PREFIX, str(module.prefix));
    try root_xy.put(a, K.xy.ORGANIZATION, str(module.organization));
    try root_xy.put(a, K.xy.CONTACT, str(module.contact));

    // A uses-expanded view resolves leafrefs; the typedefs map stays the module's, as
    // Python's shallow `copy(module)` shares it.
    const schema_module = try module.cowCopy(a);
    var expanded = try expandForJson(&g, module.statements.items, schema_module);
    schema_module.statements = .empty;
    try schema_module.statements.appendSlice(a, expanded);
    try applyOwnAugments(&g, schema_module);
    try capabilities.applyForExport(&g.reporter, schema_module);
    expanded = schema_module.statements.items;

    const properties = try newObject(a);
    for (expanded) |s| {
        if (s.name.len == 0) continue;
        const prop = try statementToProperty(&g, s, &names, schema_module, .{ .module = schema_module }) orelse continue;
        try properties.put(a, try propertyKey(a, s, module), prop);
    }

    const defs = try newObject(a);
    for (schema_module.typedefs.keys(), schema_module.typedefs.values()) |n, td| {
        if (td.kind() == .typedef) try defs.put(a, n, try typedefToDef(&g, td, schema_module));
    }
    for (g.scoped_typedefs.keys(), g.scoped_typedefs.values()) |key, entry| {
        try defs.put(a, key, try typedefToDef(&g, entry.typedef, entry.module));
    }
    for (schema_module.identities.keys(), schema_module.identities.values()) |n, id| {
        if (id.kind() == .identity) try defs.put(a, n, try identityToDef(&g, n, id, schema_module, null));
    }

    const rpcs = try newObject(a);
    for (expanded) |s| {
        if (s.kind() == .rpc and s.name.len > 0) try rpcs.put(a, s.name, try rpcToJson(&g, s, &names, schema_module, K.types.RPC));
    }
    if (rpcs.count() > 0) try root_xy.put(a, K.xy.RPCS, objVal(rpcs));
    const module_invocations = try orderedExtensionInvocations(&g, schema_module, &names);
    const imports = try mergeExtensionImports(&g, module, try importsForJson(&g, module));
    try addImportedStructures(&g, schema_module, imports);
    if (imports.count() > 0) try root_xy.put(a, K.xy.IMPORTS, objVal(imports));
    const ext_defs = try newObject(a);
    for (module.extensions.keys(), module.extensions.values()) |n, ext| {
        if (ext.kind() == .extension) try ext_defs.put(a, n, try extensionDefJson(a, ext));
    }
    if (ext_defs.count() > 0) try root_xy.put(a, K.xy.EXTENSION, objVal(ext_defs));
    const features = try featuresJson(a, module);
    if (features.count() > 0) try root_xy.put(a, K.xy.FEATURES, objVal(features));
    if (module_invocations) |inv| try root_xy.put(a, K.xy.EXTENSIONS, inv);
    try assertExtensionsPlaced(&g, schema_module);
    // Typedefs registered while expanding grouping bodies belong to the module (Python
    // shares the dict between the module and its copy).
    module.typedefs = schema_module.typedefs;

    const root = try newObject(a);
    try root.put(a, K.SCHEMA, str("https://json-schema.org/draft/2020-12/schema"));
    try root.put(a, K.ID, str(if (module.namespace.len > 0) module.namespace else try std.fmt.allocPrint(a, "urn:{s}", .{if (module.name.len > 0) module.name else "unknown"})));
    try withDescription(a, root, module.description);
    try root.put(a, K.X_YANG, objVal(root_xy));
    try root.put(a, K.TYPE, str("object"));
    try root.put(a, K.PROPERTIES, objVal(properties));
    try root.put(a, K.ADDITIONAL_PROPERTIES, .{ .bool = false });
    if (defs.count() > 0) try root.put(a, K.DEFS, objVal(defs));
    return objVal(root);
}

/// `schema_to_yang_json`: `json.dumps(generate_json_schema(module), indent=2,
/// ensure_ascii=False) + "\n"`.
pub fn schemaToYangJson(a: Allocator, module: *Module, diag: *errors.Diagnostic) Error![]const u8 {
    const v = try generate(a, module, diag);
    var out: std.Io.Writer.Allocating = .init(a);
    jv.dumpIndented(&out.writer, v, 2) catch return error.OutOfMemory;
    out.writer.writeByte('\n') catch return error.OutOfMemory;
    return out.written();
}

fn convertForTest(a: Allocator, source: []const u8, diag: *errors.Diagnostic) ![]const u8 {
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, null, diag, &.{});
    loader.expand_uses = false;
    const m = try loader.parseString(source, "t.yang", null, true);
    return schemaToYangJson(a, m, diag);
}

test "the native JSON form is Python's text" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var diag: errors.Diagnostic = .{};
    const text = try convertForTest(arena.allocator(),
        \\module t { yang-version 1.1; namespace "urn:t"; prefix t;
        \\  identity base;
        \\  extension note { argument text; }
        \\  container c { t:note "hi"; leaf x { type int64; default "-3"; } leaf k { type identityref { base base; } } }
        \\}
    , &diag);
    try std.testing.expectEqualStrings(
        \\{
        \\  "$schema": "https://json-schema.org/draft/2020-12/schema",
        \\  "$id": "urn:t",
        \\  "x-yang": {
        \\    "module": "t",
        \\    "yang-version": "1.1",
        \\    "namespace": "urn:t",
        \\    "prefix": "t",
        \\    "organization": "",
        \\    "contact": "",
        \\    "extension": {
        \\      "note": {
        \\        "argument": "text"
        \\      }
        \\    }
        \\  },
        \\  "type": "object",
        \\  "properties": {
        \\    "c": {
        \\      "type": "object",
        \\      "x-yang": {
        \\        "type": "container",
        \\        "extensions": [
        \\          {
        \\            "name": "t:note",
        \\            "argument": "hi"
        \\          }
        \\        ]
        \\      },
        \\      "properties": {
        \\        "x": {
        \\          "type": "string",
        \\          "pattern": "^-?[0-9]+$",
        \\          "x-yang": {
        \\            "type": "int64"
        \\          },
        \\          "default": -3
        \\        },
        \\        "k": {
        \\          "$ref": "#/$defs/base",
        \\          "x-yang": {
        \\            "type": "identityref",
        \\            "bases": [
        \\              "base"
        \\            ]
        \\          }
        \\        }
        \\      },
        \\      "additionalProperties": false
        \\    }
        \\  },
        \\  "additionalProperties": false,
        \\  "$defs": {
        \\    "base": {
        \\      "type": "string",
        \\      "enum": [
        \\        "t:base"
        \\      ],
        \\      "x-yang": {
        \\        "type": "identity",
        \\        "bases": []
        \\      }
        \\    }
        \\  }
        \\}
        \\
    , text);
}

test "statements Python cannot copy fail the conversion" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    try std.testing.expectError(error.YangLoad, convertForTest(a, "module t { prefix t; notification n { leaf a { type string; } } }", &diag));
    try std.testing.expectEqualStrings("Unsupported statement type for copy: YangNotificationStmt", diag.message);
    try std.testing.expectError(error.YangLoad, convertForTest(a, "module t { prefix t; leaf a { type string; } deviation \"/t:a\" { deviate not-supported; } }", &diag));
    try std.testing.expectEqualStrings("Unsupported statement type for copy: YangDeviationStmt", diag.message);
}

fn structureFixture(a: Allocator, diag: *errors.Diagnostic, name: []const u8, expand: bool) !*Module {
    const dir = try std.fmt.allocPrint(a, "../tests/cases/modules/{s}", .{name});
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, std.testing.io, diag, &.{dir});
    loader.expand_uses = expand;
    return loader.parseFile(try std.fs.path.join(a, &.{ dir, "m.yang" }));
}

test "RFC 8791 own augment export leaves the source tree untouched (#164)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    const module = try structureFixture(a, &diag, "json-form-augment-structure-164", false);
    const structure = module.statements.items[0];
    const augment = module.statements.items[1];
    const before = try schemaToYangJson(a, module, &diag);
    try std.testing.expectEqual(@as(usize, 3), structure.statements.items.len);
    try std.testing.expectEqual(@as(usize, 0), module.structures.count());
    try std.testing.expect(!augment.rfc8791_applied);
    try std.testing.expect(!augment.when.?.evaluate_with_parent_context);
    try std.testing.expectEqualStrings(before, try schemaToYangJson(a, module, &diag));
}

test "RFC 8791 foreign augment export leaves the imported tree untouched (#164)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    const module = try structureFixture(a, &diag, "json-form-augment-structure-cross-164", false);
    const imported = module.import_prefixes.get("b").?;
    const box = imported.statements.items[0].statements.items[0];
    const before = try schemaToYangJson(a, module, &diag);
    try std.testing.expectEqual(@as(usize, 1), box.statements.items.len);
    try std.testing.expectEqual(@as(usize, 0), imported.structures.count());
    try std.testing.expectEqualStrings(before, try schemaToYangJson(a, module, &diag));
}

test "RFC 8791 export after application and reload applies foreign augment once (#164)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    const module = try structureFixture(a, &diag, "json-form-augment-structure-cross-164", true);
    const form = try generate(a, module, &diag);
    const unapplied = try structureFixture(a, &diag, "json-form-augment-structure-cross-164", false);
    try std.testing.expect(jv.pyEql(form, try generate(a, unapplied, &diag)));
    var message: []const u8 = "";
    const loaded = try @import("parser.zig").parseJsonSchema(a, form, &message);
    const structure = loaded.import_prefixes.get("b").?.structures.get("msg").?;
    const box = structure.statements.items[0];
    try std.testing.expectEqual(@as(usize, 2), box.statements.items.len);
    var reporter: errors.Reporter = .{ .arena = a, .diag = &diag };
    try capabilities.applyExtensionInvocations(&reporter, loaded);
    try std.testing.expectEqual(@as(usize, 2), box.statements.items.len);
    try std.testing.expect(jv.pyEql(form, try generate(a, loaded, &diag)));
}
