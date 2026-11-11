//! xYang in Zig: parse YANG modules (phase 1 of #165).

pub const ast = @import("ast.zig");
pub const errors = @import("errors.zig");
pub const pyfmt = @import("pyfmt.zig");
pub const Module = @import("module.zig").Module;
pub const dispatch_registry = @import("parser/dispatch_registry.zig");
pub const tokenizer = @import("parser/tokenizer.zig");
pub const yang_parser = @import("parser/yang_parser.zig");

pub const Diagnostic = errors.Diagnostic;
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
}
