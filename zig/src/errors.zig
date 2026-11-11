//! Load errors with the same text as Python's `YangSyntaxError` / `YangSemanticError`
//! (`src/xyang/errors.py`), plus `unsupported` for constructs this port does not handle yet.

const std = @import("std");

pub const Kind = enum {
    /// `YangSyntaxError`: printed as `filename: line: message` when the location is known.
    syntax,
    /// `YangSemanticError`: printed as the message alone.
    semantic,
    /// A construct the Zig port cannot handle yet. Never coerced or dropped.
    unsupported,
    /// The file could not be read (missing, unreadable, not UTF-8).
    io,
};

pub const Error = error{ YangLoad, OutOfMemory };

pub const Diagnostic = struct {
    kind: Kind = .syntax,
    message: []const u8 = "",
    line: ?usize = null,
    filename: ?[]const u8 = null,

    /// Python's `str(exc)`: `filename: line: message`, each part present only when known.
    pub fn format(self: Diagnostic, w: *std.Io.Writer) std.Io.Writer.Error!void {
        if (self.kind == .syntax or self.kind == .unsupported) {
            if (self.filename) |f| try w.print("{s}: ", .{f});
            if (self.line) |l| try w.print("{d}: ", .{l});
        }
        try w.writeAll(self.message);
    }
};

/// Where module resolution reports: one failure (the `Diagnostic`) and the warnings Python
/// logs with `logger.warning` (printed to stderr by the CLI, in order).
pub const Reporter = struct {
    arena: std.mem.Allocator,
    diag: *Diagnostic,
    warnings: std.ArrayList([]const u8) = .empty,

    /// A failure with no source location: `YangSemanticError(msg)` (`.semantic`) or
    /// `YangSyntaxError(msg)` (`.syntax`), which print the same text.
    pub fn fail(self: *Reporter, kind: Kind, comptime fmt: []const u8, args: anytype) Error {
        const msg = try std.fmt.allocPrint(self.arena, fmt, args);
        self.diag.* = .{ .kind = kind, .message = msg };
        return error.YangLoad;
    }

    pub fn warn(self: *Reporter, comptime fmt: []const u8, args: anytype) Error!void {
        try self.warnings.append(self.arena, try std.fmt.allocPrint(self.arena, fmt, args));
    }
};

test "headline format matches YangSyntaxError" {
    var buf: [128]u8 = undefined;
    const d = Diagnostic{ .message = "boom", .line = 8, .filename = "/m.yang" };
    const s = try std.fmt.bufPrint(&buf, "{f}", .{d});
    try std.testing.expectEqualStrings("/m.yang: 8: boom", s);
    const sem = Diagnostic{ .kind = .semantic, .message = "bad", .line = 3, .filename = "/m.yang" };
    try std.testing.expectEqualStrings("bad", try std.fmt.bufPrint(&buf, "{f}", .{sem}));
}
