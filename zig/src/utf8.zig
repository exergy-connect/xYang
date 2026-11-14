//! Codepoint decoding for a slice whose length the caller already took from
//! `std.unicode.utf8ByteSequenceLength`.

const std = @import("std");
const unicode = std.unicode;

pub const DecodeError = error{
    Utf8ExpectedContinuation,
    Utf8OverlongEncoding,
    Utf8EncodesSurrogateHalf,
    Utf8CodepointTooLarge,
};

/// `bytes.len` must be 1 to 4. A single byte is returned as is.
pub fn decode(bytes: []const u8) DecodeError!u21 {
    return switch (bytes.len) {
        1 => bytes[0],
        2 => unicode.utf8Decode2(bytes[0..2].*),
        3 => unicode.utf8Decode3(bytes[0..3].*),
        4 => unicode.utf8Decode4(bytes[0..4].*),
        else => unreachable,
    };
}

test "decode" {
    try std.testing.expectEqual(@as(u21, 'a'), try decode("a"));
    try std.testing.expectEqual(@as(u21, 0xe9), try decode("\xc3\xa9"));
    try std.testing.expectEqual(@as(u21, 0x20ac), try decode("\xe2\x82\xac"));
    try std.testing.expectEqual(@as(u21, 0x1f600), try decode("\xf0\x9f\x98\x80"));
    try std.testing.expectError(error.Utf8ExpectedContinuation, decode("\xc3a"));
}
