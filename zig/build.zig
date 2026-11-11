const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const lib = b.addModule("xyang", .{
        .root_source_file = b.path("src/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    const exe = b.addExecutable(.{
        .name = "xyang-zig",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{.{ .name = "xyang", .module = lib }},
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
