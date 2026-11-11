import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { describe, expect, it } from "vitest";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const MODULE = `
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type int64; }
    }
    leaf marker { type empty; }
  }
}
`;

const NATIVE = { top: { interface: { eth0: { mtu: 1500 } }, marker: null } };

describe("native json", () => {
  it("rejects the repro by default and accepts --native-json", async () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-native-"));
    const yang = join(dir, "m.yang");
    const data = join(dir, "data.json");
    writeFileSync(yang, MODULE);
    writeFileSync(data, JSON.stringify(NATIVE));
    const cli = join(dir, "cli.mjs");
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
    const rejected = spawnSync(process.execPath, [cli, "validate", "--format", "json", yang, data], {
      encoding: "utf-8"
    });
    expect(rejected.status).toBe(1);
    expect(JSON.parse(rejected.stdout).valid).toBe(false);
    const accepted = spawnSync(
      process.execPath,
      [cli, "validate", "--native-json", "--format", "json", yang, data],
      { encoding: "utf-8" }
    );
    expect(accepted.status).toBe(0);
    expect(JSON.parse(accepted.stdout).valid).toBe(true);
  });
});
