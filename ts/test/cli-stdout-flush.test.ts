import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { beforeAll, describe, expect, it } from "vitest";
import { generateJsonSchema } from "../src/json";
import { YangParser } from "../src/parser";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const work = mkdtempSync(join(tmpdir(), "xyang-flush-"));
const cli = join(work, "cli.mjs");

beforeAll(async () => {
  await build({
    absWorkingDir: tsRoot,
    entryPoints: [resolve(tsRoot, "src/cli.ts")],
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node24",
    outfile: cli,
    logLevel: "silent"
  });
});

function convertStdout(yangPath: string): Buffer {
  const result = spawnSync(process.execPath, [cli, "convert", yangPath], {
    encoding: "buffer",
    maxBuffer: 32 * 1024 * 1024,
    timeout: 60_000
  });
  expect(result.error).toBeUndefined();
  expect(result.status).toBe(0);
  return result.stdout;
}

function expectedSchema(yangPath: string): string {
  const module = new YangParser({ expand_uses: false }).parseFile(yangPath);
  return `${JSON.stringify(generateJsonSchema(module), null, 2)}\n`;
}

describe("xyang-ts stdout flush before exit", () => {
  it("returns the failure status with the error on stderr", () => {
    const result = spawnSync(process.execPath, [cli, "parse"], { encoding: "utf-8" });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Missing <file.yang>");
  });

  it("writes a full JSON Schema larger than the pipe buffer", () => {
    const yangPath = join(work, "wide.yang");
    const leaves: string[] = [];
    for (let i = 0; i < 800; i += 1) {
      leaves.push(
        `    leaf field_${i} {\n      type string;\n      description "field ${i} ${"x".repeat(80)}";\n    }`
      );
    }
    writeFileSync(
      yangPath,
      `module wide {\n  yang-version 1.1;\n  namespace "urn:xyang:wide";\n  prefix w;\n  container top {\n${leaves.join("\n")}\n  }\n}\n`
    );

    const stdout = convertStdout(yangPath);
    const text = stdout.toString("utf-8");
    // Node keeps 64 KiB of a piped write and drops the rest on process.exit().
    expect(stdout.length).toBeGreaterThan(64 * 1024);
    expect(text.endsWith("\n")).toBe(true);
    expect(text).toBe(expectedSchema(yangPath));
    expect(JSON.parse(text).properties.top.properties.field_799.description).toContain("field 799");
  });

  it("matches the library schema for examples/meta-model.yang", () => {
    const yangPath = join(tsRoot, "..", "examples", "meta-model.yang");
    const stdout = convertStdout(yangPath);
    expect(stdout.length).toBeGreaterThan(64 * 1024);
    expect(stdout.toString("utf-8")).toBe(expectedSchema(yangPath));
  });
});
