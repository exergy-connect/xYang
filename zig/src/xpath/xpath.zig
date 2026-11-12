//! YANG XPath with schema-aware nodes (mirrors `src/xyang/xpath/__init__.py`).
//!
//! `Context` (current, root) is fixed for one expression; `Node` (data, schema, parent)
//! is the cursor created on every step; `current()` returns the validation anchor.
//! `compile` and `compilePath` parse and bind an expression when its module loads.

const std = @import("std");
const Module = @import("../module.zig").Module;

pub const ast = @import("ast.zig");
pub const tokens = @import("tokens.zig");
pub const tokenizer = @import("tokenizer.zig");
pub const parser = @import("parser.zig");
pub const node = @import("node.zig");
pub const utils = @import("utils.zig");
pub const schema_nav = @import("schema_nav.zig");
pub const functions = @import("functions.zig");
pub const evaluator = @import("evaluator.zig");

pub const Expr = ast.Expr;
pub const Path = ast.Path;
pub const Node = node.Node;
pub const Context = node.Context;
pub const Value = node.Value;
pub const Schema = node.Schema;
pub const Evaluator = evaluator.Evaluator;
pub const Parser = parser.Parser;

/// Why an expression did not compile, with Python's `str(exc)`.
pub const Failure = struct {
    /// `unsupported`: a construct this port cannot represent yet.
    unsupported: bool = false,
    message: []const u8 = "",
};

pub const CompileError = error{ OutOfMemory, Invalid };

fn resolvePrefix(ctx: *anyopaque, prefix: []const u8) ?[]const u8 {
    const m: *Module = @ptrCast(@alignCast(ctx));
    return m.resolvePrefixToModuleName(prefix);
}

fn bind(a: std.mem.Allocator, e: *Expr, module: *Module, expression: []const u8, failure: *Failure) CompileError!void {
    parser.bindPrefixes(a, e, .{ .ctx = module, .resolve = resolvePrefix }, expression, &failure.message) catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        error.UnknownPrefix => return error.Invalid,
    };
}

fn parseFailure(err: parser.Error, p: *const Parser, failure: *Failure) CompileError {
    failure.* = .{ .unsupported = err == error.UnsupportedNumber, .message = p.message };
    return if (err == error.OutOfMemory) error.OutOfMemory else error.Invalid;
}

/// `YangParsedXPathBase.__post_init__` and `bind_prefixes`: a `must` or `when`
/// expression, bound to the prefixes of `module`. Empty text has no AST.
pub fn compile(a: std.mem.Allocator, expression: []const u8, module: *Module, failure: *Failure) CompileError!?*Expr {
    if (expression.len == 0) return null;
    var p = try Parser.init(a, expression);
    const e = p.parse() catch |err| return parseFailure(err, &p, failure);
    try bind(a, e, module, expression, failure);
    return e;
}

/// A leafref `path`: `parse_path()` then `bind_xpath_prefixes`.
pub fn compilePath(a: std.mem.Allocator, path: []const u8, module: *Module, failure: *Failure) CompileError!*Expr {
    var p = try Parser.init(a, path);
    const e = p.parsePath(true) catch |err| return parseFailure(err, &p, failure);
    try bind(a, e, module, path, failure);
    return e;
}

test {
    _ = tokenizer;
    _ = parser;
    _ = utils;
    _ = @import("pychars.zig");
}
