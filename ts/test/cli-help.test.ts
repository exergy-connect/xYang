import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { beforeAll, describe, expect, it } from "vitest";
import { cliCommands, formatCommandHelp, formatGlobalHelp, requestsHelp } from "../src/cli/args";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const work = mkdtempSync(join(tmpdir(), "xyang-help-"));
const cli = join(work, "cli.mjs");

beforeAll(async () => {
  await build({
    absWorkingDir: tsRoot,
    entryPoints: [resolve(tsRoot, "src/cli.ts")],
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node22",
    outfile: cli,
    logLevel: "silent"
  });
});

function emptyDir(): string {
  return mkdtempSync(join(tmpdir(), "xyang-help-cwd-"));
}

function run(args: string[], cwd = emptyDir()): ReturnType<typeof spawnSync> {
  return spawnSync(process.execPath, [cli, ...args], {
    cwd,
    encoding: "utf-8",
    input: "",
    timeout: 15_000
  });
}

function longOptions(text: string): string[] {
  return text.match(/--[A-Za-z0-9][\w-]*/g) ?? [];
}

describe("xyang-ts --help", () => {
  it("renders help from the command registry", () => {
    const commands = cliCommands();
    expect(commands.length).toBeGreaterThan(0);
    const globalHelp = formatGlobalHelp();
    const names = new Set(commands.map((command) => command.name));
    for (const name of names) {
      expect(globalHelp).toContain(name);
    }
    expect(globalHelp).toContain("examples:");
    const allFlags = new Set<string>(["--help"]);
    for (const command of commands) {
      for (const option of command.options) {
        allFlags.add(option.name);
      }
    }
    const globalBody = globalHelp.split("\nnotes:\n")[0] ?? globalHelp;
    for (const flag of longOptions(globalBody)) {
      expect(allFlags.has(flag)).toBe(true);
    }
    for (const command of commands) {
      const help = formatCommandHelp(command);
      expect(help).toContain("examples:");
      expect(help.toLowerCase()).toContain("default");
      for (const option of command.options) {
        expect(help).toContain(option.name);
        expect(help).toContain(option.help);
        if (option.metavar) {
          expect(help).toContain(option.metavar);
        }
      }
      const optionsBlock = help.slice(help.indexOf("\noptions:\n"), help.indexOf("\nexamples:\n"));
      for (const flag of longOptions(optionsBlock)) {
        expect(flag === "--help" || command.options.some((option) => option.name === flag)).toBe(true);
      }
      const beforeNotes = help.split("\nnotes:\n")[0] ?? help;
      for (const flag of longOptions(beforeNotes)) {
        expect(allFlags.has(flag)).toBe(true);
      }
    }
    const convert = commands.find((command) => command.name === "convert");
    expect(convert).toBeDefined();
    const convertOptions = convert!.options.map((option) => option.name);
    expect(convertOptions).not.toContain("--output");
    expect(convertOptions).not.toContain("-o");
    expect(commands.flatMap((command) => command.options.map((option) => option.name))).not.toContain("--version");
  });

  it("exits 0 on --help and -h without reading or writing files", () => {
    const cwd = emptyDir();
    const globalHelp = formatGlobalHelp();
    for (const args of [[], ["--help"], ["-h"]]) {
      const result = run(args, cwd);
      expect(result.status).toBe(0);
      expect(result.stdout).toBe(globalHelp);
      expect(result.stderr).toBe("");
    }
    for (const command of cliCommands()) {
      const help = formatCommandHelp(command);
      for (const flag of ["--help", "-h"]) {
        const result = run([command.name, flag], cwd);
        expect(result.status).toBe(0);
        expect(result.stdout).toBe(help);
        expect(result.stderr).toBe("");
      }
    }
    expect(readdirSync(cwd)).toEqual([]);
  });

  it("exits 2 for an unknown command, unknown flag, or missing option value", () => {
    const cwd = emptyDir();
    const unknown = run(["no-such-command"], cwd);
    expect(unknown.status).toBe(2);
    expect(unknown.stdout).toBe("");
    expect(unknown.stderr).toContain("Unknown command: no-such-command");

    const globalFlag = run(["--not-a-registered-flag"], cwd);
    expect(globalFlag.status).toBe(2);
    expect(globalFlag.stdout).toBe("");
    expect(globalFlag.stderr).toContain("--not-a-registered-flag");

    for (const command of cliCommands()) {
      const bad = run([command.name, "--not-a-registered-flag"], cwd);
      expect(bad.status).toBe(2);
      expect(bad.stdout).toBe("");
      expect(bad.stderr).toContain("unrecognized argument: --not-a-registered-flag");
      for (const option of command.options) {
        if (!option.takesValue) {
          continue;
        }
        const missing = run([command.name, option.name], cwd);
        expect(missing.status).toBe(2);
        expect(missing.stdout).toBe("");
        expect(missing.stderr.length).toBeGreaterThan(0);
      }
    }
    expect(readdirSync(cwd)).toEqual([]);
  });

  it("keeps non-help missing-file exits", () => {
    const cwd = emptyDir();
    const parse = run(["parse"], cwd);
    expect(parse.status).toBe(1);
    expect(parse.stderr).toContain("Missing <file.yang>");
    const convert = run(["convert"], cwd);
    expect(convert.status).toBe(1);
    expect(convert.stderr).toContain("Missing <file.yang>");
    const validate = run(["validate"], cwd);
    expect(validate.status).toBe(2);
    expect(validate.stderr).toContain("Missing <file.yang>");
    expect(readdirSync(cwd)).toEqual([]);
  });

  it("treats a value-taking option's next token as a value", () => {
    const validate = cliCommands().find((command) => command.name === "validate");
    expect(validate).toBeDefined();
    expect(requestsHelp(validate!.options, ["--help"])).toBe(true);
    expect(requestsHelp(validate!.options, ["-h"])).toBe(true);
    expect(requestsHelp(validate!.options, ["--format", "json", "--help"])).toBe(true);
    expect(requestsHelp(validate!.options, ["--format", "--help"])).toBe(false);
  });
});
