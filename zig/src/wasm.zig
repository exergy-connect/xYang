//! Minimal, single-model Wasm ABI. No filesystem, WASI, or JavaScript imports.
//! Input buffers belong to the caller; model and per-call allocations are separate.
const std = @import("std");
const xyang = @import("root.zig");

const backing = std.heap.wasm_allocator;
var model_arena = std.heap.ArenaAllocator.init(backing);
var call_arena = std.heap.ArenaAllocator.init(backing);
var model: ?*xyang.Module = null;
var result: []const u8 = "";

export fn xyang_alloc(len: usize) usize {
    if (len == 0) return 0;
    const buf = backing.alloc(u8, len) catch return 0;
    return @intFromPtr(buf.ptr);
}

export fn xyang_free(ptr: usize, len: usize) void {
    if (ptr == 0 or len == 0) return;
    backing.free(input(ptr, len));
}

fn input(ptr: usize, len: usize) []u8 {
    return @as([*]u8, @ptrFromInt(ptr))[0..len];
}

fn beginCall() void {
    result = "";
    _ = call_arena.reset(.free_all);
}

fn fail(code: []const u8, message: []const u8) u32 {
    result = std.json.Stringify.valueAlloc(call_arena.allocator(), .{
        .err = code,
        .message = message,
    }, .{}) catch "{\"err\":\"OutOfMemory\",\"message\":\"Out of memory\"}";
    return 1;
}

/// Load a canonical .yang.json. A failed replacement preserves the previous model.
export fn xyang_load_model(ptr: usize, len: usize) u32 {
    beginCall();
    var candidate = std.heap.ArenaAllocator.init(backing);
    defer candidate.deinit();
    const a = candidate.allocator();
    var message: []const u8 = "";
    // The shared JSON parser can borrow strings from its source buffer.
    const owned = a.dupe(u8, input(ptr, len)) catch return fail("OutOfMemory", "Out of memory");
    const data = xyang.json_value.parse(a, owned, &message) catch |err|
        return fail(@errorName(err), message);
    const loaded = xyang.json_parser.parseJsonSchema(a, data, &message) catch |err|
        return fail(@errorName(err), message);
    std.mem.swap(std.heap.ArenaAllocator, &model_arena, &candidate);
    model = loaded;
    result = "{\"loaded\":true}";
    return 0;
}

/// Validate RFC 7951 JSON. Invalid instances return 0 with valid:false;
/// malformed input, missing models, and unsupported operations return 1.
export fn xyang_validate(ptr: usize, len: usize) u32 {
    beginCall();
    return validate(ptr, len, .{});
}

/// Options are a JSON object containing rpc/action/direction strings and/or
/// context as JSON text. Keep the original two-argument ABI for document callers.
export fn xyang_validate_with_options(ptr: usize, len: usize, options_ptr: usize, options_len: usize) u32 {
    beginCall();
    var message: []const u8 = "";
    const parsed = xyang.json_value.parse(call_arena.allocator(), input(options_ptr, options_len), &message) catch |err|
        return fail(@errorName(err), message);
    if (parsed != .object) return fail("Usage", "Validation options must be a JSON object");
    var options: xyang.yang_validator.Options = .{};
    for (parsed.object.keys(), parsed.object.values()) |key, value| {
        if (std.mem.eql(u8, key, "context")) {
            if (value != .string) return fail("Usage", "context must be JSON text");
            options.context = xyang.json_value.parse(call_arena.allocator(), value.string, &message) catch |err|
                return fail(@errorName(err), message);
        } else if (std.mem.eql(u8, key, "rpc")) {
            if (value != .string) return fail("Usage", "rpc must be a string");
            options.rpc = value.string;
        } else if (std.mem.eql(u8, key, "action")) {
            if (value != .string) return fail("Usage", "action must be a string");
            options.action = value.string;
        } else if (std.mem.eql(u8, key, "direction")) {
            if (value != .string) return fail("Usage", "direction must be a string");
            options.direction = value.string;
        } else {
            return fail("Usage", "Unknown validation option");
        }
    }
    return validate(ptr, len, options);
}

fn validate(ptr: usize, len: usize, options: xyang.yang_validator.Options) u32 {
    const m = model orelse return fail("NoModel", "Load a native JSON model first");
    const a = call_arena.allocator();
    var message: []const u8 = "";
    const data = xyang.json_value.parse(a, input(ptr, len), &message) catch |err|
        return fail(@errorName(err), message);
    var validator = xyang.YangValidator.init(a, m);
    const validated = validator.validate(data, options) catch |err|
        return fail(@errorName(err), validator.unsupported orelse validator.usage orelse @errorName(err));
    result = std.json.Stringify.valueAlloc(a, .{
        .valid = validated.valid(),
        .errors = validated.errors,
        .warnings = validated.warnings,
    }, .{}) catch return fail("OutOfMemory", "Out of memory");
    return 0;
}

export fn xyang_result_ptr() usize {
    return @intFromPtr(result.ptr);
}

export fn xyang_result_len() usize {
    return result.len;
}

/// Release the model and last result; caller-owned input buffers are unaffected.
export fn xyang_reset() void {
    beginCall();
    model = null;
    _ = model_arena.reset(.free_all);
}
