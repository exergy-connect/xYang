const std = @import("std");

/// `version` in the repository `pyproject.toml`, which is what `xyang -V` prints
/// after `pip install -e .`.
fn packageVersion(b: *std.Build) []const u8 {
    const joined = b.root.join(b.allocator, "../pyproject.toml") catch @panic("OOM");
    const text = joined.root_dir.handle.readFileAlloc(
        b.graph.io,
        joined.sub_path,
        b.allocator,
        .limited(1 << 20),
    ) catch |err| std.process.fatal("reading {s}: {t}", .{ joined.sub_path, err });
    const needle = "version = \"";
    const at = std.mem.indexOf(u8, text, needle) orelse std.process.fatal("pyproject.toml has no version", .{});
    const rest = text[at + needle.len ..];
    const end = std.mem.indexOfScalar(u8, rest, '"') orelse std.process.fatal("pyproject.toml version is unterminated", .{});
    return rest[0..end];
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // Explicit opt-in target: native CLI builds remain unchanged.
    const wasm_target = b.resolveTargetQuery(.{ .cpu_arch = .wasm32, .os_tag = .freestanding });
    const wasm = b.addExecutable(.{
        .name = "xyang",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wasm.zig"),
            .target = wasm_target,
            .optimize = optimize,
        }),
    });
    wasm.entry = .disabled;
    wasm.rdynamic = true;
    wasm.stack_size = 2 * 1024 * 1024;
    wasm.max_memory = 256 * 1024 * 1024;
    const install_wasm = b.addInstallArtifact(wasm, .{});
    b.step("wasm", "Build the freestanding Wasm validation library").dependOn(&install_wasm.step);

    const lib = b.addModule("xyang", .{
        .root_source_file = b.path("src/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    const options = b.addOptions();
    options.addOption([]const u8, "version", packageVersion(b));

    const exe = b.addExecutable(.{
        .name = "xyang-zig",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "xyang", .module = lib },
                .{ .name = "build_options", .module = options.createModule() },
            },
        }),
    });
    exe.root_module.strip = optimize != .debug;
    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());
    run_cmd.addPassthruArgs();
    b.step("run", "Run xyang-zig").dependOn(&run_cmd.step);

    const runner = b.addExecutable(.{
        .name = "xyang-zig-conformance",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/conformance.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{.{ .name = "xyang", .module = lib }},
        }),
    });
    b.installArtifact(runner);
    const run_conformance = b.addRunArtifact(runner);
    run_conformance.setCwd(b.path("."));
    run_conformance.addArgs(&.{ "--cases", "../tests/cases", "--pending", "conformance-pending.txt" });
    run_conformance.addPassthruArgs();
    run_conformance.has_side_effects = true;
    b.step("conformance", "Run the shared conformance cases in tests/cases").dependOn(&run_conformance.step);

    const lib_tests = b.addTest(.{ .root_module = lib });
    const exe_tests = b.addTest(.{ .root_module = exe.root_module });
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&b.addRunArtifact(lib_tests).step);
    test_step.dependOn(&b.addRunArtifact(exe_tests).step);
}
