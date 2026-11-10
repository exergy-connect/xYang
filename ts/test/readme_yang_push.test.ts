import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { describe, expect, it } from "vitest";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(tsRoot, "..");

describe("README IETF YANG Push example", () => {
  it(
    "xyang-ts validate exits 0 and prints Valid.",
    async () => {
      const dir = mkdtempSync(join(tmpdir(), "xyang-push-"));
      const cli = join(dir, "cli.mjs");
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

      const result = spawnSync(
        process.execPath,
        [
          cli,
          "validate",
          "examples/ietf-yang-push/modules/ietf-yp-notification@2025-06-04.yang",
          "examples/ietf-yang-push/27-push-update.json",
          "--include-path",
          "examples/ietf-yang-push/modules",
          "--anydata-validation",
          "complete",
          "--anydata-module",
          "examples/ietf-yang-push/modules/ietf-yang-push@2019-09-09.yang",
          "--anydata-module",
          "examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang",
          "--anydata-module",
          "examples/ietf-yang-push/modules/ietf-yp-observation@2025-02-24.yang",
          "--anydata-module",
          "examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang",
          "--anydata-module",
          "examples/ietf-yang-push/modules/ietf-alarms-x733@2019-09-11.yang"
        ],
        { cwd: repoRoot, encoding: "utf-8" }
      );

      expect(result.status, `${result.stderr}\n${result.stdout}`).toBe(0);
      expect(result.stdout).toContain("Valid.");
    },
    180_000
  );
});