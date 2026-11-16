//! JSON-LD context and vocabulary projections of the canonical native schema.
const std = @import("std");
const jv = @import("../json_value.zig");
const gen = @import("generator.zig");
const errors = @import("../errors.zig");
const Module = @import("../module.zig").Module;
const Val = jv.Val;
const Object = jv.Object;
const Allocator = std.mem.Allocator;
const Prefix = struct { name: []const u8, iri: []const u8 };
const prefixes = [_]Prefix{
    .{ .name = "schema", .iri = "https://schema.org/" },
    .{ .name = "rdf", .iri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#" },
    .{ .name = "rdfs", .iri = "http://www.w3.org/2000/01/rdf-schema#" },
    .{ .name = "skos", .iri = "http://www.w3.org/2004/02/skos/core#" },
    .{ .name = "wd", .iri = "http://www.wikidata.org/entity/" },
};
fn text(v: Val) []const u8 {
    return if (v == .string) v.string else "";
}
fn get(o: *const Object, key: []const u8) Val {
    return o.get(key) orelse .null;
}
fn field(o: *const Object, key: []const u8) []const u8 {
    return text(get(o, key));
}
fn eq(a: []const u8, b: []const u8) bool {
    return std.mem.eql(u8, a, b);
}
fn object(a: Allocator) !*Object {
    const o = try a.create(Object);
    o.* = .empty;
    return o;
}
fn metadata(o: *const Object) ?*Object {
    const v = get(o, "x-yang");
    return if (v == .object) v.object else null;
}
const Property = struct { key: []const u8, schema: *Object };
const Builder = struct {
    a: Allocator,
    schema: *Object,
    diag: *errors.Diagnostic,
    module: []const u8,
    base: []const u8,
    namespaces: std.array_hash_map.String([]const u8) = .empty,
    owners: std.array_hash_map.String([]const u8) = .empty,
    graph: std.array_hash_map.String(*Object) = .empty,
    fn fail(b: *Builder, comptime fmt: []const u8, args: anytype) gen.Error {
        b.diag.* = .{ .kind = .semantic, .message = try b.a.print(fmt, args) };
        return error.Export;
    }
    fn namespace(b: *Builder, ns: []const u8) ![]const u8 {
        return if (ns.len > 0 and std.mem.findScalar(u8, "#/:", ns[ns.len - 1]) != null) ns else try b.a.print("{s}#", .{ns});
    }
    fn iri(b: *Builder, raw: []const u8) gen.Error![]const u8 {
        var value = raw;
        if (std.mem.findScalar(u8, value, ':')) |colon| {
            for (prefixes) |p| if (eq(p.name, value[0..colon])) {
                value = try b.a.print("{s}{s}", .{ p.iri, value[colon + 1 ..] });
                break;
            };
        }
        const colon = std.mem.findScalar(u8, value, ':') orelse return b.fail("JSON-LD mapping must be an absolute IRI: {s}", .{raw});
        if (colon == 0 or colon + 1 == value.len or !std.ascii.isAlphabetic(value[0])) return b.fail("JSON-LD mapping must be an absolute IRI: {s}", .{raw});
        for (value[1..colon]) |c| if (!std.ascii.isAlphanumeric(c) and std.mem.findScalar(u8, "+.-", c) == null) return b.fail("JSON-LD mapping must be an absolute IRI: {s}", .{raw});
        for (value[colon + 1 ..]) |c| if (std.ascii.isWhitespace(c)) return b.fail("JSON-LD mapping must be an absolute IRI: {s}", .{raw});
        return value;
    }
    fn mappings(b: *Builder, node: *Object) gen.Error!*Object {
        const out = try object(b.a);
        const xy = metadata(node) orelse return out;
        const invocations = get(xy, "extensions");
        if (invocations != .array) return out;
        for (invocations.array) |inv| {
            if (inv != .object) continue;
            const label = field(inv.object, "name");
            const colon = std.mem.findScalar(u8, label, ':') orelse continue;
            const name = label[colon + 1 ..];
            const owner = b.owners.get(label[0..colon]) orelse "";
            const key = if (eq(owner, "xyang-jsonld")) name else if (eq(name, "schema-org-property")) "iri" else if (eq(name, "schema-org-class")) "class" else if (eq(name, "wikidata")) "close-match" else if (eq(name, "unit-code")) "unit-code" else continue;
            if (!eq(key, "iri") and !eq(key, "iri-value") and !eq(key, "class") and !eq(key, "close-match") and !eq(key, "unit-code")) continue;
            var arg = field(inv.object, "argument");
            if (!eq(key, "iri-value") and arg.len == 0) return b.fail("JSON-LD {s} mapping requires a non-empty argument", .{key});
            var value: Val = undefined;
            if (eq(key, "iri-value")) value = .{ .bool = true } else if (eq(key, "unit-code")) value = gen.str(arg) else {
                if ((eq(name, "schema-org-property") or eq(name, "schema-org-class")) and std.mem.findScalar(u8, arg, ':') == null) arg = try b.a.print("https://schema.org/{s}", .{arg});
                if (eq(name, "wikidata") and arg.len > 1 and arg[0] == 'Q') {
                    const digits = for (arg[1..]) |c| {
                        if (!std.ascii.isDigit(c)) break false;
                    } else true;
                    if (digits) arg = try b.a.print("http://www.wikidata.org/entity/{s}", .{arg});
                }
                value = gen.str(if (eq(key, "iri") and (eq(arg, "@id") or eq(arg, "@type"))) arg else try b.iri(arg));
            }
            if (eq(key, "close-match")) {
                var list: std.ArrayList(Val) = .empty;
                const old = get(out, key);
                if (old == .array) try list.appendSlice(b.a, old.array);
                try list.append(b.a, value);
                try out.put(b.a, key, .{ .array = try list.toOwnedSlice(b.a) });
            } else if (out.get(key)) |old| {
                if (!jv.pyEql(old, value)) return b.fail("Conflicting JSON-LD {s} mappings", .{key});
            } else try out.put(b.a, key, value);
            if (eq(name, "schema-org-property") and eq(arg, "https://schema.org/url")) try out.put(b.a, "iri-value", .{ .bool = true });
        }
        return out;
    }
    fn resolve(b: *Builder, node: *Object, depth: usize) gen.Error!*Object {
        const ref = field(node, "$ref");
        if (ref.len == 0) return node;
        if (!std.mem.startsWith(u8, ref, "#/$defs/") or depth > 128) return b.fail("Unsupported or recursive JSON-LD schema reference: {s}", .{ref});
        var key: std.ArrayList(u8) = .empty;
        var i: usize = "#/$defs/".len;
        while (i < ref.len) : (i += 1) {
            if (ref[i] == '~' and i + 1 < ref.len and (ref[i + 1] == '0' or ref[i + 1] == '1')) {
                i += 1;
                try key.append(b.a, if (ref[i] == '1') '/' else '~');
            } else try key.append(b.a, ref[i]);
        }
        const defs = get(b.schema, "$defs");
        const target = if (defs == .object) get(defs.object, key.items) else Val.null;
        if (target != .object) return b.fail("Unresolved JSON-LD schema reference: {s}", .{ref});
        const merged = try gen.cloneObject(b.a, try b.resolve(target.object, depth + 1));
        for (node.keys(), node.values()) |k, v| if (!eq(k, "$ref")) try merged.put(b.a, k, v);
        return merged;
    }
    fn properties(b: *Builder, raw: *Object, out: *std.ArrayList(Property), depth: usize) gen.Error!void {
        if (depth > 128) return b.fail("JSON-LD context nesting exceeds 128 levels", .{});
        const shape = try b.resolve(raw, 0);
        const props = get(shape, "properties");
        if (props == .object) for (props.object.keys(), props.object.values()) |k, v| {
            if (v == .object) try out.append(b.a, .{ .key = k, .schema = v.object });
        };
        for ([_][]const u8{ "oneOf", "anyOf", "allOf" }) |key| {
            const branches = get(shape, key);
            if (branches == .array) for (branches.array) |branch| {
                if (branch == .object) try b.properties(branch.object, out, depth + 1);
            };
        }
    }
    fn link(b: *Builder, iri_value: Val) !Val {
        const o = try object(b.a);
        try o.put(b.a, "@id", iri_value);
        return gen.objVal(o);
    }
    fn record(b: *Builder, iri_value: []const u8, name: []const u8, node: *Object, mapping: *Object) gen.Error!void {
        if (std.mem.startsWith(u8, iri_value, "@")) return;
        const rec = b.graph.get(iri_value) orelse blk: {
            const o = try object(b.a);
            try o.put(b.a, "@id", gen.str(iri_value));
            try o.put(b.a, "@type", gen.str("rdf:Property"));
            try o.put(b.a, "rdfs:label", gen.str(name));
            try b.graph.put(b.a, iri_value, o);
            break :blk o;
        };
        const values = try object(b.a);
        try values.put(b.a, "rdfs:label", gen.str(name));
        const desc = field(node, "description");
        if (desc.len > 0) try values.put(b.a, "rdfs:comment", gen.str(desc));
        const xy = metadata(node);
        const units = if (field(mapping, "unit-code").len > 0) field(mapping, "unit-code") else if (xy) |m| field(m, "units") else "";
        if (units.len > 0) try values.put(b.a, "schema:unitCode", gen.str(units));
        const class = field(mapping, "class");
        if (class.len > 0) try values.put(b.a, "rdfs:range", try b.link(gen.str(class)));
        const matches = get(mapping, "close-match");
        if (matches == .array) {
            const links = try b.a.alloc(Val, matches.array.len);
            for (matches.array, 0..) |v, i| links[i] = try b.link(v);
            try values.put(b.a, "skos:closeMatch", .{ .array = links });
        }
        for (values.keys(), values.values()) |k, v| {
            if (rec.get(k)) |old| {
                if (jv.pyEql(old, v)) continue;
                var merged: std.ArrayList(Val) = .empty;
                if (old == .array) try merged.appendSlice(b.a, old.array) else try merged.append(b.a, old);
                const next = if (v == .array) v.array else &[_]Val{v};
                for (next) |item| {
                    const exists = for (merged.items) |prev| {
                        if (jv.pyEql(prev, item)) break true;
                    } else false;
                    if (!exists) try merged.append(b.a, item);
                }
                try rec.put(b.a, k, .{ .array = try merged.toOwnedSlice(b.a) });
            } else try rec.put(b.a, k, v);
        }
    }
    fn terms(b: *Builder, shape: *Object, parent_module: []const u8, depth: usize) gen.Error!*Object {
        if (depth > 128) return b.fail("JSON-LD context nesting exceeds 128 levels", .{});
        const context = try object(b.a);
        var props: std.ArrayList(Property) = .empty;
        try b.properties(shape, &props, 0);
        for (props.items) |prop| {
            const node = try b.resolve(prop.schema, 0);
            const colon = std.mem.findScalar(u8, prop.key, ':');
            const owner = if (colon) |i| prop.key[0..i] else parent_module;
            const local = if (colon) |i| prop.key[i + 1 ..] else prop.key;
            const ns = b.namespaces.get(owner) orelse return b.fail("JSON-LD namespace is missing for module {s}", .{owner});
            const mapping = try b.mappings(node);
            const default_iri = try b.a.print("{s}{s}", .{ ns, local });
            const mapped = field(mapping, "iri");
            const iri_value = if (mapped.len > 0) mapped else default_iri;
            const term = try object(b.a);
            try term.put(b.a, "@id", gen.str(iri_value));
            const iri_type = get(mapping, "iri-value");
            if (iri_type == .bool and iri_type.bool and std.mem.startsWith(u8, iri_value, "@")) return b.fail("JSON-LD keyword aliases cannot have value coercion", .{});
            if (iri_type == .bool and iri_type.bool) try term.put(b.a, "@type", gen.str("@id"));
            const xy = metadata(node);
            const kind = if (xy) |m| field(m, "type") else "";
            if (eq(kind, "container") or eq(kind, "list")) {
                const items = get(node, "items");
                const child = if (eq(kind, "list") and items == .object) items.object else node;
                try term.put(b.a, "@context", gen.objVal(try b.terms(child, owner, depth + 1)));
                if (std.mem.startsWith(u8, iri_value, "@")) return b.fail("JSON-LD keyword aliases cannot have child contexts", .{});
            }
            if (colon != null and !eq(iri_value, default_iri)) return b.fail("JSON-LD cannot remap compact-IRI member {s}; use unqualified members", .{prop.key});
            if (context.get(prop.key)) |old| if (!jv.pyEql(old, gen.objVal(term))) return b.fail("Conflicting JSON-LD term {s} across choice branches", .{prop.key});
            try context.put(b.a, prop.key, gen.objVal(term));
            try b.record(iri_value, local, node, mapping);
        }
        return context;
    }
};
pub const Documents = struct { context: Val, vocab: Val };
pub fn generate(a: Allocator, module: *Module, diag: *errors.Diagnostic) gen.Error!Documents {
    const schema = (try gen.generate(a, module, diag)).object;
    const xy = metadata(schema).?;
    const name = field(xy, "module");
    const ns = field(xy, "namespace");
    var b: Builder = .{ .a = a, .schema = schema, .diag = diag, .module = name, .base = "" };
    b.base = try b.namespace(if (ns.len > 0) ns else try a.print("urn:{s}", .{name}));
    try b.namespaces.put(a, name, b.base);
    try b.owners.put(a, field(xy, "prefix"), name);
    const imports = get(xy, "imports");
    if (imports == .object) for (imports.object.keys(), imports.object.values()) |prefix, stub| {
        if (stub != .object) continue;
        const imported = field(stub.object, "module");
        const imported_ns = field(stub.object, "namespace");
        try b.namespaces.put(a, imported, try b.namespace(if (imported_ns.len > 0) imported_ns else try a.print("urn:{s}", .{imported})));
        try b.owners.put(a, prefix, imported);
    };
    const terms = try b.terms(schema, name, 0);
    const context = try object(a);
    try context.put(a, "@version", .{ .float = 1.1 });
    try context.put(a, "@vocab", gen.str(b.base));
    for (b.namespaces.keys(), b.namespaces.values()) |owner, iri_value| if (!terms.contains(owner)) {
        const p = try object(a);
        try p.put(a, "@id", gen.str(iri_value));
        try p.put(a, "@prefix", .{ .bool = true });
        try context.put(a, owner, gen.objVal(p));
    };
    for (terms.keys(), terms.values()) |k, v| try context.put(a, k, v);
    const wrapped = try object(a);
    try wrapped.put(a, "@context", gen.objVal(context));
    const vocab_context = try object(a);
    try vocab_context.put(a, "@version", .{ .float = 1.1 });
    for (prefixes) |p| try vocab_context.put(a, p.name, gen.str(p.iri));
    const graph = try a.alloc(Val, b.graph.count());
    for (b.graph.values(), 0..) |v, i| graph[i] = gen.objVal(v);
    std.mem.sort(Val, graph, {}, struct {
        fn less(_: void, x: Val, y: Val) bool {
            return std.mem.order(u8, field(x.object, "@id"), field(y.object, "@id")) == .lt;
        }
    }.less);
    const vocab = try object(a);
    try vocab.put(a, "@context", gen.objVal(vocab_context));
    try vocab.put(a, "@graph", .{ .array = graph });
    return .{ .context = gen.objVal(wrapped), .vocab = gen.objVal(vocab) };
}

test "JSON-LD uses scoped terms (#229)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, null, &diag, &.{});
    const m = try loader.parseString(
        \\module xyang-jsonld { namespace "urn:jl"; prefix jl;
        \\ extension iri { argument value; }
        \\ container seller { leaf name { type string; jl:iri "schema:name"; } }
        \\ container series { leaf name { type string; jl:iri "schema:model"; } }
        \\}
    , "m.yang", null, true);
    const docs = try generate(a, m, &diag);
    const ctx = get(docs.context.object, "@context").object;
    const seller = get(get(ctx, "seller").object, "@context").object;
    const series = get(get(ctx, "series").object, "@context").object;
    try std.testing.expectEqualStrings("https://schema.org/name", field(get(seller, "name").object, "@id"));
    try std.testing.expectEqualStrings("https://schema.org/model", field(get(series, "name").object, "@id"));
}

test "invalid JSON-LD IRI is an export error (#229)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: errors.Diagnostic = .{};
    var loader = @import("../parser/yang_parser.zig").Loader.init(a, null, &diag, &.{});
    const m = try loader.parseString(
        \\module xyang-jsonld { namespace "urn:jl"; prefix jl;
        \\ extension iri { argument value; } leaf name { type string; jl:iri "relative"; } }
    , "m.yang", null, true);
    try std.testing.expectError(error.Export, generate(a, m, &diag));
}
