//! YANG `pattern` arguments (XSD regular expressions, RFC 7950 9.4.5, XML Schema Part 2
//! Appendix F), mirroring `src/xyang/xsd_regex.py`.
//!
//! `translate` follows Python step for step: the XSD pattern becomes the same Python `re`
//! source text (`(?:body)\Z`, classes rendered as `\UXXXXXXXX` ranges), and that text is
//! compiled by a parser for the `re` subset the translator emits, so unsupported
//! constructs and `re.error` failures report the same messages and positions. Matching
//! is `re.match` (anchored at the start) on code points, by NFA simulation.

const std = @import("std");
const pyfmt = @import("pyfmt.zig");
const uc = @import("unicode_categories.zig");

const Allocator = std.mem.Allocator;
const repr = pyfmt.repr;

pub const Range = [2]u21;
pub const Error = error{ OutOfMemory, InvalidPattern };

/// `YangSemanticError` text when `translate` fails.
pub const Failure = struct {
    message: []const u8 = "",
    /// True when the construct is valid for Python but this port cannot match it.
    unsupported: bool = false,
};

pub const MAX_CP: u21 = 0x10FFFF;

const GENERAL_CATEGORIES = [_]struct { []const u8, []const []const u8 }{
    .{ "L", &.{ "Lu", "Ll", "Lt", "Lm", "Lo" } },
    .{ "M", &.{ "Mn", "Mc", "Me" } },
    .{ "N", &.{ "Nd", "Nl", "No" } },
    .{ "P", &.{ "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po" } },
    .{ "Z", &.{ "Zs", "Zl", "Zp" } },
    .{ "S", &.{ "Sm", "Sc", "Sk", "So" } },
    .{ "C", &.{ "Cc", "Cf", "Co", "Cn" } },
};

/// XML 1.0 (5th ed.) NameStartChar / NameChar.
const NAME_START = [_]Range{
    .{ 0x3A, 0x3A },     .{ 0x41, 0x5A },     .{ 0x5F, 0x5F },     .{ 0x61, 0x7A },       .{ 0xC0, 0xD6 },     .{ 0xD8, 0xF6 },
    .{ 0xF8, 0x2FF },    .{ 0x370, 0x37D },   .{ 0x37F, 0x1FFF },  .{ 0x200C, 0x200D },   .{ 0x2070, 0x218F }, .{ 0x2C00, 0x2FEF },
    .{ 0x3001, 0xD7FF }, .{ 0xF900, 0xFDCF }, .{ 0xFDF0, 0xFFFD }, .{ 0x10000, 0xEFFFF },
};
const NAME_CHAR_EXTRA = [_]Range{ .{ 0x2D, 0x2E }, .{ 0x30, 0x39 }, .{ 0xB7, 0xB7 }, .{ 0x300, 0x36F }, .{ 0x203F, 0x2040 } };
const XSD_SPACE = [_]Range{ .{ 0x9, 0xA }, .{ 0xD, 0xD }, .{ 0x20, 0x20 } };
const XSD_DOT_EXCLUDED = [_]Range{ .{ 0xA, 0xA }, .{ 0xD, 0xD } };
const SINGLE_ESCAPE_LITERALS = "\\|.-^?*+{}()[]";

/// XSD `SingleCharEsc` punctuation, plus any other ASCII printable non-alphanumeric (#204).
fn isLiteralPunctuation(ch: u21) bool {
    if (ch < 0x80 and std.mem.indexOfScalar(u8, SINGLE_ESCAPE_LITERALS, @intCast(ch)) != null) return true;
    if (ch < 0x20 or ch > 0x7E) return false;
    const c: u8 = @intCast(ch);
    if (c >= '0' and c <= '9') return false;
    if (c >= 'A' and c <= 'Z') return false;
    if (c >= 'a' and c <= 'z') return false;
    return true;
}

/// Characters `re.escape` prefixes with a backslash (Python 3.7+).
const RE_SPECIAL = "()[]{}?*+-|^$\\.&~# \t\n\r\x0b\x0c";

fn isSubcategory(name: []const u8) bool {
    for (uc.CATEGORIES) |c| if (std.mem.eql(u8, c, name)) return true;
    return false;
}

fn groupOf(name: []const u8) ?[]const []const u8 {
    for (GENERAL_CATEGORIES) |g| if (std.mem.eql(u8, g[0], name)) return g[1];
    return null;
}

fn lessRange(_: void, x: Range, y: Range) bool {
    return x[0] < y[0] or (x[0] == y[0] and x[1] < y[1]);
}

pub fn normalize(a: Allocator, ranges: []const Range) Error![]Range {
    const sorted = try a.dupe(Range, ranges);
    std.mem.sort(Range, sorted, {}, lessRange);
    var out: std.ArrayList(Range) = .empty;
    for (sorted) |r| {
        if (out.items.len > 0 and @as(u32, r[0]) <= @as(u32, out.items[out.items.len - 1][1]) + 1) {
            const last = &out.items[out.items.len - 1];
            last[1] = @max(last[1], r[1]);
        } else {
            try out.append(a, r);
        }
    }
    return out.items;
}

pub fn complement(a: Allocator, ranges: []const Range) Error![]Range {
    var out: std.ArrayList(Range) = .empty;
    var nxt: u32 = 0;
    for (try normalize(a, ranges)) |r| {
        if (r[0] > nxt) try out.append(a, .{ @intCast(nxt), r[0] - 1 });
        nxt = @as(u32, r[1]) + 1;
    }
    if (nxt <= MAX_CP) try out.append(a, .{ @intCast(nxt), MAX_CP });
    return out.items;
}

/// `_category_ranges`: a one- or two-letter general category.
pub fn categoryRanges(a: Allocator, name: []const u8) Error![]Range {
    const single = [_][]const u8{name};
    const subs: []const []const u8 = groupOf(name) orelse &single;
    var ids: [32]bool = @splat(false);
    for (subs) |s| {
        for (uc.CATEGORIES, 0..) |c, i| if (std.mem.eql(u8, c, s)) {
            ids[i] = true;
        };
    }
    var out: std.ArrayList(Range) = .empty;
    for (uc.RUNS, 0..) |run, i| {
        if (!ids[run & 31]) continue;
        const start: u21 = @intCast(run >> 5);
        const end: u21 = if (i + 1 < uc.RUNS.len) @intCast((uc.RUNS[i + 1] >> 5) - 1) else MAX_CP;
        try out.append(a, .{ start, end });
    }
    return normalize(a, out.items);
}

fn decodeUtf8(a: Allocator, s: []const u8) Error![]u21 {
    var out: std.ArrayList(u21) = .empty;
    var it = (std.unicode.Utf8View.init(s) catch return error.InvalidPattern).iterator();
    while (it.nextCodepoint()) |cp| try out.append(a, cp);
    return out.items;
}

fn encodeUtf8(a: Allocator, cps: []const u21) Error![]const u8 {
    var out: std.ArrayList(u8) = .empty;
    for (cps) |cp| {
        var buf: [4]u8 = undefined;
        const n = std.unicode.utf8Encode(cp, &buf) catch {
            try out.appendSlice(a, "\u{FFFD}");
            continue;
        };
        try out.appendSlice(a, buf[0..n]);
    }
    return out.items;
}

const Translator = struct {
    a: Allocator,
    pattern: []const u8,
    src: []const u21,
    pos: usize = 0,
    out: std.ArrayList(u21) = .empty,
    failure: *Failure,

    fn peek(t: *const Translator, offset: usize) ?u21 {
        const i = t.pos + offset;
        return if (i < t.src.len) t.src[i] else null;
    }

    fn unsupported(t: *Translator, construct: []const u21) Error {
        const text = try encodeUtf8(t.a, construct);
        t.failure.* = .{ .message = try std.fmt.allocPrint(t.a, "unsupported XSD regex construct {f} in pattern {f}", .{ repr(text), repr(t.pattern) }) };
        return error.InvalidPattern;
    }

    fn unsupportedText(t: *Translator, text: []const u8) Error {
        t.failure.* = .{ .message = try std.fmt.allocPrint(t.a, "unsupported XSD regex construct {f} in pattern {f}", .{ repr(text), repr(t.pattern) }) };
        return error.InvalidPattern;
    }

    fn semantic(t: *Translator, comptime fmt: []const u8) Error {
        t.failure.* = .{ .message = try std.fmt.allocPrint(t.a, fmt, .{repr(t.pattern)}) };
        return error.InvalidPattern;
    }

    const Escape = struct { ranges: []Range, negated: bool };

    /// `escape_ranges`: an escape at `pos` (after the backslash).
    fn escapeRanges(t: *Translator) Error!Escape {
        const ch = t.peek(0) orelse return t.unsupportedText("\\");
        t.pos += 1;
        switch (ch) {
            'p', 'P' => {
                if (t.peek(0) != '{') {
                    return t.unsupported(&.{ '\\', ch });
                }
                const end = std.mem.indexOfScalarPos(u21, t.src, t.pos, '}') orelse return t.unsupported(t.src[t.pos - 2 ..]);
                const name = try encodeUtf8(t.a, t.src[t.pos + 1 .. end]);
                t.pos = end + 1;
                if (groupOf(name) == null and !isSubcategory(name)) {
                    return t.unsupportedText(try std.fmt.allocPrint(t.a, "\\{u}{{{s}}}", .{ ch, name }));
                }
                return .{ .ranges = try categoryRanges(t.a, name), .negated = ch == 'P' };
            },
            'n' => return .{ .ranges = try t.a.dupe(Range, &.{.{ 0xA, 0xA }}), .negated = false },
            'r' => return .{ .ranges = try t.a.dupe(Range, &.{.{ 0xD, 0xD }}), .negated = false },
            't' => return .{ .ranges = try t.a.dupe(Range, &.{.{ 0x9, 0x9 }}), .negated = false },
            'd', 'D' => return .{ .ranges = try categoryRanges(t.a, "Nd"), .negated = ch == 'D' },
            's', 'S' => return .{ .ranges = try t.a.dupe(Range, &XSD_SPACE), .negated = ch == 'S' },
            'w', 'W' => {
                var excluded: std.ArrayList(Range) = .empty;
                try excluded.appendSlice(t.a, try categoryRanges(t.a, "P"));
                try excluded.appendSlice(t.a, try categoryRanges(t.a, "Z"));
                try excluded.appendSlice(t.a, try categoryRanges(t.a, "C"));
                return .{ .ranges = try normalize(t.a, excluded.items), .negated = ch == 'w' };
            },
            'i', 'I' => return .{ .ranges = try t.a.dupe(Range, &NAME_START), .negated = ch == 'I' },
            'c', 'C' => {
                var all: std.ArrayList(Range) = .empty;
                try all.appendSlice(t.a, &NAME_START);
                try all.appendSlice(t.a, &NAME_CHAR_EXTRA);
                return .{ .ranges = all.items, .negated = ch == 'C' };
            },
            else => {
                if (isLiteralPunctuation(ch)) {
                    return .{ .ranges = try t.a.dupe(Range, &.{.{ ch, ch }}), .negated = false };
                }
                return t.unsupported(&.{ '\\', ch });
            },
        }
    }

    fn classAtom(t: *Translator) Error![]Range {
        const ch = t.peek(0) orelse return t.semantic("unterminated character class in pattern {f}");
        if (ch == '\\') {
            t.pos += 1;
            const e = try t.escapeRanges();
            return if (e.negated) complement(t.a, e.ranges) else e.ranges;
        }
        if (ch == '[') return t.unsupportedText("[");
        t.pos += 1;
        return t.a.dupe(Range, &.{.{ ch, ch }});
    }

    /// `char_class`: `[...]` at `pos` (after `[`).
    fn charClass(t: *Translator) Error!void {
        const start = t.pos - 1;
        const negated = t.peek(0) == '^';
        if (negated) t.pos += 1;
        var ranges: std.ArrayList(Range) = .empty;
        var first = true;
        while (true) {
            const ch = t.peek(0) orelse return t.semantic("unterminated character class in pattern {f}");
            if (ch == ']' and !first) {
                t.pos += 1;
                break;
            }
            if (ch == '-' and t.peek(1) == '[') {
                const end = std.mem.indexOfScalarPos(u21, t.src, t.pos, ']');
                const stop = if (end) |e| @min(e + 2, t.src.len) else t.src.len;
                return t.unsupported(t.src[start..stop]);
            }
            first = false;
            const single = ch != '\\' or (if (t.peek(1)) |n| (n >= 0x80 or std.mem.indexOfScalar(u8, "pPdDsSwWiIcC", @intCast(n)) == null) else false);
            const lo_ranges = try t.classAtom();
            const next1 = t.peek(1);
            if (single and t.peek(0) == '-' and next1 != ']' and next1 != '[') {
                t.pos += 1;
                const hi_ranges = try t.classAtom();
                if (lo_ranges.len != 1 or hi_ranges.len != 1 or lo_ranges[0][0] != lo_ranges[0][1] or hi_ranges[0][0] != hi_ranges[0][1]) {
                    return t.unsupported(t.src[start..t.pos]);
                }
                const lo = lo_ranges[0][0];
                const hi = hi_ranges[0][1];
                if (hi < lo) return t.semantic("invalid character range in pattern {f}");
                try ranges.append(t.a, .{ lo, hi });
            } else {
                try ranges.appendSlice(t.a, lo_ranges);
            }
        }
        var norm = try normalize(t.a, ranges.items);
        if (negated) norm = try complement(t.a, norm);
        try t.emitClass(norm);
    }

    fn emit(t: *Translator, s: []const u8) Error!void {
        for (s) |c| try t.out.append(t.a, c);
    }

    /// `[{_render(ranges)}]`, or `(?!)` for an empty set.
    fn emitClass(t: *Translator, ranges: []const Range) Error!void {
        if (ranges.len == 0) return t.emit("(?!)");
        try t.emit("[");
        for (ranges) |r| {
            var buf: [24]u8 = undefined;
            const text = if (r[0] == r[1])
                std.fmt.bufPrint(&buf, "\\U{X:0>8}", .{r[0]})
            else
                std.fmt.bufPrint(&buf, "\\U{X:0>8}-\\U{X:0>8}", .{ r[0], r[1] });
            try t.emit(text catch unreachable);
        }
        try t.emit("]");
    }

    /// `re.escape(ch)`.
    fn emitEscaped(t: *Translator, ch: u21) Error!void {
        if (ch < 0x80 and std.mem.indexOfScalar(u8, RE_SPECIAL, @intCast(ch)) != null) try t.out.append(t.a, '\\');
        try t.out.append(t.a, ch);
    }

    fn translate(t: *Translator) Error!void {
        while (t.pos < t.src.len) {
            const ch = t.src[t.pos];
            switch (ch) {
                '\\' => {
                    t.pos += 1;
                    const e = try t.escapeRanges();
                    try t.emitClass(if (e.negated) try complement(t.a, e.ranges) else e.ranges);
                },
                '[' => {
                    t.pos += 1;
                    try t.charClass();
                },
                '.' => {
                    t.pos += 1;
                    try t.emitClass(try complement(t.a, &XSD_DOT_EXCLUDED));
                },
                '(' => {
                    if (t.peek(1) == '?') return t.unsupportedText("(?");
                    t.pos += 1;
                    try t.emit("(?:");
                },
                '^', '$' => {
                    t.pos += 1;
                    try t.emitEscaped(ch);
                },
                '|', ')', '*', '+', '?' => {
                    t.pos += 1;
                    try t.out.append(t.a, ch);
                },
                '{' => {
                    // `\{\d+(,\d*)?\}`
                    var i = t.pos + 1;
                    const d0 = i;
                    while (i < t.src.len and t.src[i] >= '0' and t.src[i] <= '9') i += 1;
                    if (i == d0) return t.unsupportedText("{");
                    if (i < t.src.len and t.src[i] == ',') {
                        i += 1;
                        while (i < t.src.len and t.src[i] >= '0' and t.src[i] <= '9') i += 1;
                    }
                    if (i >= t.src.len or t.src[i] != '}') return t.unsupportedText("{");
                    try t.out.appendSlice(t.a, t.src[t.pos .. i + 1]);
                    t.pos = i + 1;
                },
                else => {
                    t.pos += 1;
                    try t.emitEscaped(ch);
                },
            }
        }
    }
};

// ---------------------------------------------------------------------------------------
// Compiled program: the `re` subset the translator emits, run as a Pike VM.

const Inst = union(enum) {
    set: []const Range,
    split: [2]u32,
    jmp: u32,
    /// `\Z`.
    at_end,
    /// `(?!)`.
    fail,
    match,
};

pub const Regex = struct {
    pattern: []const u8,
    /// The Python `re` source the pattern translates to.
    python_source: []const u8,
    prog: []const Inst,

    /// `re.match(...) is not None`: some path from the start reaches the end of the
    /// program, consuming a prefix of `s`.
    pub fn matches(self: *const Regex, a: Allocator, s: []const u8) error{OutOfMemory}!bool {
        const n = self.prog.len;
        var clist = try a.alloc(u32, n);
        var nlist = try a.alloc(u32, n);
        const seen = try a.alloc(u32, n);
        defer a.free(clist);
        defer a.free(nlist);
        defer a.free(seen);
        @memset(seen, std.math.maxInt(u32));
        var stack: std.ArrayList(u32) = .empty;
        defer stack.deinit(a);

        const cps = decodeUtf8(a, s) catch return false;
        defer a.free(cps);

        var clen: usize = 0;
        var gen: u32 = 0;
        if (try self.addThread(a, &stack, clist, &clen, seen, gen, 0, cps.len == 0)) return true;
        for (cps, 0..) |cp, i| {
            gen += 1;
            var nlen: usize = 0;
            const at_end = i + 1 == cps.len;
            for (clist[0..clen]) |pc| {
                switch (self.prog[pc]) {
                    .set => |ranges| if (inSet(ranges, cp)) {
                        if (try self.addThread(a, &stack, nlist, &nlen, seen, gen, pc + 1, at_end)) return true;
                    },
                    else => {},
                }
            }
            std.mem.swap([]u32, &clist, &nlist);
            clen = nlen;
            if (clen == 0) return false;
        }
        return false;
    }

    /// Follow the epsilon closure from `start`; true when `match` is reachable.
    fn addThread(self: *const Regex, a: Allocator, stack: *std.ArrayList(u32), list: []u32, len: *usize, seen: []u32, gen: u32, start: u32, at_end: bool) error{OutOfMemory}!bool {
        stack.clearRetainingCapacity();
        try stack.append(a, start);
        while (stack.pop()) |pc| {
            if (seen[pc] == gen) continue;
            seen[pc] = gen;
            switch (self.prog[pc]) {
                .match => return true,
                .jmp => |to| try stack.append(a, to),
                .split => |to| {
                    try stack.append(a, to[1]);
                    try stack.append(a, to[0]);
                },
                .at_end => if (at_end) try stack.append(a, pc + 1),
                .fail => {},
                .set => {
                    list[len.*] = pc;
                    len.* += 1;
                },
            }
        }
        return false;
    }
};

fn inSet(ranges: []const Range, cp: u21) bool {
    var lo: usize = 0;
    var hi: usize = ranges.len;
    while (lo < hi) {
        const mid = (lo + hi) / 2;
        if (cp < ranges[mid][0]) {
            hi = mid;
        } else if (cp > ranges[mid][1]) {
            lo = mid + 1;
        } else return true;
    }
    return false;
}

const Node = union(enum) {
    set: []const Range,
    concat: []const *Node,
    alt: []const *Node,
    repeat: struct { node: *Node, min: u32, max: ?u32 },
    at_end,
    fail,
};

/// Parser for the translator's output (`sre_parse` errors and positions).
const ReParser = struct {
    a: Allocator,
    src: []const u21,
    pos: usize = 0,
    failure: *Failure,
    pattern: []const u8,

    fn reError(p: *ReParser, msg: []const u8, at: usize) Error {
        p.failure.* = .{ .message = try std.fmt.allocPrint(p.a, "invalid pattern {f}: {s} at position {d}", .{ repr(p.pattern), msg, at }) };
        return error.InvalidPattern;
    }

    fn newNode(p: *ReParser, n: Node) Error!*Node {
        const out = try p.a.create(Node);
        out.* = n;
        return out;
    }

    fn parseAlt(p: *ReParser) Error!*Node {
        var branches: std.ArrayList(*Node) = .empty;
        try branches.append(p.a, try p.parseSeq());
        while (p.pos < p.src.len and p.src[p.pos] == '|') {
            p.pos += 1;
            try branches.append(p.a, try p.parseSeq());
        }
        if (branches.items.len == 1) return branches.items[0];
        return p.newNode(.{ .alt = branches.items });
    }

    fn parseSeq(p: *ReParser) Error!*Node {
        var items: std.ArrayList(*Node) = .empty;
        while (p.pos < p.src.len) {
            const ch = p.src[p.pos];
            if (ch == '|' or ch == ')') break;
            if (ch == '*' or ch == '+' or ch == '?' or ch == '{') {
                try p.parseRepeat(&items);
                continue;
            }
            try items.append(p.a, try p.parseAtom());
        }
        return p.newNode(.{ .concat = items.items });
    }

    fn parseRepeat(p: *ReParser, items: *std.ArrayList(*Node)) Error!void {
        const at = p.pos;
        const ch = p.src[p.pos];
        p.pos += 1;
        var min: u32 = 0;
        var max: ?u32 = null;
        switch (ch) {
            '*' => {},
            '+' => min = 1,
            '?' => max = 1,
            else => {
                const lo = p.readInt();
                if (p.src[p.pos] == ',') {
                    p.pos += 1;
                    max = p.readInt();
                } else {
                    max = lo;
                }
                min = lo orelse 0;
                p.pos += 1; // `}`
                if (max) |m| if (m < min) return p.reError("min repeat greater than max repeat", at + 1);
            },
        }
        if (items.items.len == 0 or items.items[items.items.len - 1].* == .at_end) return p.reError("nothing to repeat", at);
        const last = items.items[items.items.len - 1];
        if (last.* == .repeat) return p.reError("multiple repeat", at);
        if (p.pos < p.src.len and p.src[p.pos] == '?') {
            p.pos += 1;
        } else if (p.pos < p.src.len and p.src[p.pos] == '+') {
            const text = try encodeUtf8(p.a, p.src[at .. p.pos + 1]);
            p.failure.* = .{
                .message = try std.fmt.allocPrint(p.a, "xyang-zig cannot match the possessive quantifier {f} in pattern {f}", .{ repr(text), repr(p.pattern) }),
                .unsupported = true,
            };
            return error.InvalidPattern;
        }
        items.items[items.items.len - 1] = try p.newNode(.{ .repeat = .{ .node = last, .min = min, .max = max } });
    }

    fn readInt(p: *ReParser) ?u32 {
        const start = p.pos;
        var v: u64 = 0;
        while (p.pos < p.src.len and p.src[p.pos] >= '0' and p.src[p.pos] <= '9') : (p.pos += 1) {
            v = @min(v * 10 + (p.src[p.pos] - '0'), std.math.maxInt(u32));
        }
        return if (p.pos == start) null else @intCast(v);
    }

    fn readHex8(p: *ReParser) u21 {
        var v: u32 = 0;
        for (0..8) |_| {
            v = v * 16 + (std.fmt.charToDigit(@intCast(p.src[p.pos]), 16) catch 0);
            p.pos += 1;
        }
        return @intCast(@min(v, MAX_CP));
    }

    fn parseAtom(p: *ReParser) Error!*Node {
        const ch = p.src[p.pos];
        switch (ch) {
            '(' => {
                const start = p.pos;
                // `(?:` or `(?!)`
                if (p.pos + 3 < p.src.len and p.src[p.pos + 1] == '?' and p.src[p.pos + 2] == '!' and p.src[p.pos + 3] == ')') {
                    p.pos += 4;
                    return p.newNode(.fail);
                }
                p.pos += 3;
                const inner = try p.parseAlt();
                if (p.pos >= p.src.len or p.src[p.pos] != ')') return p.reError("missing ), unterminated subpattern", start);
                p.pos += 1;
                return inner;
            },
            '[' => {
                p.pos += 1;
                var ranges: std.ArrayList(Range) = .empty;
                while (p.src[p.pos] != ']') {
                    p.pos += 2; // `\U`
                    const lo = p.readHex8();
                    var hi = lo;
                    if (p.src[p.pos] == '-') {
                        p.pos += 3;
                        hi = p.readHex8();
                    }
                    try ranges.append(p.a, .{ lo, hi });
                }
                p.pos += 1;
                return p.newNode(.{ .set = ranges.items });
            },
            '\\' => {
                const esc = p.src[p.pos + 1];
                p.pos += 2;
                if (esc == 'Z') return p.newNode(.at_end);
                return p.newNode(.{ .set = try p.a.dupe(Range, &.{.{ esc, esc }}) });
            },
            else => {
                p.pos += 1;
                return p.newNode(.{ .set = try p.a.dupe(Range, &.{.{ ch, ch }}) });
            },
        }
    }
};

const Compiler = struct {
    a: Allocator,
    prog: std.ArrayList(Inst) = .empty,

    fn pc(c: *const Compiler) u32 {
        return @intCast(c.prog.items.len);
    }

    fn emit(c: *Compiler, inst: Inst) Error!u32 {
        const at = c.pc();
        try c.prog.append(c.a, inst);
        return at;
    }

    fn compile(c: *Compiler, n: *const Node) Error!void {
        switch (n.*) {
            .set => |r| _ = try c.emit(.{ .set = r }),
            .at_end => _ = try c.emit(.at_end),
            .fail => _ = try c.emit(.fail),
            .concat => |items| for (items) |it| try c.compile(it),
            .alt => |branches| {
                var jumps: std.ArrayList(u32) = .empty;
                for (branches, 0..) |b, i| {
                    if (i + 1 < branches.len) {
                        const split = try c.emit(.{ .split = .{ 0, 0 } });
                        c.prog.items[split].split[0] = c.pc();
                        try c.compile(b);
                        try jumps.append(c.a, try c.emit(.{ .jmp = 0 }));
                        c.prog.items[split].split[1] = c.pc();
                    } else {
                        try c.compile(b);
                    }
                }
                for (jumps.items) |j| c.prog.items[j].jmp = c.pc();
            },
            .repeat => |r| {
                for (0..r.min) |_| try c.compile(r.node);
                if (r.max) |max| {
                    var exits: std.ArrayList(u32) = .empty;
                    for (r.min..max) |_| {
                        const split = try c.emit(.{ .split = .{ 0, 0 } });
                        c.prog.items[split].split[0] = c.pc();
                        try exits.append(c.a, split);
                        try c.compile(r.node);
                    }
                    for (exits.items) |s| c.prog.items[s].split[1] = c.pc();
                } else {
                    const split = try c.emit(.{ .split = .{ 0, 0 } });
                    c.prog.items[split].split[0] = c.pc();
                    try c.compile(r.node);
                    _ = try c.emit(.{ .jmp = split });
                    c.prog.items[split].split[1] = c.pc();
                }
            },
        }
    }
};

/// Repetition bounds that would expand the program past this many instructions are
/// refused loudly instead of building an unbounded automaton.
const MAX_PROGRAM = 1 << 20;

/// `translate`: compile an XSD regex; on failure `failure` holds the message.
pub fn translate(a: Allocator, pattern: []const u8, failure: *Failure) Error!*Regex {
    const src = decodeUtf8(a, pattern) catch {
        failure.* = .{ .message = try std.fmt.allocPrint(a, "invalid pattern {f}: not UTF-8", .{repr(pattern)}) };
        return error.InvalidPattern;
    };
    var t: Translator = .{ .a = a, .pattern = pattern, .src = src, .failure = failure };
    try t.emit("(?:");
    try t.translate();
    try t.emit(")\\Z");
    const body = t.out.items;
    var p: ReParser = .{ .a = a, .src = body, .failure = failure, .pattern = pattern };
    const root = try p.parseAlt();
    if (p.pos < body.len) return p.reError("unbalanced parenthesis", p.pos);
    if (programSize(root) > MAX_PROGRAM) {
        failure.* = .{
            .message = try std.fmt.allocPrint(a, "xyang-zig cannot match pattern {f}: its repetition bounds are too large", .{repr(pattern)}),
            .unsupported = true,
        };
        return error.InvalidPattern;
    }
    var c: Compiler = .{ .a = a };
    try c.compile(root);
    _ = try c.emit(.match);
    const re = try a.create(Regex);
    re.* = .{ .pattern = pattern, .python_source = try encodeUtf8(a, body), .prog = c.prog.items };
    return re;
}

fn programSize(n: *const Node) u64 {
    return switch (n.*) {
        .set, .at_end, .fail => 1,
        .concat => |items| blk: {
            var s: u64 = 0;
            for (items) |it| s +|= programSize(it);
            break :blk s;
        },
        .alt => |b| blk: {
            var s: u64 = 0;
            for (b) |it| s +|= programSize(it) + 2;
            break :blk s;
        },
        .repeat => |r| (programSize(r.node) + 2) *| (@as(u64, r.max orelse r.min) + 1),
    };
}

fn expectMatch(pattern: []const u8, s: []const u8, want: bool) !void {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var f: Failure = .{};
    const re = try translate(arena.allocator(), pattern, &f);
    try std.testing.expectEqual(want, try re.matches(arena.allocator(), s));
}

fn expectFailure(pattern: []const u8, message: []const u8) !void {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var f: Failure = .{};
    try std.testing.expectError(error.InvalidPattern, translate(arena.allocator(), pattern, &f));
    try std.testing.expectEqualStrings(message, f.message);
}

test "anchored XSD matching" {
    try expectMatch("[a-z]+", "abc", true);
    try expectMatch("[a-z]+", "abc1", false);
    try expectMatch("\\d{4}-\\d{2}", "2026-11", true);
    try expectMatch("\\d{4}-\\d{2}", "2026-1", false);
    try expectMatch("a|bc", "bc", true);
    try expectMatch("(ab)*c?", "ababc", true);
    try expectMatch("(ab)*c?", "aba", false);
    try expectMatch("x{2,3}", "xxxx", false);
    try expectMatch("x{2,}", "xxxxx", true);
    try expectMatch("\\p{L}+", "Größe", true);
    try expectMatch("\\p{L}+", "abc1", false);
    try expectMatch("\\P{Nd}*", "abc", true);
    try expectMatch("[^0-9]+", "ab", true);
    try expectMatch(".", "\n", false);
    try expectMatch("\\w+", "a_b", false);
    try expectMatch("\\w+", "ab9", true);
    try expectMatch("^a$", "^a$", true);
    try expectMatch("", "", true);
    try expectMatch("", "x", false);
    try expectMatch("[b\\*\\-\\#$@&:]+", "b#@", true);
    try expectMatch("[b\\*\\-\\#$@&:]+", "x", false);
    try expectMatch("a\\#b\\%c", "a#b%c", true);
    try expectMatch("a\\#b\\%c", "a#bc", false);
}

test "errors follow xsd_regex.py and re" {
    try expectFailure("[a-z-[aeiou]]+", "unsupported XSD regex construct '[a-z-[aeiou]]' in pattern '[a-z-[aeiou]]+'");
    try expectFailure("\\p{IsBasicLatin}", "unsupported XSD regex construct '\\\\p{IsBasicLatin}' in pattern '\\\\p{IsBasicLatin}'");
    try expectFailure("(?i)a", "unsupported XSD regex construct '(?' in pattern '(?i)a'");
    try expectFailure("\\q", "unsupported XSD regex construct '\\\\q' in pattern '\\\\q'");
    try expectFailure("\\1", "unsupported XSD regex construct '\\\\1' in pattern '\\\\1'");
    try expectFailure("[z-a]", "invalid character range in pattern '[z-a]'");
    try expectFailure("[ab", "unterminated character class in pattern '[ab'");
    try expectFailure("*a", "invalid pattern '*a': nothing to repeat at position 3");
    try expectFailure("a**", "invalid pattern 'a**': multiple repeat at position 5");
    try expectFailure("(a", "invalid pattern '(a': missing ), unterminated subpattern at position 0");
    try expectFailure("a)b", "invalid pattern 'a)b': unbalanced parenthesis at position 6");
}
