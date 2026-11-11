//! Python `repr()` of a `str`, so error messages quote values exactly like the Python CLI.

const std = @import("std");

pub const Repr = struct {
    s: []const u8,

    pub fn format(self: Repr, w: *std.Io.Writer) std.Io.Writer.Error!void {
        const has_single = std.mem.indexOfScalar(u8, self.s, '\'') != null;
        const has_double = std.mem.indexOfScalar(u8, self.s, '"') != null;
        const quote: u8 = if (has_single and !has_double) '"' else '\'';
        try w.writeByte(quote);
        var i: usize = 0;
        while (i < self.s.len) {
            const c = self.s[i];
            if (c < 0x80) {
                switch (c) {
                    '\\' => try w.writeAll("\\\\"),
                    '\n' => try w.writeAll("\\n"),
                    '\r' => try w.writeAll("\\r"),
                    '\t' => try w.writeAll("\\t"),
                    else => {
                        if (c == quote) {
                            try w.writeByte('\\');
                            try w.writeByte(c);
                        } else if (c < 0x20 or c == 0x7f) {
                            try w.print("\\x{x:0>2}", .{c});
                        } else {
                            try w.writeByte(c);
                        }
                    },
                }
                i += 1;
                continue;
            }
            const len = std.unicode.utf8ByteSequenceLength(c) catch 1;
            if (i + len > self.s.len) {
                try w.writeAll(self.s[i..]);
                break;
            }
            const cp = std.unicode.utf8Decode(self.s[i .. i + len]) catch {
                try w.writeByte(c);
                i += 1;
                continue;
            };
            if (!isPrintable(cp)) {
                if (cp <= 0xff) {
                    try w.print("\\x{x:0>2}", .{cp});
                } else if (cp <= 0xffff) {
                    try w.print("\\u{x:0>4}", .{cp});
                } else {
                    try w.print("\\U{x:0>8}", .{cp});
                }
            } else {
                try w.writeAll(self.s[i .. i + len]);
            }
            i += len;
        }
        try w.writeByte(quote);
    }
};

/// Non-ASCII code points Python's `str.isprintable()` rejects that occur in practice
/// (C1 controls, separators, format characters).
fn isPrintable(cp: u21) bool {
    return switch (cp) {
        0x80...0xa0, 0xad, 0x1680, 0x2000...0x200f, 0x2028...0x202f, 0x205f...0x206f, 0x3000, 0xfeff => false,
        else => true,
    };
}

pub fn repr(s: []const u8) Repr {
    return .{ .s = s };
}

test "repr quoting follows Python" {
    var buf: [64]u8 = undefined;
    try std.testing.expectEqualStrings("'yes'", try std.fmt.bufPrint(&buf, "{f}", .{repr("yes")}));
    try std.testing.expectEqualStrings("\"it's\"", try std.fmt.bufPrint(&buf, "{f}", .{repr("it's")}));
    try std.testing.expectEqualStrings("'a\\'b\"'", try std.fmt.bufPrint(&buf, "{f}", .{repr("a'b\"")}));
    try std.testing.expectEqualStrings("'a\\nb\\\\'", try std.fmt.bufPrint(&buf, "{f}", .{repr("a\nb\\")}));
    try std.testing.expectEqualStrings("''", try std.fmt.bufPrint(&buf, "{f}", .{repr("")}));
}
