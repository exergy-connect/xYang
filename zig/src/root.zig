//! xYang in Zig: parse YANG modules and resolve them (phases 1 and 2 of #165).

pub const ast = @import("ast.zig");
pub const errors = @import("errors.zig");
pub const pyfmt = @import("pyfmt.zig");
pub const module = @import("module.zig");
pub const Module = module.Module;
pub const dispatch_registry = @import("parser/dispatch_registry.zig");
pub const tokenizer = @import("parser/tokenizer.zig");
pub const yang_parser = @import("parser/yang_parser.zig");
pub const identity_graph = @import("identity_graph.zig");
pub const if_feature_eval = @import("if_feature_eval.zig");
pub const capabilities = @import("ext/capabilities.zig");
pub const schema_dump = @import("schema_dump.zig");

pub const Diagnostic = errors.Diagnostic;
pub const Loader = yang_parser.Loader;
pub const parseFile = yang_parser.parseFile;
pub const parseString = yang_parser.parseString;

test {
    _ = @import("ast.zig");
    _ = @import("errors.zig");
    _ = @import("pyfmt.zig");
    _ = @import("module.zig");
    _ = @import("parser/dispatch_registry.zig");
    _ = @import("parser/tokenizer.zig");
    _ = @import("parser/token_stream.zig");
    _ = @import("parser/yang_strings.zig");
    _ = @import("parser/statement_parsers.zig");
    _ = @import("parser/yang_parser.zig");
    _ = @import("refine_expand.zig");
    _ = @import("uses_expand.zig");
    _ = @import("augment_expand.zig");
    _ = @import("semantic_validate.zig");
    _ = @import("ext/capabilities.zig");
    _ = @import("identity_graph.zig");
    _ = @import("if_feature_eval.zig");
}
