//! Python `str` character classes (`isalpha`, `isdigit`, `isalnum`, `isspace`) on code
//! points, from the Unicode general categories Python 15.0.0 uses.

const std = @import("std");
const uc = @import("../unicode_categories.zig");

fn categoryIndex(cp: u21) usize {
    var lo: usize = 0;
    var hi: usize = uc.RUNS.len;
    while (hi - lo > 1) {
        const mid = (lo + hi) / 2;
        if ((uc.RUNS[mid] >> 5) <= cp) lo = mid else hi = mid;
    }
    return lo;
}

/// Two-letter general category of `cp` (`Lu`, `Nd`, ...).
pub fn category(cp: u21) []const u8 {
    return uc.CATEGORIES[uc.RUNS[categoryIndex(cp)] & 31];
}

fn runStart(cp: u21) u21 {
    return @intCast(uc.RUNS[categoryIndex(cp)] >> 5);
}

pub fn isAlpha(cp: u21) bool {
    if (cp < 0x80) return std.ascii.isAlphabetic(@intCast(cp));
    return category(cp)[0] == 'L';
}

/// Superscript and subscript digits: Numeric_Type=Digit outside `Nd`.
fn isOtherDigit(cp: u21) bool {
    return switch (cp) {
        0xb2, 0xb3, 0xb9, 0x2070, 0x2074...0x2079, 0x2080...0x2089 => true,
        else => false,
    };
}

pub fn isDigit(cp: u21) bool {
    if (cp < 0x80) return std.ascii.isDigit(@intCast(cp));
    return std.mem.eql(u8, category(cp), "Nd") or isOtherDigit(cp);
}

/// The value of a decimal digit (`Nd`), as `int()` reads it, or null.
pub fn decimalValue(cp: u21) ?u8 {
    if (cp < 0x80) return if (std.ascii.isDigit(@intCast(cp))) @intCast(cp - '0') else null;
    if (!std.mem.eql(u8, category(cp), "Nd")) return null;
    return @intCast((cp - runStart(cp)) % 10);
}

pub fn isAlnum(cp: u21) bool {
    if (cp < 0x80) return std.ascii.isAlphanumeric(@intCast(cp));
    const c = category(cp)[0];
    return c == 'L' or c == 'N';
}

pub fn isSpace(cp: u21) bool {
    return switch (cp) {
        0x09...0x0d, 0x1c...0x20, 0x85 => true,
        else => cp >= 0x80 and category(cp)[0] == 'Z',
    };
}

/// `str.strip()`.
pub fn strip(s: []const u8) []const u8 {
    var start: usize = 0;
    while (start < s.len) {
        const n = std.unicode.utf8ByteSequenceLength(s[start]) catch break;
        if (start + n > s.len) break;
        const cp = std.unicode.utf8Decode(s[start .. start + n]) catch break;
        if (!isSpace(cp)) break;
        start += n;
    }
    var end = s.len;
    while (end > start) {
        var b = end - 1;
        while (b > start and (s[b] & 0xc0) == 0x80) b -= 1;
        const cp = std.unicode.utf8Decode(s[b..end]) catch break;
        if (!isSpace(cp)) break;
        end = b;
    }
    return s[start..end];
}

test "python character classes" {
    try std.testing.expect(isAlpha('a') and isAlpha(0xe9) and !isAlpha('1'));
    try std.testing.expect(isDigit('7') and isDigit(0x0663) and isDigit(0xb2) and !isDigit('x'));
    try std.testing.expectEqual(@as(?u8, 3), decimalValue(0x0663));
    try std.testing.expect(isSpace(' ') and isSpace(0xa0) and !isSpace('a'));
    try std.testing.expectEqualStrings("a b", strip(" \u{a0}a b\t"));
}
