//! YANG document validator (mirrors `src/xyang/validator/document_validator.py`).
//!
//! Walks the canonical data tree (see `encoding/instance.zig`) in lockstep with the
//! schema. At each node, in Python's order: if-feature, when, JSON shape, structural
//! checks (mandatory, min/max-elements, presence), must, type, then descend. `choice`
//! and `case` are not data nodes; their errors point at the parent data node.
//!
//! The walk carries the XPath `Node` of each data node (`Node.step`), so `when`, `must`
//! and leafref evaluate in the same context as Python: a node's own `when` and `must` at
//! that node, a `when` merged from `uses` or `augment` and a `choice` / `case` `when` at
//! the parent, a list's `must` per entry, a leaf-list's `must` per item.

const std = @import("std");
const ast = @import("../ast.zig");
const jv = @import("../json_value.zig");
const module_mod = @import("../module.zig");
const registry = @import("../types/registry.zig");
const if_feature_eval = @import("../if_feature_eval.zig");
const rfc7951 = @import("../encoding/rfc7951.zig");
const instance = @import("../encoding/instance.zig");
const type_checker = @import("type_checker.zig");
const PathBuilder = @import("path_builder.zig").PathBuilder;
const xpath = @import("../xpath/xpath.zig");
const xpath_utils = @import("../xpath/utils.zig");
const schema_nav = @import("../xpath/schema_nav.zig");
const operation_mod = @import("operation.zig");

const Allocator = std.mem.Allocator;
const Statement = ast.Statement;
const TypeStmt = ast.TypeStmt;
const Module = module_mod.Module;
const Val = jv.Val;
const Object = jv.Object;
const XNode = xpath.Node;

pub const Error = type_checker.Error;

pub const Severity = enum { @"error", warning };

pub const ValidationError = struct {
    /// Display path (`/top/items[id='a']/v`), printed by text output.
    path: []const u8,
    message: []const u8,
    expression: ?[]const u8 = null,
    severity: Severity = .@"error",
    code: []const u8,
    /// JSON Pointer into the instance as written.
    pointer: []const u8,
    document: []const u8 = "data",
};

/// The schema node whose children are walked: the module or a statement.
const Owner = union(enum) {
    module: *Module,
    stmt: *Statement,

    fn statements(o: Owner) []const *Statement {
        return switch (o) {
            .module => |m| m.statements.items,
            .stmt => |s| s.statements.items,
        };
    }
};

fn isContainerKind(s: *const Statement) bool {
    return switch (s.kind()) {
        .container, .notification, .input, .output => true,
        else => false,
    };
}

fn presence(s: *const Statement) ?[]const u8 {
    return switch (s.data) {
        .container, .notification, .input, .output => |c| c.presence,
        else => null,
    };
}

fn leafType(s: *const Statement) ?*TypeStmt {
    return switch (s.data) {
        .leaf => |d| d.type,
        .leaf_list => |d| d.type,
        else => null,
    };
}

pub const DocumentValidator = struct {
    a: Allocator,
    module: *Module,
    enabled: if_feature_eval.EnabledFeatures,
    checker: *type_checker.TypeChecker,
    keys: *rfc7951.MemberKeys,
    errors: std.ArrayList(ValidationError) = .empty,
    /// The XPath root: the canonical data under the module.
    root: *const XNode = undefined,
    case_stack: std.ArrayList(*Statement) = .empty,
    case_data_stack: std.ArrayList(*const Object) = .empty,
    /// False when the root schema is an RFC 8791 structure (Python's root schema is then
    /// not a `YangModule`): every `if-feature` holds. Defaults still resolve against
    /// the containing module, like Python's `_typedef_module`.
    module_root: bool = true,

    fn add(self: *DocumentValidator, path: []const u8, pointer: []const u8, code: []const u8, message: []const u8) error{OutOfMemory}!void {
        try self.errors.append(self.a, .{ .path = path, .pointer = pointer, .code = code, .message = message });
    }

    fn addExpr(self: *DocumentValidator, path: []const u8, pointer: []const u8, code: []const u8, message: []const u8, expression: []const u8) error{OutOfMemory}!void {
        try self.errors.append(self.a, .{ .path = path, .pointer = pointer, .code = code, .message = message, .expression = expression });
    }

    fn context(self: *const DocumentValidator, node: *const XNode) xpath.Context {
        return .{ .current = node, .root = self.root };
    }

    /// `_eval_expr`: the expression as a YANG boolean at `node`, or null when it has no
    /// AST or its evaluation raises.
    fn evalExpr(self: *DocumentValidator, e: ?*xpath.Expr, node: *const XNode) error{OutOfMemory}!?bool {
        const expr = e orelse return null;
        var ev: xpath.Evaluator = .{ .a = self.a };
        const v = ev.eval(expr, self.context(node), node) catch |err| switch (err) {
            error.OutOfMemory => return error.OutOfMemory,
            error.XPathEval => return null,
        };
        return xpath_utils.yangBool(v);
    }

    /// `_check_must`: each `must` of `s` at `node`.
    fn checkMust(self: *DocumentValidator, s: *const Statement, node: *const XNode, path: []const u8, pointer: []const u8) error{OutOfMemory}!void {
        for (s.must_statements.items) |must| {
            const result = try self.evalExpr(must.ast, node) orelse {
                try self.addExpr(path, pointer, "xpath-error", try std.fmt.allocPrint(self.a, "Error evaluating must expression on '{s}'", .{s.name}), must.expression);
                continue;
            };
            if (!result) {
                const base = if (must.error_message.len > 0) must.error_message else try std.fmt.allocPrint(self.a, "must constraint not satisfied on '{s}'", .{s.name});
                const message = if (must.error_app_tag.len > 0) try std.fmt.allocPrint(self.a, "{s} (error-app-tag: {s})", .{ base, must.error_app_tag }) else base;
                try self.addExpr(path, pointer, "must", message, must.expression);
            }
        }
    }

    fn ifFeaturesActive(self: *DocumentValidator, s: *const Statement) error{OutOfMemory}!bool {
        if (!self.module_root) return true;
        if (!s.hasIfFeatures() or s.if_features.items.len == 0) return true;
        return if_feature_eval.ifFeaturesSatisfied(self.a, s.if_features.items, self.module, &self.enabled);
    }

    /// `validate`: walk the canonical tree from the module root.
    pub fn validate(self: *DocumentValidator, data: Val) Error![]ValidationError {
        self.errors = .empty;
        self.case_stack = .empty;
        self.case_data_stack = .empty;
        var path: PathBuilder = .{ .a = self.a };
        self.root = try xpath.node.newNode(self.a, data, .{ .module = self.module }, null);
        try self.visitChildren(data, .{ .module = self.module }, &path, true, self.root);
        return self.errors.items;
    }

    /// `validate` with an RFC 8791 structure as the root schema (`module_root` false).
    pub fn validateStructure(self: *DocumentValidator, data: Val, structure: *Statement) Error![]ValidationError {
        self.errors = .empty;
        self.case_stack = .empty;
        self.case_data_stack = .empty;
        var path: PathBuilder = .{ .a = self.a };
        self.root = try xpath.node.newNode(self.a, data, .{ .stmt = structure }, null);
        try self.visitChildren(data, .{ .stmt = structure }, &path, true, self.root);
        return self.errors.items;
    }

    /// What `validateOperation` checks: `self.module` is the accessible module of RFC 7950
    /// 6.4.1 and `parent_copies` are its copies of `target.parents`.
    pub const OperationRun = struct {
        target: operation_mod.OperationTarget,
        operation: *Statement,
        parent_copies: []const *Statement,
        host: *Module,
        /// Server data in the same encoding, already validated against the module.
        context: ?Val,
        native: bool,
    };

    /// `validate_operation`: the parameters of one rpc or action `input` or `output`
    /// (RFC 7950 7.14, 7.15), without the RFC 8040 wrapper. Pointers address `params`.
    pub fn validateOperation(self: *DocumentValidator, u: *operation_mod.Usage, params: Val, run: OperationRun) (Error || error{Usage})![]ValidationError {
        const target = run.target;
        for (target.parents) |step| {
            for (step.wrappers) |w| if (!try self.ifFeaturesActive(w)) {
                return u.fail("{s} is not available: '{s}' has a false 'if-feature' condition", .{ target.label, w.name });
            };
            if (!try self.ifFeaturesActive(step.stmt)) {
                return u.fail("{s} is not available: '{s}' has a false 'if-feature' condition", .{ target.label, step.stmt.name });
            }
        }
        if (!try self.ifFeaturesActive(target.operation)) {
            return u.fail("{s} is not available: its 'if-feature' condition is false", .{target.label});
        }
        var out: std.ArrayList(ValidationError) = .empty;
        if (params != .object) {
            try out.append(self.a, .{ .path = "/", .pointer = "", .code = "type", .message = "operation parameters must be an object" });
            return out.items;
        }
        var walk_keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = target.module_name };
        var walk: instance.Walk = .{ .a = self.a, .module = run.host, .native = run.native, .keys = &walk_keys, .checker = self.checker };
        const nodes = try walk.walkObject(params.object, run.operation, "", false);
        const projection = try instance.project(self.a, self.keys, nodes.items);
        const canonical = projection.data;
        for (try instance.encodingErrors(self.a, nodes.items)) |e| {
            try out.append(self.a, .{ .path = if (e.pointer.len > 0) e.pointer else "/", .pointer = e.pointer, .code = e.code, .message = e.message });
        }

        var root_data = try self.a.create(Object);
        root_data.* = .empty;
        if (run.context) |c| if (c == .object) {
            var context_keys: rfc7951.MemberKeys = .{ .a = self.a, .parent_module = run.host.name };
            var context_walk: instance.Walk = .{ .a = self.a, .module = run.host, .native = run.native, .keys = &context_keys, .checker = self.checker };
            const context_nodes = try context_walk.walkObject(c.object, null, "", true);
            root_data = (try instance.project(self.a, self.keys, context_nodes.items)).data;
        };

        const root = try xpath.node.newNode(self.a, .{ .object = root_data }, .{ .module = self.module }, null);
        var holder = root_data;
        var holder_node = root;
        for (target.parents, run.parent_copies) |step, copied| {
            const member = (try self.keys.key(step.stmt)) orelse step.stmt.name;
            const value = holder.get(member);
            if (step.stmt.kind() == .list) {
                const key_names = try keyNames(self.a, step.stmt);
                var key_members: std.ArrayList([]const u8) = .empty;
                for (key_names) |k| {
                    const leaf = schema_nav.child(.{ .stmt = step.stmt }, k);
                    try key_members.append(self.a, if (leaf) |l| (try self.keys.key(l)) orelse l.name else k);
                }
                const rows: []const Val = if (value) |v| (if (v == .array) v.array else &.{}) else &.{};
                const row: ?*Object = for (rows) |r| {
                    if (r != .object) continue;
                    const matches = for (key_members.items, step.keys.?) |k, want| {
                        const got = r.object.get(k) orelse break false;
                        if (!std.mem.eql(u8, try operation_mod.lexical(self.a, got), want)) break false;
                    } else true;
                    if (matches) break r.object;
                } else null;
                const entry = row orelse {
                    return self.missingParent(target, try std.fmt.allocPrint(self.a, "no '{s}' entry with key {s}", .{ step.stmt.name, try std.mem.join(self.a, ", ", step.keys.?) }));
                };
                holder = entry;
                holder_node = try xpath.node.newNode(self.a, .{ .object = entry }, .{ .stmt = copied }, holder_node);
            } else {
                var obj: *Object = undefined;
                if (value) |v| {
                    if (v != .object) {
                        return self.missingParent(target, try std.fmt.allocPrint(self.a, "presence container '{s}' is absent", .{step.stmt.name}));
                    }
                    obj = v.object;
                } else {
                    if (presence(step.stmt) != null) {
                        return self.missingParent(target, try std.fmt.allocPrint(self.a, "presence container '{s}' is absent", .{step.stmt.name}));
                    }
                    // RFC 7950 7.5.1: a non-presence container exists implicitly.
                    obj = try self.a.create(Object);
                    obj.* = .empty;
                    try holder.put(self.a, member, .{ .object = obj });
                }
                holder = obj;
                holder_node = try xpath.node.newNode(self.a, .{ .object = obj }, .{ .stmt = copied }, holder_node);
            }
        }
        try holder.put(self.a, (try self.keys.key(run.operation)) orelse run.operation.name, .{ .object = canonical });

        self.errors = .empty;
        self.case_stack = .empty;
        self.case_data_stack = .empty;
        self.root = root;
        const op_node = try holder_node.step(self.a, .{ .object = canonical }, .{ .stmt = run.operation });
        try self.checkMust(run.operation, op_node, "/", "");
        var path: PathBuilder = .{ .a = self.a };
        try self.visitChildren(.{ .object = canonical }, .{ .stmt = run.operation }, &path, true, op_node);
        for (self.errors.items) |e| {
            var err = e;
            err.pointer = try instance.remapPointer(self.a, e.pointer, &projection.map);
            try out.append(self.a, err);
        }
        return out.items;
    }

    fn missingParent(self: *DocumentValidator, target: operation_mod.OperationTarget, detail: []const u8) error{OutOfMemory}![]ValidationError {
        const out = try self.a.alloc(ValidationError, 1);
        out[0] = .{
            .path = "/",
            .pointer = "",
            .document = "context",
            .code = "action-parent",
            .message = try std.fmt.allocPrint(self.a, "{s} is invoked on an instance that is not in the context: {s}", .{ target.label, detail }),
        };
        return out;
    }

    fn childEnforce(owner: Owner, parent_enforce: bool) bool {
        const s = switch (owner) {
            .module => return true,
            .stmt => |s| s,
        };
        if (s.kind() == .case) return false;
        if (isContainerKind(s)) return if (presence(s) == null) parent_enforce else true;
        if (s.kind() == .list) return true;
        return parent_enforce;
    }

    // -- effective values and defaults --------------------------------------------------

    fn effectiveValue(self: *DocumentValidator, data: *const Object, s: *const Statement) Error!?Val {
        const found = try self.keys.lookup(data, s);
        if (found.json_key != null) return found.value;
        // Schema defaults are YANG lexical text; integer typedefs and unions decode here.
        const d = schema_nav.default(s) orelse return null;
        if (d != .string) return d;
        const t = s.data.leaf.type orelse return d;
        return try self.decodeLexical(t, d.string, &.{});
    }

    const Marker = struct { prefix: ?[]const u8, name: []const u8 };

    fn seenMarker(seen: []const Marker, m: Marker) bool {
        for (seen) |s| {
            const same_prefix = if (s.prefix == null or m.prefix == null) s.prefix == null and m.prefix == null else std.mem.eql(u8, s.prefix.?, m.prefix.?);
            if (same_prefix and std.mem.eql(u8, s.name, m.name)) return true;
        }
        return false;
    }

    /// `_decode_lexical`: a schema default as the value its type decodes it to.
    fn decodeLexical(self: *DocumentValidator, t: *const TypeStmt, value: []const u8, seen_in: []const Marker) Error!Val {
        const marker: Marker = .{ .prefix = t.prefix, .name = t.name };
        if (seenMarker(seen_in, marker)) return .{ .string = value };
        const seen = try std.mem.concat(self.a, Marker, &.{ seen_in, &.{marker} });
        if (t.prefix == null and registry.isIntegerName(t.name) and instance.isIntText(value)) {
            const n: Val = .{ .int = std.fmt.parseInt(i128, value, 10) catch return .{ .string = value } };
            return if (try self.accepted(n, t)) n else .{ .string = value };
        }
        if (t.prefix == null and registry.isDecimalName(t.name) and instance.isDecText(value)) {
            const n: Val = .{ .decimal = jv.Decimal.parse(self.a, value) catch return .{ .string = value } };
            return if (try self.accepted(n, t)) n else .{ .string = value };
        }
        if (t.prefix == null and std.mem.eql(u8, t.name, registry.UNION)) {
            for (t.members()) |member| {
                const decoded = try self.decodeLexical(member, value, seen);
                if (try self.accepted(decoded, member)) return decoded;
            }
            return .{ .string = value };
        }
        if (module_mod.resolveTypedef(t, self.module)) |r| {
            if (r.typedef.data.typedef.type) |inner| return self.decodeLexical(inner, value, seen);
        }
        return .{ .string = value };
    }

    /// `_default_accepted`: the type accepts the decoded default, checked as a value of
    /// its own (`Node(value, type)` as the XPath root).
    fn accepted(self: *DocumentValidator, v: Val, t: *const TypeStmt) Error!bool {
        const node = try xpath.node.newNode(self.a, v, .none, null);
        return (try self.checker.checkIn(v, t, .{ .current = node, .root = node })).len == 0;
    }

    // -- choice and mandatory helpers -----------------------------------------------------

    fn hasMatchingData(self: *DocumentValidator, s: *const Statement, data: *const Object) Error!bool {
        switch (s.kind()) {
            .leaf, .anydata, .anyxml, .leaf_list, .list, .container, .notification, .input, .output => return self.keys.present(data, s),
            .choice => {
                for (s.data.choice.cases.items) |case| {
                    for (case.statements.items) |ch| if (try self.hasMatchingData(ch, data)) return true;
                }
                return false;
            },
            else => return false,
        }
    }

    fn caseHasOtherData(self: *DocumentValidator, case: *const Statement, data: *const Object, skip: *const Statement) Error!bool {
        for (case.statements.items) |s| {
            if (s == skip) continue;
            if (try self.hasMatchingData(s, data)) return true;
        }
        return false;
    }

    fn caseHasAnyData(self: *DocumentValidator, case: *const Statement, data: *const Object) Error!bool {
        for (case.statements.items) |s| if (try self.hasMatchingData(s, data)) return true;
        return false;
    }

    fn caseLevelData(self: *DocumentValidator) *const Object {
        if (self.case_data_stack.items.len > 0) return self.case_data_stack.items[self.case_data_stack.items.len - 1];
        return &empty_object;
    }

    fn mandatoryChoiceViolation(self: *DocumentValidator, choice: *const Statement, enforce: bool) Error!bool {
        if (!choice.data.choice.mandatory) return false;
        if (enforce) return true;
        if (self.case_stack.items.len == 0) return true;
        return self.caseHasOtherData(self.case_stack.items[self.case_stack.items.len - 1], self.caseLevelData(), choice);
    }

    fn leafMandatoryMustExist(self: *DocumentValidator, enforce: bool) Error!bool {
        if (enforce) return true;
        if (self.case_stack.items.len == 0) return true;
        return self.caseHasAnyData(self.case_stack.items[self.case_stack.items.len - 1], self.caseLevelData());
    }

    fn mandatoryOf(s: *const Statement) bool {
        return switch (s.data) {
            .leaf => |d| d.mandatory,
            .anydata => |d| d.mandatory,
            .anyxml => |d| d.mandatory,
            else => false,
        };
    }

    // -- tree walk -------------------------------------------------------------------------

    const NameSet = std.StringHashMapUnmanaged(void);

    fn visitChildren(self: *DocumentValidator, data: Val, owner: Owner, path: *PathBuilder, enforce: bool, parent: *const XNode) Error!void {
        if (data != .object) return;
        const obj = data.object;
        const child_enforce = childEnforce(owner, enforce);
        var visited: NameSet = .empty;
        for (owner.statements()) |s| {
            if (s.kind() == .rpc or s.kind() == .action) continue;
            if (s.kind() == .choice) {
                try self.choiceInstanceKeys(s, obj, &visited);
            } else if (try self.keys.key(s)) |k| {
                try visited.put(self.a, k, {});
            }
            try self.visitStmt(s, obj, path, child_enforce, parent);
        }
        for (obj.keys()) |key| {
            if (visited.contains(key)) continue;
            try self.add(try path.child(key), try path.childPointer(key), "unknown-field", try std.fmt.allocPrint(self.a, "Unknown field '{s}'", .{key}));
        }
    }

    fn visitStmt(self: *DocumentValidator, s: *Statement, data: *const Object, path: *PathBuilder, enforce: bool, parent: *const XNode) Error!void {
        if (s.kind() == .choice) return self.visitChoice(s, data, path, enforce, parent);
        if (s.kind() == .case) {
            try self.case_stack.append(self.a, s);
            try self.case_data_stack.append(self.a, data);
            defer {
                _ = self.case_data_stack.pop();
                _ = self.case_stack.pop();
            }
            return self.visitChildren(.{ .object = @constCast(data) }, .{ .stmt = s }, path, childEnforce(.{ .stmt = s }, enforce), parent);
        }

        const name = s.name;
        const present = try self.keys.present(data, s);
        const found = try self.keys.lookup(data, s);
        const json_name = found.json_key orelse name;
        const child_path = try path.child(json_name);
        const child_pointer = try path.childPointer(json_name);

        if (!try self.ifFeaturesActive(s)) {
            if (present) {
                try self.add(child_path, child_pointer, "if-feature", try std.fmt.allocPrint(self.a, "Node '{s}' is present but its 'if-feature' condition is false \u{2014} this node must not exist", .{name}));
            }
            return;
        }

        const val = try self.effectiveValue(data, s);
        const curr = try parent.step(self.a, val orelse .null, .{ .stmt = s });

        if (s.hasWhen()) if (s.when) |w| {
            // RFC 7950 7.21.5: a `when` merged from `uses` or `augment` uses the parent.
            const ok = try self.evalExpr(w.ast, if (w.evaluate_with_parent_context) parent else curr) orelse true;
            if (!ok) {
                if (present) {
                    try self.addExpr(child_path, child_pointer, "when", try std.fmt.allocPrint(self.a, "Node '{s}' is present but its 'when' condition evaluates to false \u{2014} this node must not exist", .{name}), w.expression);
                }
                return;
            }
        };

        if (present) {
            const v = val orelse Val.null;
            if (isContainerKind(s) and v != .object) {
                try self.add(child_path, child_pointer, "type", "container must be an object");
                return;
            }
            if (s.kind() == .list) {
                if (v != .array) {
                    try self.add(child_path, child_pointer, "type", "list must be an array");
                    return;
                }
                for (v.array, 0..) |entry, i| {
                    if (entry != .object) {
                        try self.add(try std.fmt.allocPrint(self.a, "{s}[{d}]", .{ child_path, i }), try std.fmt.allocPrint(self.a, "{s}/{d}", .{ child_pointer, i }), "type", "list item must be an object");
                    }
                }
            }
            if (s.kind() == .leaf_list and v != .array) {
                try self.add(child_path, child_pointer, "type", "leaf-list must be an array");
                return;
            }
        }

        if (!try self.checkStructural(s, name, data, val, present, child_path, child_pointer, enforce)) {
            if (isContainerKind(s) and presence(s) == null and !present) {
                // RFC 7950 7.5.1: a non-presence container exists implicitly.
                try path.push(name, null, null, json_name);
                defer path.pop();
                const empty = try self.a.create(Object);
                empty.* = .empty;
                const empty_node = try parent.step(self.a, .{ .object = empty }, .{ .stmt = s });
                try self.visitChildren(.{ .object = empty }, .{ .stmt = s }, path, childEnforce(.{ .stmt = s }, enforce), empty_node);
            }
            return;
        }

        if (s.hasMust() and s.kind() != .list) {
            if (s.kind() == .leaf_list) {
                // Per element; a non-array value was already rejected above.
                const items: []const Val = if (val) |v| (if (v == .array) v.array else &.{}) else &.{};
                for (items, 0..) |item, i| {
                    const item_node = try parent.step(self.a, item, .{ .stmt = s });
                    try self.checkMust(s, item_node, try std.fmt.allocPrint(self.a, "{s}[{d}]", .{ child_path, i }), try std.fmt.allocPrint(self.a, "{s}/{d}", .{ child_pointer, i }));
                }
            } else {
                try self.checkMust(s, curr, child_path, child_pointer);
            }
        }

        if (s.kind() == .leaf) if (leafType(s)) |t| if (val) |v| if (v != .null) {
            for (try self.checker.checkIn(v, t, self.context(curr))) |i| try self.add(child_path, child_pointer, i.code, i.message);
        };
        if (s.kind() == .leaf_list) if (leafType(s)) |t| {
            const items: []const Val = if (val) |v| (if (v == .array) v.array else &.{}) else &.{};
            for (items, 0..) |item, i| {
                const item_path = try std.fmt.allocPrint(self.a, "{s}[{d}]", .{ child_path, i });
                const item_pointer = try std.fmt.allocPrint(self.a, "{s}/{d}", .{ child_pointer, i });
                const item_node = try parent.step(self.a, item, .{ .stmt = s });
                for (try self.checker.checkIn(item, t, self.context(item_node))) |iss| try self.add(item_path, item_pointer, iss.code, iss.message);
            }
        };

        const v = val orelse return;
        if (isContainerKind(s) and v == .object) {
            try path.push(name, null, null, json_name);
            defer path.pop();
            try self.visitChildren(v, .{ .stmt = s }, path, childEnforce(.{ .stmt = s }, enforce), curr);
        } else if (s.kind() == .list and v == .array) {
            const key_names = try keyNames(self.a, s);
            try self.checkListKeyUniqueness(v.array, key_names, name, child_path, child_pointer);
            try self.checkListUnique(s, v.array, child_path, child_pointer);
            for (v.array, 0..) |entry, i| {
                if (entry != .object) continue;
                try path.push(name, try self.entryKey(entry.object, key_names), i, json_name);
                defer path.pop();
                const entry_node = try xpath.node.newNode(self.a, entry, .{ .stmt = s }, parent);
                try self.checkMust(s, entry_node, try path.current(), try path.pointer());
                try self.visitChildren(entry, .{ .stmt = s }, path, childEnforce(.{ .stmt = s }, enforce), entry_node);
            }
        }
    }

    fn keyNames(a: Allocator, s: *const Statement) error{OutOfMemory}![]const []const u8 {
        var out: std.ArrayList([]const u8) = .empty;
        const key = s.data.list.key orelse return out.items;
        var it = std.mem.tokenizeAny(u8, key, &std.ascii.whitespace);
        while (it.next()) |k| try out.append(a, k);
        return out.items;
    }

    /// `_entry_key_from_names`: `k='v', ...` for the display path, or null.
    fn entryKey(self: *DocumentValidator, entry: *const Object, key_names: []const []const u8) error{OutOfMemory}!?[]const u8 {
        if (key_names.len == 0) return null;
        var parts: std.ArrayList([]const u8) = .empty;
        for (key_names) |k| try parts.append(self.a, try std.fmt.allocPrint(self.a, "{s}='{f}'", .{ k, jv.pyStr(entry.get(k) orelse .null) }));
        return try std.mem.join(self.a, ", ", parts.items);
    }

    /// `_stmt_instance_keys_from_data`.
    fn stmtInstanceKeys(self: *DocumentValidator, s: *Statement, data: *const Object, out: *NameSet) Error!void {
        if (try self.keys.key(s)) |k| if (data.contains(k)) {
            try out.put(self.a, k, {});
            return;
        };
        if (s.kind() == .choice) try self.choiceInstanceKeys(s, data, out);
    }

    /// `_choice_instance_keys`: keys in `data` consumed by this choice.
    fn choiceInstanceKeys(self: *DocumentValidator, choice: *Statement, data: *const Object, out: *NameSet) Error!void {
        if (!try self.ifFeaturesActive(choice)) return;
        var active: std.ArrayList(*Statement) = .empty;
        for (choice.data.choice.cases.items) |c| {
            if (try self.ifFeaturesActive(c) and try self.caseHasAnyData(c, data)) try active.append(self.a, c);
        }
        for (active.items) |case| {
            for (case.statements.items) |s| try self.stmtInstanceKeys(s, data, out);
        }
    }

    fn visitChoice(self: *DocumentValidator, choice: *Statement, data: *const Object, path: *PathBuilder, enforce: bool, parent: *const XNode) Error!void {
        const cname = choice.name;
        if (!try self.ifFeaturesActive(choice)) {
            for (choice.data.choice.cases.items) |c| if (try self.caseHasAnyData(c, data)) {
                try self.add(try path.current(), try path.pointer(), "if-feature", try std.fmt.allocPrint(self.a, "Choice '{s}' has data but its 'if-feature' condition is false \u{2014} this branch must not exist", .{cname}));
                break;
            };
            return;
        }
        if (choice.when) |w| {
            if (!(try self.evalExpr(w.ast, parent) orelse true)) {
                for (choice.data.choice.cases.items) |c| if (try self.caseHasAnyData(c, data)) {
                    try self.addExpr(try path.current(), try path.pointer(), "when", try std.fmt.allocPrint(self.a, "Choice '{s}' has data but its 'when' evaluates to false \u{2014} this branch must not exist", .{cname}), w.expression);
                    break;
                };
                return;
            }
        }
        var active: std.ArrayList(*Statement) = .empty;
        for (choice.data.choice.cases.items) |case| {
            if (!try self.ifFeaturesActive(case)) {
                if (try self.caseHasAnyData(case, data)) {
                    try self.add(try path.current(), try path.pointer(), "if-feature", try std.fmt.allocPrint(self.a, "Case '{s}' of choice '{s}' has data but its 'if-feature' condition is false \u{2014} this branch must not exist", .{ case.name, cname }));
                    return;
                }
                continue;
            }
            if (!try self.caseHasAnyData(case, data)) continue;
            if (case.when) |w| {
                if (!(try self.evalExpr(w.ast, parent) orelse true)) {
                    try self.addExpr(try path.current(), try path.pointer(), "when", try std.fmt.allocPrint(self.a, "Case '{s}' of choice '{s}' has data but its 'when' evaluates to false \u{2014} this branch must not exist", .{ case.name, cname }), w.expression);
                    return;
                }
            }
            try active.append(self.a, case);
        }
        if (active.items.len > 1) {
            var names: std.ArrayList([]const u8) = .empty;
            for (active.items) |c| try names.append(self.a, c.name);
            try self.add(try path.current(), try path.pointer(), "choice-multiple-cases", try std.fmt.allocPrint(self.a, "Choice '{s}' allows only one case; data matches multiple cases: {s}", .{ cname, try std.mem.join(self.a, ", ", names.items) }));
            return;
        }
        if (active.items.len == 0) {
            if (try self.mandatoryChoiceViolation(choice, enforce)) {
                try self.add(try path.current(), try path.pointer(), "mandatory-choice", try std.fmt.allocPrint(self.a, "Mandatory choice '{s}' has no active case", .{cname}));
            }
            return;
        }
        const case = active.items[0];
        try self.case_stack.append(self.a, case);
        try self.case_data_stack.append(self.a, data);
        defer {
            _ = self.case_data_stack.pop();
            _ = self.case_stack.pop();
        }
        const inner = childEnforce(.{ .stmt = case }, enforce);
        for (case.statements.items) |s| try self.visitStmt(s, data, path, inner, parent);
    }

    /// `_check_structural`: false when the node is absent and nothing further applies.
    fn checkStructural(self: *DocumentValidator, s: *const Statement, name: []const u8, data: *const Object, effective: ?Val, present: bool, path: []const u8, pointer: []const u8, enforce: bool) Error!bool {
        _ = data;
        const eff_present = if (effective) |e| e != .null else false;
        switch (s.kind()) {
            .leaf => {
                if (leafType(s)) |t| if (std.mem.eql(u8, t.name, registry.EMPTY) and present) return true;
                if (!eff_present and mandatoryOf(s)) {
                    if (try self.leafMandatoryMustExist(enforce)) {
                        try self.add(path, pointer, "mandatory", try std.fmt.allocPrint(self.a, "Mandatory leaf '{s}' is missing", .{name}));
                    }
                }
                return eff_present;
            },
            .anydata, .anyxml => {
                if (!eff_present and mandatoryOf(s)) {
                    if (try self.leafMandatoryMustExist(enforce)) {
                        const kind = if (s.kind() == .anydata) "anydata" else "anyxml";
                        try self.add(path, pointer, "mandatory", try std.fmt.allocPrint(self.a, "Mandatory {s} '{s}' is missing", .{ kind, name }));
                    }
                }
                return eff_present;
            },
            .list, .leaf_list => {
                const count: usize = if (effective) |e| (if (e == .array) e.array.len else if (e != .null) 1 else 0) else 0;
                const min_e = if (s.kind() == .list) s.data.list.min_elements else s.data.leaf_list.min_elements;
                const max_e = if (s.kind() == .list) s.data.list.max_elements else s.data.leaf_list.max_elements;
                if (min_e) |m| if (@as(i64, @intCast(count)) < m) {
                    try self.add(path, pointer, "min-elements", try std.fmt.allocPrint(self.a, "'{s}' has {d} element(s) but requires at least {d}", .{ name, count, m }));
                };
                if (max_e) |m| if (present and @as(i64, @intCast(count)) > m) {
                    try self.add(path, pointer, "max-elements", try std.fmt.allocPrint(self.a, "'{s}' has {d} element(s) but allows at most {d}", .{ name, count, m }));
                };
                return present;
            },
            else => return present,
        }
    }

    /// Python's `hash`/`==` classes for key tuples: `1`, `1.0` and `True` collide.
    fn hashKey(self: *DocumentValidator, v: Val) error{OutOfMemory}![]const u8 {
        return switch (v) {
            .null => "N",
            .bool => |b| if (b) "#1" else "#0",
            .int => |i| std.fmt.allocPrint(self.a, "#{d}", .{i}),
            .float => |f| if (std.math.isFinite(f) and @floor(f) == f and @abs(f) < 1e38)
                std.fmt.allocPrint(self.a, "#{d}", .{@as(i128, @intFromFloat(f))})
            else
                std.fmt.allocPrint(self.a, "#{f}", .{jv.floatRepr(f)}),
            .decimal => |d| if (d.toInt()) |i| std.fmt.allocPrint(self.a, "#{d}", .{i}) else std.fmt.allocPrint(self.a, "#{f}", .{jv.floatRepr(d.toFloat())}),
            .string => |s| std.fmt.allocPrint(self.a, "S{s}", .{s}),
            else => std.fmt.allocPrint(self.a, "R{f}", .{jv.pyRepr(v)}),
        };
    }

    fn checkListKeyUniqueness(self: *DocumentValidator, entries: []const Val, key_names: []const []const u8, list_name: []const u8, path: []const u8, pointer: []const u8) Error!void {
        if (key_names.len == 0) return;
        var seen: std.StringHashMapUnmanaged(usize) = .empty;
        for (entries, 0..) |entry, i| {
            if (entry != .object) continue;
            var parts: std.ArrayList([]const u8) = .empty;
            for (key_names) |k| try parts.append(self.a, try self.hashKey(entry.object.get(k) orelse .null));
            const token = try std.mem.join(self.a, "\x00", parts.items);
            if (seen.get(token)) |first| {
                var shown: std.ArrayList([]const u8) = .empty;
                for (key_names) |k| try shown.append(self.a, try std.fmt.allocPrint(self.a, "{s}='{f}'", .{ k, jv.pyStr(entry.object.get(k) orelse .null) }));
                try self.add(path, pointer, "duplicate-key", try std.fmt.allocPrint(self.a, "Duplicate key in list '{s}': {s} (entries at index {d} and {d})", .{ list_name, try std.mem.join(self.a, ", ", shown.items), first, i }));
                return;
            }
            try seen.put(self.a, token, i);
        }
    }

    fn descendantValue(entry: Val, p: []const u8) ?Val {
        var cur = entry;
        var it = std.mem.splitScalar(u8, p, '/');
        while (it.next()) |seg| {
            if (cur != .object) return null;
            cur = cur.object.get(seg) orelse return null;
        }
        return cur;
    }

    /// `_unique_display`.
    fn uniqueDisplay(self: *DocumentValidator, v: Val) error{OutOfMemory}![]const u8 {
        if (v == .bool) return if (v.bool) "true" else "false";
        return std.fmt.allocPrint(self.a, "{f}", .{jv.pyStr(v)});
    }

    /// RFC 7950 7.8.3: one error per `unique` set whose values repeat across entries.
    fn checkListUnique(self: *DocumentValidator, s: *const Statement, entries: []const Val, path: []const u8, pointer: []const u8) Error!void {
        for (s.data.list.unique.items) |paths| {
            var seen: std.StringHashMapUnmanaged(usize) = .empty;
            entry_loop: for (entries, 0..) |entry, i| {
                var values: std.ArrayList(Val) = .empty;
                for (paths) |p| try values.append(self.a, descendantValue(entry, p) orelse continue :entry_loop);
                const token = try jv.jsonToken(self.a, .{ .array = values.items });
                if (seen.get(token)) |first| {
                    var shown: std.ArrayList([]const u8) = .empty;
                    for (paths, values.items) |p, v| try shown.append(self.a, try std.fmt.allocPrint(self.a, "{s}='{s}'", .{ p, try self.uniqueDisplay(v) }));
                    try self.add(path, pointer, "unique", try std.fmt.allocPrint(self.a, "Unique constraint violated in list '{s}': {s} (entries at index {d} and {d})", .{ s.name, try std.mem.join(self.a, ", ", shown.items), first, i }));
                    break;
                }
                try seen.put(self.a, token, i);
            }
        }
    }
};

var empty_object: Object = .empty;
