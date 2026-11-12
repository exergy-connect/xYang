//! Instance JSON as Python's `json.loads` builds it, and the Python text of each value
//! (`str`, `repr`, type names), so validation messages read like the Python CLI's.
//!
//! Integers are exact (`i128`), floats are `f64`, and `decimal` is a Python `Decimal`
//! (decimal64 values after RFC 7951 decoding). Objects keep member order; a repeated
//! member keeps its first position and takes the last value, like a Python `dict`.

const std = @import("std");
const pyfmt = @import("pyfmt.zig");

const Allocator = std.mem.Allocator;

pub const Object = std.StringArrayHashMapUnmanaged(Val);

/// A Python `Decimal`: `(-1)**negative * coefficient * 10**exponent`. `digits` has no
/// leading zeros ("0" for zero).
pub const Decimal = struct {
    negative: bool,
    digits: []const u8,
    exponent: i32,

    /// `Decimal(text)` for `-?\d+(\.\d+)?` or a Python float `repr`.
    pub fn parse(a: Allocator, text: []const u8) error{ OutOfMemory, InvalidDecimal }!Decimal {
        var s = text;
        var negative = false;
        if (s.len > 0 and (s[0] == '-' or s[0] == '+')) {
            negative = s[0] == '-';
            s = s[1..];
        }
        var exponent: i32 = 0;
        if (std.mem.indexOfAny(u8, s, "eE")) |e| {
            exponent = std.fmt.parseInt(i32, s[e + 1 ..], 10) catch return error.InvalidDecimal;
            s = s[0..e];
        }
        var coeff: std.ArrayList(u8) = .empty;
        var seen_dot = false;
        for (s) |c| {
            if (c == '.') {
                if (seen_dot) return error.InvalidDecimal;
                seen_dot = true;
                continue;
            }
            if (c < '0' or c > '9') return error.InvalidDecimal;
            if (seen_dot) exponent -= 1;
            try coeff.append(a, c);
        }
        if (coeff.items.len == 0) return error.InvalidDecimal;
        var digits = std.mem.trimStart(u8, coeff.items, "0");
        if (digits.len == 0) digits = "0";
        return .{ .negative = negative, .digits = digits, .exponent = exponent };
    }

    pub fn fromInt(a: Allocator, n: i128) error{OutOfMemory}!Decimal {
        const mag = try std.fmt.allocPrint(a, "{d}", .{@abs(n)});
        return .{ .negative = n < 0, .digits = mag, .exponent = 0 };
    }

    /// `str(Decimal)` (scientific notation off the `-6 < adjusted` window).
    pub fn format(self: Decimal, w: *std.Io.Writer) std.Io.Writer.Error!void {
        if (self.negative) try w.writeByte('-');
        const n: i64 = @intCast(self.digits.len);
        const leftdigits: i64 = self.exponent + n;
        const dotplace: i64 = if (self.exponent <= 0 and leftdigits > -6) leftdigits else 1;
        if (dotplace <= 0) {
            try w.writeAll("0.");
            try w.splatByteAll('0', @intCast(-dotplace));
            try w.writeAll(self.digits);
        } else if (dotplace >= n) {
            try w.writeAll(self.digits);
            try w.splatByteAll('0', @intCast(dotplace - n));
        } else {
            try w.writeAll(self.digits[0..@intCast(dotplace)]);
            try w.writeByte('.');
            try w.writeAll(self.digits[@intCast(dotplace)..]);
        }
        if (leftdigits != dotplace) try w.print("E{s}{d}", .{ if (leftdigits - dotplace >= 0) "+" else "-", @abs(leftdigits - dotplace) });
    }

    /// `float(Decimal)`.
    pub fn toFloat(self: Decimal) f64 {
        var buf: [512]u8 = undefined;
        const text = std.fmt.bufPrint(&buf, "{s}{s}e{d}", .{ if (self.negative) "-" else "", self.digits, self.exponent }) catch return std.math.nan(f64);
        return std.fmt.parseFloat(f64, text) catch std.math.nan(f64);
    }

    /// Exact numeric equality (`Decimal == Decimal`).
    pub fn eql(x: Decimal, y: Decimal) bool {
        const xz = std.mem.eql(u8, x.digits, "0");
        const yz = std.mem.eql(u8, y.digits, "0");
        if (xz or yz) return xz and yz;
        if (x.negative != y.negative) return false;
        const xd = std.mem.trimEnd(u8, x.digits, "0");
        const yd = std.mem.trimEnd(u8, y.digits, "0");
        const xe = x.exponent + @as(i32, @intCast(x.digits.len - xd.len));
        const ye = y.exponent + @as(i32, @intCast(y.digits.len - yd.len));
        return xe == ye and std.mem.eql(u8, xd, yd);
    }

    /// The integer value when the decimal is integral and fits.
    pub fn toInt(self: Decimal) ?i128 {
        const trimmed = std.mem.trimEnd(u8, self.digits, "0");
        const zeros: i32 = @intCast(self.digits.len - trimmed.len);
        if (self.exponent + zeros < 0) return null;
        var v: i128 = std.fmt.parseInt(i128, if (trimmed.len == 0) "0" else trimmed, 10) catch return null;
        var e = self.exponent + zeros;
        while (e > 0) : (e -= 1) v = std.math.mul(i128, v, 10) catch return null;
        return if (self.negative) -v else v;
    }
};

pub const Val = union(enum) {
    null,
    bool: bool,
    int: i128,
    float: f64,
    decimal: Decimal,
    string: []const u8,
    array: []Val,
    object: *Object,

    pub fn isNull(v: Val) bool {
        return v == .null;
    }
};

pub const LoadError = error{ OutOfMemory, InvalidJson, IntegerTooLarge };

/// `json.loads`. On failure `message` is set.
pub fn parse(a: Allocator, text: []const u8, message: *[]const u8) LoadError!Val {
    const parsed = std.json.parseFromSliceLeaky(std.json.Value, a, text, .{
        .parse_numbers = false,
        .duplicate_field_behavior = .use_last,
    }) catch |err| {
        message.* = try std.fmt.allocPrint(a, "invalid JSON: {s}", .{@errorName(err)});
        return error.InvalidJson;
    };
    return fromStd(a, parsed, message);
}

fn fromStd(a: Allocator, v: std.json.Value, message: *[]const u8) LoadError!Val {
    return switch (v) {
        .null => .null,
        .bool => |b| .{ .bool = b },
        .integer => |i| .{ .int = i },
        .float => |f| .{ .float = f },
        .number_string => |s| try number(a, s, message),
        .string => |s| .{ .string = s },
        .array => |arr| blk: {
            const out = try a.alloc(Val, arr.items.len);
            for (arr.items, 0..) |item, i| out[i] = try fromStd(a, item, message);
            break :blk .{ .array = out };
        },
        .object => |obj| blk: {
            const out = try a.create(Object);
            out.* = .empty;
            var it = obj.iterator();
            while (it.next()) |e| try out.put(a, e.key_ptr.*, try fromStd(a, e.value_ptr.*, message));
            break :blk .{ .object = out };
        },
    };
}

fn number(a: Allocator, s: []const u8, message: *[]const u8) LoadError!Val {
    if (std.json.isNumberFormattedLikeAnInteger(s)) {
        const n = std.fmt.parseInt(i128, s, 10) catch {
            message.* = try std.fmt.allocPrint(a, "xyang-zig cannot represent the JSON integer {s}: it is outside the 128-bit range", .{s});
            return error.IntegerTooLarge;
        };
        return .{ .int = n };
    }
    return .{ .float = std.fmt.parseFloat(f64, s) catch std.math.inf(f64) };
}

/// Python `repr(float)` (and `str(float)`).
pub const FloatRepr = struct {
    f: f64,

    pub fn format(self: FloatRepr, w: *std.Io.Writer) std.Io.Writer.Error!void {
        const f = self.f;
        if (std.math.isNan(f)) return w.writeAll("nan");
        if (std.math.isInf(f)) return w.writeAll(if (f < 0) "-inf" else "inf");
        var buf: [64]u8 = undefined;
        const sci = std.fmt.float.render(&buf, @abs(f), .{ .mode = .scientific }) catch return w.writeAll("?");
        const e_at = std.mem.indexOfScalar(u8, sci, 'e').?;
        const exp = std.fmt.parseInt(i32, sci[e_at + 1 ..], 10) catch 0;
        var digits_buf: [32]u8 = undefined;
        var nd: usize = 0;
        for (sci[0..e_at]) |c| {
            if (c != '.') {
                digits_buf[nd] = c;
                nd += 1;
            }
        }
        var digits: []const u8 = digits_buf[0..nd];
        digits = std.mem.trimEnd(u8, digits, "0");
        if (digits.len == 0) digits = "0";
        if (std.math.signbit(f)) try w.writeByte('-');
        if (exp >= -4 and exp < 16) {
            const point: i32 = exp + 1;
            if (point <= 0) {
                try w.writeAll("0.");
                try w.splatByteAll('0', @intCast(-point));
                try w.writeAll(digits);
            } else if (point >= digits.len) {
                try w.writeAll(digits);
                try w.splatByteAll('0', @intCast(point - @as(i32, @intCast(digits.len))));
                try w.writeAll(".0");
            } else {
                try w.writeAll(digits[0..@intCast(point)]);
                try w.writeByte('.');
                try w.writeAll(digits[@intCast(point)..]);
            }
            return;
        }
        try w.writeByte(digits[0]);
        if (digits.len > 1) {
            try w.writeByte('.');
            try w.writeAll(digits[1..]);
        }
        try w.print("e{s}{d:0>2}", .{ if (exp < 0) "-" else "+", @abs(exp) });
    }
};

pub fn floatRepr(f: f64) FloatRepr {
    return .{ .f = f };
}

/// Python `str(value)`.
pub const PyStr = struct {
    v: Val,
    pub fn format(self: PyStr, w: *std.Io.Writer) std.Io.Writer.Error!void {
        switch (self.v) {
            .string => |s| try w.writeAll(s),
            .decimal => |d| try d.format(w),
            else => try writeRepr(w, self.v),
        }
    }
};

/// Python `repr(value)`.
pub const PyRepr = struct {
    v: Val,
    pub fn format(self: PyRepr, w: *std.Io.Writer) std.Io.Writer.Error!void {
        try writeRepr(w, self.v);
    }
};

pub fn pyStr(v: Val) PyStr {
    return .{ .v = v };
}

pub fn pyRepr(v: Val) PyRepr {
    return .{ .v = v };
}

fn writeRepr(w: *std.Io.Writer, v: Val) std.Io.Writer.Error!void {
    switch (v) {
        .null => try w.writeAll("None"),
        .bool => |b| try w.writeAll(if (b) "True" else "False"),
        .int => |i| try w.print("{d}", .{i}),
        .float => |f| try floatRepr(f).format(w),
        .decimal => |d| {
            try w.writeAll("Decimal('");
            try d.format(w);
            try w.writeAll("')");
        },
        .string => |s| try pyfmt.repr(s).format(w),
        .array => |items| {
            try w.writeByte('[');
            for (items, 0..) |item, i| {
                if (i > 0) try w.writeAll(", ");
                try writeRepr(w, item);
            }
            try w.writeByte(']');
        },
        .object => |obj| {
            try w.writeByte('{');
            var it = obj.iterator();
            var i: usize = 0;
            while (it.next()) |e| : (i += 1) {
                if (i > 0) try w.writeAll(", ");
                try pyfmt.repr(e.key_ptr.*).format(w);
                try w.writeAll(": ");
                try writeRepr(w, e.value_ptr.*);
            }
            try w.writeByte('}');
        },
    }
}

/// `type(value).__name__`.
pub fn typeName(v: Val) []const u8 {
    return switch (v) {
        .null => "NoneType",
        .bool => "bool",
        .int => "int",
        .float => "float",
        .decimal => "Decimal",
        .string => "str",
        .array => "list",
        .object => "dict",
    };
}

/// `_json_type_name`: the RFC 8259 type name (`number`, `boolean`, ...).
pub fn jsonTypeName(v: Val) []const u8 {
    return switch (v) {
        .null => "null",
        .bool => "boolean",
        .int, .float => "number",
        .string => "string",
        .array => "array",
        .object => "object",
        .decimal => "Decimal",
    };
}

/// Python numeric value of a number (bools are ints), for `==` across types.
fn numeric(v: Val) ?f64 {
    return switch (v) {
        .bool => |b| if (b) 1 else 0,
        .int => |i| @floatFromInt(i),
        .float => |f| f,
        .decimal => |d| d.toFloat(),
        else => null,
    };
}

/// Python `==` on JSON values (`1 == 1.0 == True`, `Decimal('1.0') == 1`).
pub fn pyEql(x: Val, y: Val) bool {
    switch (x) {
        .null => return y == .null,
        .string => |s| return y == .string and std.mem.eql(u8, s, y.string),
        .array => |xs| {
            if (y != .array or y.array.len != xs.len) return false;
            for (xs, y.array) |p, q| if (!pyEql(p, q)) return false;
            return true;
        },
        .object => |xo| {
            if (y != .object or y.object.count() != xo.count()) return false;
            var it = xo.iterator();
            while (it.next()) |e| {
                const other = y.object.get(e.key_ptr.*) orelse return false;
                if (!pyEql(e.value_ptr.*, other)) return false;
            }
            return true;
        },
        else => {},
    }
    if (x == .int and y == .int) return x.int == y.int;
    if (x == .decimal and y == .decimal) return Decimal.eql(x.decimal, y.decimal);
    if (x == .int and y == .bool) return x.int == @intFromBool(y.bool);
    if (x == .bool and y == .int) return y.int == @intFromBool(x.bool);
    if (x == .bool and y == .bool) return x.bool == y.bool;
    const p = numeric(x) orelse return false;
    const q = numeric(y) orelse return false;
    return p == q;
}

/// `json.dumps(value, sort_keys=True, default=str)` (a `Decimal` dumps as its `str`).
pub fn jsonToken(a: Allocator, v: Val) error{OutOfMemory}![]const u8 {
    var out: std.Io.Writer.Allocating = .init(a);
    writeJsonToken(a, &out.writer, v) catch return error.OutOfMemory;
    return out.written();
}

fn writeJsonToken(a: Allocator, w: *std.Io.Writer, v: Val) (std.Io.Writer.Error || error{OutOfMemory})!void {
    switch (v) {
        .null => try w.writeAll("null"),
        .bool => |b| try w.writeAll(if (b) "true" else "false"),
        .int => |i| try w.print("{d}", .{i}),
        .float => |f| if (std.math.isNan(f)) try w.writeAll("NaN") else if (std.math.isInf(f)) try w.writeAll(if (f < 0) "-Infinity" else "Infinity") else try floatRepr(f).format(w),
        .decimal => |d| {
            var buf: [256]u8 = undefined;
            var bw: std.Io.Writer = .fixed(&buf);
            try d.format(&bw);
            try std.json.Stringify.encodeJsonString(bw.buffered(), .{}, w);
        },
        .string => |s| try std.json.Stringify.encodeJsonString(s, .{}, w),
        .array => |items| {
            try w.writeByte('[');
            for (items, 0..) |item, i| {
                if (i > 0) try w.writeAll(", ");
                try writeJsonToken(a, w, item);
            }
            try w.writeByte(']');
        },
        .object => |obj| {
            const keys = try a.dupe([]const u8, obj.keys());
            std.mem.sort([]const u8, keys, {}, struct {
                fn lt(_: void, p: []const u8, q: []const u8) bool {
                    return std.mem.order(u8, p, q) == .lt;
                }
            }.lt);
            try w.writeByte('{');
            for (keys, 0..) |k, i| {
                if (i > 0) try w.writeAll(", ");
                try std.json.Stringify.encodeJsonString(k, .{}, w);
                try w.writeAll(": ");
                try writeJsonToken(a, w, obj.get(k).?);
            }
            try w.writeByte('}');
        },
    }
}

test "python text of values" {
    var buf: [128]u8 = undefined;
    const cases = [_]struct { f64, []const u8 }{
        .{ 1.5, "1.5" },       .{ 100.0, "100.0" },      .{ 1e16, "1e+16" }, .{ 0.0001, "0.0001" },
        .{ 0.00001, "1e-05" }, .{ -2.5e-7, "-2.5e-07" }, .{ 0.1, "0.1" },    .{ 123456789.125, "123456789.125" },
        .{ -0.0, "-0.0" },
    };
    for (cases) |c| try std.testing.expectEqualStrings(c[1], try std.fmt.bufPrint(&buf, "{f}", .{floatRepr(c[0])}));
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const d = try Decimal.parse(a, "007.50");
    try std.testing.expectEqualStrings("7.50", try std.fmt.bufPrint(&buf, "{f}", .{d}));
    try std.testing.expectEqualStrings("0.00001", try std.fmt.bufPrint(&buf, "{f}", .{try Decimal.parse(a, "1e-05")}));
    try std.testing.expectEqualStrings("1E+16", try std.fmt.bufPrint(&buf, "{f}", .{try Decimal.parse(a, "1e+16")}));
    try std.testing.expect(Decimal.eql(try Decimal.parse(a, "1.50"), try Decimal.parse(a, "1.5")));
    try std.testing.expect(pyEql(.{ .int = 1 }, .{ .bool = true }));
    try std.testing.expect(pyEql(.{ .int = 1 }, .{ .float = 1.0 }));
    try std.testing.expectEqualStrings("Decimal('1.5')", try std.fmt.bufPrint(&buf, "{f}", .{pyRepr(.{ .decimal = try Decimal.parse(a, "1.5") })}));
}
