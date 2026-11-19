//! Standalone schema projections and diagnostics for YANG data subtrees.
const std = @import("std");
const jv = @import("../json_value.zig");
const Module = @import("../module.zig").Module;
const Diagnostic = @import("../errors.zig").Diagnostic;
const feature = @import("../if_feature_eval.zig");
const xpath = @import("../xpath/parser.zig");
const xast = @import("../xpath/ast.zig");
const gen = @import("generator.zig");
const A = std.mem.Allocator;
const Val = jv.Val;
const Obj = jv.Object;
const equal = std.mem.eql;

pub const SchemaDiagnostic = struct { path: []const u8, constraint: []const u8, expression: []const u8, reason: []const u8 };
const external = "depends on data outside the selected subtree or cannot be proved local";

fn getObj(o: *const Obj, key: []const u8) ?*Obj {
    const v = o.get(key) orelse return null;
    return if (v == .object) v.object else null;
}
fn getString(o: *const Obj, key: []const u8) ?[]const u8 {
    const v = o.get(key) orelse return null;
    return if (v == .string) v.string else null;
}
fn clone(a: A, v: Val) error{OutOfMemory}!Val {
    return switch (v) {
        .object => |o| blk: {
            const result = try gen.newObject(a);
            for (o.keys(), o.values()) |k, item| try result.put(a, k, try clone(a, item));
            break :blk .{ .object = result };
        },
        .array => |items| blk: {
            const result = try a.alloc(Val, items.len);
            for (items, 0..) |item, i| result[i] = try clone(a, item);
            break :blk .{ .array = result };
        },
        else => v,
    };
}
fn local(name: []const u8) []const u8 {
    if (std.mem.lastIndexOfScalar(u8, name, ':')) |i| return name[i + 1 ..];
    return name;
}
fn gather(o: *Obj, name: []const u8, found: *?*Obj, count: *usize) void {
    if (getObj(o, "properties")) |properties| {
        for (properties.keys(), properties.values()) |key, val| {
            if (val != .object) continue;
            if (equal(u8, key, name) or (std.mem.indexOfScalar(u8, name, ':') == null and equal(u8, local(key), name))) {
                if (found.* == null or !jv.pyEql(.{ .object = found.*.? }, .{ .object = val.object })) {
                    found.* = val.object;
                    count.* += 1;
                }
            }
            if (getObj(val.object, "x-yang")) |meta| if (getString(meta, "type")) |kind| {
                if (equal(u8, kind, "choice")) gather(val.object, name, found, count);
            };
        }
    }
    if (getObj(o, "items")) |items| gather(items, name, found, count);
    for ([_][]const u8{ "oneOf", "anyOf", "allOf" }) |key| {
        const branches = o.get(key) orelse continue;
        if (branches != .array) continue;
        for (branches.array) |branch| if (branch == .object) {
            gather(branch.object, name, found, count);
        };
    }
}
fn lookup(root: *Obj, path: []const []const u8) ?*Obj {
    var node = root;
    for (path) |segment| {
        var found: ?*Obj = null;
        var count: usize = 0;
        gather(node, segment, &found, &count);
        if (count != 1) return null;
        node = found.?;
    }
    return node;
}
fn parseExpr(a: A, expression: []const u8) gen.Error!*xast.Expr {
    var parser = xpath.Parser.init(a, expression) catch return error.OutOfMemory;
    return parser.parse() catch |err| switch (err) {
        error.OutOfMemory => error.OutOfMemory,
        else => error.Export,
    };
}
fn inside(path: []const []const u8, scope: []const []const u8) bool {
    if (path.len < scope.len) return false;
    for (scope, 0..) |part, i| if (!equal(u8, part, path[i])) return false;
    return true;
}
fn expressionWithin(a: A, expr: *const xast.Expr, base: []const []const u8, context: []const []const u8, scope: []const []const u8, module: *Module, bindings: ?*Obj) gen.Error!bool {
    switch (expr.*) {
        .literal => return true,
        .binary => |b| {
            if (equal(u8, b.operator, "/") and b.left.* == .call and equal(u8, b.left.call.name, "current")) {
                return inside(context, scope) and try expressionWithin(a, b.right, context, context, scope, module, bindings);
            }
            return (try expressionWithin(a, b.left, base, context, scope, module, bindings)) and (try expressionWithin(a, b.right, base, context, scope, module, bindings));
        },
        .call => |call| {
            if (equal(u8, call.name, "deref")) return false;
            if (equal(u8, call.name, "current")) return inside(context, scope);
            for (call.args) |arg| if (!try expressionWithin(a, arg, base, context, scope, module, bindings)) return false;
            return true;
        },
        .path => |p| {
            var path: std.ArrayList([]const u8) = .empty;
            if (!p.is_absolute) try path.appendSlice(a, base);
            for (p.segments) |seg| {
                if (seg.prefix()) |prefix| {
                    const owner = if (bindings) |b| getString(b, prefix) else null;
                    if (!equal(u8, prefix, module.prefix) and (owner == null or !equal(u8, owner.?, module.name))) return false;
                }
                if (equal(u8, seg.step, "..")) {
                    if (path.items.len > 0) _ = path.pop();
                } else if (!equal(u8, seg.step, ".")) {
                    if (seg.isWildcard()) return false;
                    try path.append(a, seg.local());
                }
                if (seg.predicate) |predicate| if (!try expressionWithin(a, predicate, path.items, context, scope, module, bindings)) return false;
            }
            return inside(path.items, scope);
        },
    }
}
fn prefixesSupported(expr: *const xast.Expr, module: *Module, bindings: ?*Obj) bool {
    switch (expr.*) {
        .literal => return true,
        .binary => |b| return prefixesSupported(b.left, module, bindings) and prefixesSupported(b.right, module, bindings),
        .call => |call| {
            for (call.args) |arg| if (!prefixesSupported(arg, module, bindings)) return false;
            return true;
        },
        .path => |p| {
            for (p.segments) |seg| {
                if (seg.prefix()) |prefix| {
                    const owner = if (bindings) |b| getString(b, prefix) else null;
                    if (!equal(u8, prefix, module.prefix) and (owner == null or !equal(u8, owner.?, module.name))) return false;
                }
                if (seg.predicate) |predicate| if (!prefixesSupported(predicate, module, bindings)) return false;
            }
            return true;
        },
    }
}
fn targetPath(a: A, expression: []const u8, context: []const []const u8) gen.Error![]const []const u8 {
    const ast = try parseExpr(a, expression);
    if (ast.* != .path) return error.Export;
    var out: std.ArrayList([]const u8) = .empty;
    if (!ast.path.is_absolute) try out.appendSlice(a, context);
    for (ast.path.segments) |seg| {
        if (equal(u8, seg.step, "..")) {
            if (out.items.len == 0) return error.Export;
            _ = out.pop();
        } else if (!equal(u8, seg.step, ".")) {
            if (seg.isWildcard()) return error.Export;
            try out.append(a, seg.local());
        }
    }
    return out.items;
}
fn jsonPattern(a: A, pattern: []const u8) gen.Error![]const u8 {
    var out: std.ArrayList(u8) = .empty;
    try out.appendSlice(a, "^(?:");
    var escaped = false;
    var in_class = false;
    for (pattern) |char| {
        if (escaped) {
            if (std.mem.indexOfScalar(u8, "dDsSwWiIcCpP", char) != null) return error.Export;
            if (char == 'n' or char == 'r' or char == 't') {
                try out.append(a, '\\');
                try out.append(a, char);
            } else {
                if (char >= 128) return error.Export;
                const hex = "0123456789ABCDEF";
                try out.appendSlice(a, "\\u00");
                try out.append(a, hex[char >> 4]);
                try out.append(a, hex[char & 15]);
            }
            escaped = false;
        } else if (char == '\\') {
            escaped = true;
        } else if (char == '[') {
            in_class = true;
            try out.append(a, char);
        } else if (char == ']' and in_class) {
            in_class = false;
            try out.append(a, char);
        } else if (!in_class and (char == '^' or char == '$')) {
            try out.append(a, '\\');
            try out.append(a, char);
        } else if (!in_class and char == '.') {
            try out.appendSlice(a, "[^\\r\\n]");
        } else try out.append(a, char);
    }
    if (escaped) return error.Export;
    try out.appendSlice(a, ")$");
    return out.items;
}
fn translatePatterns(a: A, value: Val) gen.Error!void {
    if (value == .array) {
        for (value.array) |item| try translatePatterns(a, item);
        return;
    }
    if (value != .object) return;
    const o = value.object;
    if (getObj(o, "x-yang")) |xy| if (xy.get("string-patterns")) |patterns| if (patterns == .array and patterns.array.len > 0) {
        var simple = false;
        if (patterns.array.len == 1 and patterns.array[0] == .object) {
            const item = patterns.array[0].object;
            const inverted = item.get("invert-match") orelse .null;
            if (inverted != .bool or !inverted.bool) if (getString(item, "pattern")) |pattern| {
                try o.put(a, "pattern", .{ .string = try jsonPattern(a, pattern) });
                simple = true;
            };
        }
        if (!simple) if (o.get("allOf")) |branches| if (branches == .array) {
            for (patterns.array, 0..) |pattern, i| {
                if (i >= branches.array.len or pattern != .object or branches.array[i] != .object) continue;
                const item = pattern.object;
                const inverted = item.get("invert-match") orelse .null;
                const branch = branches.array[i].object;
                const target = if (inverted == .bool and inverted.bool) getObj(branch, "not") orelse continue else branch;
                if (getString(item, "pattern")) |text| try target.put(a, "pattern", .{ .string = try jsonPattern(a, text) });
            }
        };
    };
    for (o.values()) |child| try translatePatterns(a, child);
}

fn containsVal(items: []const Val, value: Val) bool {
    for (items) |item| if (jv.pyEql(item, value)) return true;
    return false;
}

const Projector = struct {
    a: A,
    full: *Obj,
    available: *Obj,
    module: *Module,
    scope: []const []const u8,
    enabled: *const feature.EnabledFeatures,
    native_json: bool,
    diagnostics: std.ArrayList(SchemaDiagnostic) = .empty,

    fn active(self: *Projector, o: *Obj) gen.Error!bool {
        const meta = getObj(o, "x-yang") orelse return true;
        return self.guardsActive(meta);
    }
    fn guardsActive(self: *Projector, meta: *Obj) gen.Error!bool {
        const value = meta.get("if-features") orelse return true;
        if (value != .array) return true;
        var guards: std.ArrayList([]const u8) = .empty;
        const imported = try feature.reachableModules(self.a, self.module);
        for (value.array) |guard| if (guard == .string) {
            var tokens = std.mem.tokenizeAny(u8, guard.string, " ()\t\n\r");
            while (tokens.next()) |token| {
                if (equal(u8, token, "and") or equal(u8, token, "or") or equal(u8, token, "not") or std.mem.indexOfScalar(u8, token, ':') != null) continue;
                for (imported) |other| if (other != self.module and other.features.contains(token)) return error.Export;
            }
            try guards.append(self.a, guard.string);
        };
        return feature.ifFeaturesSatisfied(self.a, guards.items, self.module, self.enabled, null);
    }
    fn prune(self: *Projector, o: *Obj) gen.Error!bool {
        if (!try self.active(o)) return false;
        if (getObj(o, "x-yang")) |meta| if (getObj(meta, "choice")) |choice| {
            if (!try self.guardsActive(choice)) {
                const branches = o.get("oneOf") orelse .null;
                if (branches == .array and branches.array.len > 0 and branches.array[0] == .object) {
                    const first = branches.array[0].object;
                    const common = try gen.newObject(self.a);
                    if (getObj(first, "properties")) |props| {
                        for (props.keys(), props.values()) |key, value| {
                            var present = true;
                            for (branches.array[1..]) |branch| {
                                const other_props = if (branch == .object) getObj(branch.object, "properties") else null;
                                const other = if (other_props) |op| op.get(key) else null;
                                if (other == null or !jv.pyEql(value, other.?)) {
                                    present = false;
                                    break;
                                }
                            }
                            if (present) try common.put(self.a, key, value);
                        }
                    }
                    var required: std.ArrayList(Val) = .empty;
                    if (first.get("required")) |first_required| if (first_required == .array) {
                        for (first_required.array) |entry| {
                            var present = true;
                            for (branches.array[1..]) |branch| {
                                const other = if (branch == .object) branch.object.get("required") orelse .null else Val.null;
                                if (other != .array or !containsVal(other.array, entry)) {
                                    present = false;
                                    break;
                                }
                            }
                            if (present) try required.append(self.a, entry);
                        }
                    };
                    try o.put(self.a, "properties", .{ .object = common });
                    try o.put(self.a, "additionalProperties", .{ .bool = false });
                    if (required.items.len > 0) try o.put(self.a, "required", .{ .array = required.items }) else _ = o.orderedRemove("required");
                }
                _ = o.orderedRemove("oneOf");
                _ = meta.orderedRemove("choice");
            }
        };
        if (getObj(o, "properties")) |props| {
            var i: usize = 0;
            while (i < props.count()) {
                const v = props.values()[i];
                if (v == .object and !try self.prune(v.object)) {
                    props.orderedRemoveAt(i);
                } else {
                    i += 1;
                }
            }
            if (o.get("required")) |required| if (required == .array) {
                var keep: std.ArrayList(Val) = .empty;
                for (required.array) |item| if (item == .string and props.contains(item.string)) try keep.append(self.a, item);
                try o.put(self.a, "required", .{ .array = keep.items });
            };
        }
        if (getObj(o, "items")) |item| _ = try self.prune(item);
        for ([_][]const u8{ "oneOf", "anyOf", "allOf" }) |key| {
            const branches = o.get(key) orelse continue;
            if (branches != .array) continue;
            var keep: std.ArrayList(Val) = .empty;
            for (branches.array) |item| if (item != .object or try self.prune(item.object)) try keep.append(self.a, item);
            try o.put(self.a, key, .{ .array = keep.items });
        }
        return true;
    }
    fn report(self: *Projector, path: []const []const u8, kind: []const u8, expression: []const u8, reason: []const u8) gen.Error!void {
        const label = try self.a.print("/{s}", .{try std.mem.join(self.a, "/", path)});
        for (self.diagnostics.items) |item| if (equal(u8, item.path, label) and equal(u8, item.constraint, kind) and equal(u8, item.expression, expression) and equal(u8, item.reason, reason)) return;
        try self.diagnostics.append(self.a, .{ .path = label, .constraint = kind, .expression = expression, .reason = reason });
    }
    fn within(self: *Projector, expression: []const u8, path: []const []const u8, bindings: ?*Obj) gen.Error!bool {
        return expressionWithin(self.a, try parseExpr(self.a, expression), path, path, self.scope, self.module, bindings);
    }
    fn containsLeafref(self: *Projector, o: *Obj, depth: usize) bool {
        if (depth > 64) return true;
        if (getObj(o, "x-yang")) |xy| if (getString(xy, "type")) |kind| {
            if (equal(u8, kind, "leafref")) return true;
        };
        if (getString(o, "$ref")) |ref| if (std.mem.startsWith(u8, ref, "#/$defs/")) if (getObj(self.full, "$defs")) |defs| if (getObj(defs, ref[8..])) |definition| {
            if (self.containsLeafref(definition, depth + 1)) return true;
        };
        if (o.get("oneOf")) |variants| if (variants == .array) for (variants.array) |variant| {
            if (variant == .object and self.containsLeafref(variant.object, depth + 1)) return true;
        };
        return false;
    }
    fn visit(self: *Projector, o: *Obj, path: []const []const u8) gen.Error!void {
        const meta = getObj(o, "x-yang");
        if (meta) |xy| if (getString(xy, "type")) |kind| {
            if (equal(u8, kind, "leaf") or equal(u8, kind, "leaf-list")) {
                var resolved = o;
                if (getString(o, "$ref")) |ref| if (std.mem.startsWith(u8, ref, "#/$defs/")) if (getObj(self.full, "$defs")) |defs| {
                    resolved = getObj(defs, ref[8..]) orelse o;
                };
                if (resolved.contains("oneOf") and self.containsLeafref(resolved, 0)) return error.Export;
            }
        };
        if (meta) |xy| {
            if (xy.get("must")) |must| if (must == .array) {
                var keep: std.ArrayList(Val) = .empty;
                for (must.array) |item| {
                    if (item != .object) {
                        try keep.append(self.a, item);
                        continue;
                    }
                    const expression = getString(item.object, "must") orelse "";
                    if (try self.within(expression, path, getObj(item.object, "xpath-prefixes"))) try keep.append(self.a, item) else try self.report(path, "must", expression, external);
                }
                try xy.put(self.a, "must", .{ .array = keep.items });
            };
            if (getObj(xy, "when")) |when| if (getString(when, "condition")) |expression| {
                const parent = when.get("evaluate-with-parent-context") orelse .null;
                const context = if (parent == .bool and parent.bool and path.len > 0) path[0 .. path.len - 1] else path;
                if (!try self.within(expression, context, getObj(when, "xpath-prefixes"))) {
                    try self.report(path, "when", expression, external);
                    _ = xy.orderedRemove("when");
                }
            };
            var info: ?*Obj = null;
            if (getString(xy, "type")) |kind| if (equal(u8, kind, "leafref")) {
                info = xy;
            };
            if (info == null) if (getString(o, "$ref")) |ref| {
                if (std.mem.startsWith(u8, ref, "#/$defs/")) if (getObj(self.full, "$defs")) |defs| if (getObj(defs, ref[8..])) |definition| if (getObj(definition, "x-yang")) |candidate| {
                    if (getString(candidate, "type")) |kind| if (equal(u8, kind, "leafref")) {
                        info = candidate;
                    };
                };
            };
            if (info) |leafref| {
                if (leafref != xy) if (getString(o, "$ref")) |ref| if (std.mem.startsWith(u8, ref, "#/$defs/")) if (self.module.typedefs.get(ref[8..])) |td| {
                    if (td.kind() == .typedef) if (td.data.typedef.type) |td_type| if (td_type.leafrefPath() == null) if (td_type.pathAst()) |ast| {
                        if (ast.* == .path) for (ast.path.segments) |segment| if (segment.predicate != null) return error.Export;
                    };
                };
                const expression = getString(leafref, "path") orelse return error.Export;
                if (!prefixesSupported(try parseExpr(self.a, expression), self.module, getObj(leafref, "xpath-prefixes"))) return error.Export;
                const target_path = try targetPath(self.a, expression, path);
                var target = lookup(self.full, target_path) orelse return error.Export;
                var target_context = target_path;
                var seen: std.StringHashMapUnmanaged(void) = .empty;
                while (true) {
                    var target_meta = getObj(target, "x-yang");
                    if (target_meta == null or !equal(u8, getString(target_meta.?, "type") orelse "", "leafref")) {
                        if (getString(target, "$ref")) |ref| if (std.mem.startsWith(u8, ref, "#/$defs/")) if (getObj(self.full, "$defs")) |defs| if (getObj(defs, ref[8..])) |definition| {
                            target_meta = getObj(definition, "x-yang");
                        };
                    }
                    const next_meta = target_meta orelse break;
                    if (!equal(u8, getString(next_meta, "type") orelse "", "leafref")) break;
                    const label = try std.mem.join(self.a, "/", target_context);
                    if (seen.contains(label)) return error.Export;
                    try seen.put(self.a, label, {});
                    const next = getString(next_meta, "path") orelse return error.Export;
                    if (!prefixesSupported(try parseExpr(self.a, next), self.module, getObj(next_meta, "xpath-prefixes"))) return error.Export;
                    target_context = try targetPath(self.a, next, target_context);
                    target = lookup(self.full, target_context) orelse return error.Export;
                }
                for ([_][]const u8{ "type", "$ref", "enum", "pattern", "minimum", "maximum", "minLength", "maxLength", "anyOf", "oneOf", "allOf", "format", "multipleOf" }) |key| {
                    _ = o.orderedRemove(key);
                    if (target.get(key)) |value| try o.put(self.a, key, try clone(self.a, value));
                }
                const is_enabled = lookup(self.available, target_path) != null;
                if (!try self.within(expression, path, getObj(leafref, "xpath-prefixes")) or !is_enabled) {
                    try xy.put(self.a, "type", .{ .string = "leaf" });
                    _ = xy.orderedRemove("path");
                    _ = xy.orderedRemove("require-instance");
                    _ = xy.orderedRemove("xpath-prefixes");
                    try self.report(path, "leafref", expression, if (is_enabled) external else "target is disabled by feature selection");
                } else if (leafref != xy) {
                    for (leafref.keys(), leafref.values()) |key, value| try xy.put(self.a, key, try clone(self.a, value));
                }
            }
        }
        if (getObj(o, "properties")) |props| for (props.keys(), props.values()) |name, value| {
            if (value != .object) continue;
            const child = try self.a.alloc([]const u8, path.len + 1);
            @memcpy(child[0..path.len], path);
            child[path.len] = local(name);
            try self.visit(value.object, child);
        };
        if (getObj(o, "items")) |item| try self.visit(item, path);
        for ([_][]const u8{ "oneOf", "anyOf", "allOf" }) |key| {
            const branches = o.get(key) orelse continue;
            if (branches != .array) continue;
            for (branches.array) |item| if (item == .object) try self.visit(item.object, path);
        }
        if (self.native_json and meta != null) {
            const xy = meta.?;
            const kind = getString(xy, "type") orelse "";
            const key = getString(xy, "key") orelse "";
            if (equal(u8, kind, "list") and key.len > 0 and std.mem.indexOfAny(u8, key, " \t\n") == null) {
                const item = o.get("items") orelse return error.Export;
                const keyed_item = try clone(self.a, item);
                if (keyed_item == .object) if (keyed_item.object.get("required")) |required| if (required == .array) {
                    var keep: std.ArrayList(Val) = .empty;
                    for (required.array) |v| if (v != .string or !equal(u8, local(v.string), local(key))) try keep.append(self.a, v);
                    try keyed_item.object.put(self.a, "required", .{ .array = keep.items });
                };
                const array = try gen.newObject(self.a);
                const keyed = try gen.newObject(self.a);
                try array.put(self.a, "type", .{ .string = "array" });
                try array.put(self.a, "items", item);
                try keyed.put(self.a, "type", .{ .string = "object" });
                try keyed.put(self.a, "additionalProperties", keyed_item);
                for ([_][2][]const u8{ .{ "minItems", "minProperties" }, .{ "maxItems", "maxProperties" } }) |pair| if (o.get(pair[0])) |value| {
                    try array.put(self.a, pair[0], value);
                    try keyed.put(self.a, pair[1], value);
                    _ = o.orderedRemove(pair[0]);
                };
                _ = o.orderedRemove("type");
                _ = o.orderedRemove("items");
                const variants = try self.a.alloc(Val, 2);
                variants[0] = .{ .object = array };
                variants[1] = .{ .object = keyed };
                try o.put(self.a, "anyOf", .{ .array = variants });
            }
        }
    }
};

pub fn project(a: A, full: Val, module: *Module, path: []const u8, features: ?*const feature.EnabledFeatures, native_json: bool, diag: *Diagnostic) gen.Error!gen.SchemaExportResult {
    if (path.len < 2 or path[0] != '/') {
        diag.* = .{ .kind = .semantic, .message = "subtree path must be absolute" };
        return error.Export;
    }
    var segments: std.ArrayList([]const u8) = .empty;
    var iterator = std.mem.splitScalar(u8, path[1..], '/');
    while (iterator.next()) |segment| {
        if (segment.len == 0) {
            diag.* = .{ .kind = .semantic, .message = "invalid subtree path" };
            return error.Export;
        }
        if (std.mem.indexOfScalar(u8, segment, ':')) |i| {
            if (!equal(u8, segment[0..i], module.prefix) and !equal(u8, segment[0..i], module.name)) {
                diag.* = .{ .kind = .semantic, .message = "unsupported subtree path prefix" };
                return error.Export;
            }
        }
        try segments.append(a, local(segment));
    }
    const available = (try clone(a, full)).object;
    var enabled = try feature.buildEnabledFeatures(a, module, features);
    var self: Projector = .{ .a = a, .full = full.object, .available = available, .module = module, .scope = segments.items, .enabled = &enabled, .native_json = native_json };
    _ = self.prune(available) catch |err| {
        if (err == error.Export) diag.* = .{ .kind = .semantic, .message = "cannot safely resolve an unqualified if-feature shared with an imported module" };
        return err;
    };
    const chosen = lookup(available, segments.items) orelse {
        diag.* = .{ .kind = .semantic, .message = "subtree path not found or disabled" };
        return error.Export;
    };
    const selected = (try clone(a, .{ .object = chosen })).object;
    self.visit(selected, segments.items) catch |err| {
        if (err == error.Export) diag.* = .{ .kind = .semantic, .message = "cannot resolve subtree constraint" };
        return err;
    };
    const meta = getObj(selected, "x-yang") orelse blk: {
        const o = try gen.newObject(a);
        try selected.put(a, "x-yang", .{ .object = o });
        break :blk o;
    };
    try meta.put(a, "subtree-path", .{ .string = path });
    for ([_][]const u8{ "$schema", "$id", "$defs" }) |key| if (available.get(key)) |value| try selected.put(a, key, value);
    translatePatterns(a, .{ .object = selected }) catch |err| {
        if (err == error.Export) diag.* = .{ .kind = .semantic, .message = "subtree schema cannot portably encode an XSD regex shorthand or Unicode category" };
        return err;
    };
    return .{ .schema = .{ .object = selected }, .diagnostics = self.diagnostics.items };
}

test "subtree projection filters features and external constraints" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module m { namespace "urn:m"; prefix m; feature f;
        \\ typedef ext { type leafref { path "/m:outside/m:name"; } }
        \\ container outside { leaf name { type string { length "2..8"; } } }
        \\ container top { must "/m:outside/m:name = 'foo'";
        \\   leaf enabled { if-feature f; mandatory true; type string; }
        \\   leaf other { type leafref { path "/m:outside/m:name"; } }
        \\   leaf via { type ext; }
        \\   list nodes { key "name"; leaf name { type string; } }
        \\ } }
    , "test.yang", &diag);
    var overrides: feature.EnabledFeatures = .empty;
    try overrides.put(a, "m", .empty);
    const result = try gen.generateWithOptions(a, module, &diag, .{ .path = "/m:top", .features = &overrides, .native_json = true });
    const properties = getObj(result.schema.object, "properties").?;
    try std.testing.expect(!properties.contains("enabled"));
    try std.testing.expect(properties.contains("nodes"));
    try std.testing.expectEqual(@as(usize, 3), result.diagnostics.len);
    try std.testing.expectEqualStrings("must", result.diagnostics[0].constraint);
    try std.testing.expectEqualStrings("leafref", result.diagnostics[1].constraint);
    try std.testing.expectEqualStrings("leafref", result.diagnostics[2].constraint);
    var message: []const u8 = "";
    try std.testing.expectError(error.JsonForm, @import("parser.zig").parseJsonSchema(a, result.schema, &message));
    const other = properties.get("other").?.object;
    try std.testing.expectEqual(@as(i128, 2), other.get("minLength").?.int);
    try std.testing.expect(getObj(properties.get("nodes").?.object, "items") == null);
    try std.testing.expect((properties.get("nodes").?.object.get("anyOf").?).array.len == 2);
    const defaults = try gen.generateWithOptions(a, module, &diag, .{ .path = "/m:top" });
    try std.testing.expect(getObj(defaults.schema.object, "properties").?.contains("enabled"));
}

test "subtree projection rejects unavailable path" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a, "module m { namespace 'urn:m'; prefix m; container top {} }", "test.yang", &diag);
    try std.testing.expectError(error.Export, gen.generateWithOptions(a, module, &diag, .{ .path = "/m:missing" }));
}

test "subtree removes feature-disabled choice cases and leafref targets" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module c { namespace "urn:c"; prefix c; feature f;
        \\ container top { leaf target { if-feature f; type uint32; }
        \\ leaf ref { type leafref { path "../target"; } }
        \\ choice selection { case gated { if-feature f; leaf a { type string; } }
        \\ case open { leaf b { type string; } } } } }
    , "test.yang", &diag);
    var overrides: feature.EnabledFeatures = .empty;
    try overrides.put(a, "c", .empty);
    const result = try gen.generateWithOptions(a, module, &diag, .{ .path = "/c:top", .features = &overrides });
    try std.testing.expectEqual(@as(usize, 1), result.diagnostics.len);
    try std.testing.expectEqualStrings("target is disabled by feature selection", result.diagnostics[0].reason);
    const ref = lookup(result.schema.object, &.{"ref"}).?;
    try std.testing.expectEqualStrings("integer", getString(ref, "type").?);
    try std.testing.expect(lookup(result.schema.object, &.{"a"}) == null);
    try std.testing.expect(lookup(result.schema.object, &.{"b"}) != null);
}

test "disabled choice preserves unconditional siblings" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module c { namespace "urn:c"; prefix c; feature f;
        \\ container top { leaf shared { type string; mandatory true; }
        \\ choice selection { if-feature f; case gated { leaf a { type string; } } case other { leaf b { type string; } } } } }
    , "test.yang", &diag);
    var overrides: feature.EnabledFeatures = .empty;
    try overrides.put(a, "c", .empty);
    const result = try gen.generateWithOptions(a, module, &diag, .{ .path = "/c:top", .features = &overrides });
    const props = getObj(result.schema.object, "properties").?;
    try std.testing.expectEqual(@as(usize, 1), props.count());
    try std.testing.expect(props.contains("shared"));
    try std.testing.expectEqualStrings("shared", result.schema.object.get("required").?.array[0].string);
}

test "ambiguous imported feature context fails loudly" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const parser = @import("../parser/yang_parser.zig");
    const module = try parser.parseString(a, "module m { namespace 'urn:m'; prefix m; feature f; container top { leaf x { if-feature f; type string; } } }", "main.yang", &diag);
    const imported = try parser.parseString(a, "module lib { namespace 'urn:lib'; prefix l; feature f; }", "lib.yang", &diag);
    try module.import_prefixes.put(a, "l", imported);
    try std.testing.expectError(error.Export, gen.generateWithOptions(a, module, &diag, .{ .path = "/m:top" }));
}

test "subtree rejects nonportable XSD regex shorthand" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module p { namespace "urn:p"; prefix p;
        \\ container top { leaf value { type string { pattern '\d+'; } } } }
    , "test.yang", &diag);
    try std.testing.expectError(error.Export, gen.generateWithOptions(a, module, &diag, .{ .path = "/p:top" }));
}

test "leafref typedef predicates are preserved in diagnostics" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module m { namespace "urn:m"; prefix m;
        \\ list a { key name; leaf name { type string; } }
        \\ typedef t { type leafref { path "/a[name = current()/../x]/name"; } }
        \\ container top { leaf x { type string; } leaf v { type t; } } }
    , "test.yang", &diag);
    const result = try gen.generateWithOptions(a, module, &diag, .{ .path = "/m:top" });
    try std.testing.expectEqualStrings("/a[name = current()/../x]/name", result.diagnostics[0].expression);
}

test "leafref current predicate uses leaf context" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: Diagnostic = .{};
    const module = try @import("../parser/yang_parser.zig").parseString(a,
        \\module p { namespace "urn:p"; prefix p;
        \\ container top {
        \\  list nodes { key name; leaf name { type string; } leaf target { type string; } }
        \\  list links { key index; leaf index { type uint32; } leaf node { type string; }
        \\   leaf value { type leafref { path "/top/nodes[name = current()/../node]/target"; } }
        \\  }
        \\ } }
    , "test.yang", &diag);
    const whole = try gen.generateWithOptions(a, module, &diag, .{ .path = "/p:top" });
    try std.testing.expectEqual(@as(usize, 0), whole.diagnostics.len);
    const partial = try gen.generateWithOptions(a, module, &diag, .{ .path = "/p:top/links" });
    try std.testing.expectEqualStrings("/top/nodes[name = current()/../node]/target", partial.diagnostics[0].expression);
}
