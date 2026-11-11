//! RFC 7950 6.2 quoted string decoding (mirrors `src/xyang/parser/yang_strings.py`).

const std = @import("std");

/// Decode the inner text of a single- or double-quoted string. Returns `content` itself
/// when it has no backslash; otherwise a new slice allocated with `gpa`.
pub fn unescapeQuoted(gpa: std.mem.Allocator, content: []const u8, quote: u8) ![]const u8 {
    std.debug.assert(quote == '"' or quote == '\'');
    if (std.mem.indexOfScalar(u8, content, '\\') == null) return content;

    var out: std.ArrayList(u8) = .empty;
    errdefer out.deinit(gpa);
    var i: usize = 0;
    const n = content.len;
    while (i < n) {
        const backslash = std.mem.indexOfScalarPos(u8, content, i, '\\') orelse {
            try out.appendSlice(gpa, content[i..]);
            break;
        };
        try out.appendSlice(gpa, content[i..backslash]);
        i = backslash;
        if (i + 1 >= n) {
            try out.append(gpa, '\\');
            i += 1;
            continue;
        }
        const nxt = content[i + 1];
        switch (nxt) {
            '\\' => {
                try out.append(gpa, '\\');
                i += 2;
            },
            'n' => {
                try out.append(gpa, '\n');
                i += 2;
            },
            't' => {
                try out.append(gpa, '\t');
                i += 2;
            },
            '\r', '\n' => {
                i += 2;
                if (nxt == '\r' and i < n and content[i] == '\n') i += 1;
                while (i < n and (content[i] == ' ' or content[i] == '\t')) i += 1;
            },
            else => {
                if (nxt == quote) {
                    try out.append(gpa, quote);
                    i += 2;
                } else {
                    // Unrecognized escape: keep the backslash; the next character is copied as-is.
                    try out.append(gpa, '\\');
                    i += 1;
                }
            },
        }
    }
    return out.toOwnedSlice(gpa);
}

test "escapes" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    try std.testing.expectEqualStrings("a\"b", try unescapeQuoted(a, "a\\\"b", '"'));
    try std.testing.expectEqualStrings("a\\\"b", try unescapeQuoted(a, "a\\\"b", '\''));
    try std.testing.expectEqualStrings("x\ny\t\\", try unescapeQuoted(a, "x\\ny\\t\\\\", '"'));
    try std.testing.expectEqualStrings("\\d+", try unescapeQuoted(a, "\\d+", '\''));
    try std.testing.expectEqualStrings("ab", try unescapeQuoted(a, "a\\\n   b", '"'));
    try std.testing.expectEqualStrings("end\\", try unescapeQuoted(a, "end\\", '"'));
}
