//! Subprocess harness: turn a Debug assertion into an observable exit status.
const std = @import("std");
const xyang = @import("xyang");

pub const panic = std.debug.FullPanic(assertionFailed);
fn assertionFailed(_: []const u8, _: ?usize) noreturn {
    std.process.exit(42);
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var diag: xyang.Diagnostic = .{};
    const module = try xyang.parseString(a, "module m { namespace 'urn:m'; prefix m; leaf x { type string; } }", "test.yang", &diag);
    var message: []const u8 = "";
    const data = try xyang.json_value.parse(a, "{\"m:x\":\"é\"}", &message);
    var validator = xyang.YangValidator.init(a, module);
    _ = try validator.validate(data, .{ .assume_ascii = true });
}
