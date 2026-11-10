// Bundle bench/parse.bench.ts and run it with Node. `--cpu-prof` writes profiles to bench/profiles/.
import { build } from "esbuild";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outfile = join(mkdtempSync(join(tmpdir(), "xyang-bench-")), "parse.bench.mjs");
await build({
  absWorkingDir: tsRoot,
  entryPoints: [resolve(tsRoot, "bench/parse.bench.ts")],
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node22",
  outfile,
  logLevel: "silent"
});

const args = process.argv.slice(2);
const nodeArgs = [];
if (args.includes("--cpu-prof")) {
  const dir = resolve(tsRoot, "bench/profiles");
  mkdirSync(dir, { recursive: true });
  nodeArgs.push("--cpu-prof", `--cpu-prof-dir=${dir}`);
}
const result = spawnSync(process.execPath, [...nodeArgs, outfile, ...args.filter((a) => a !== "--cpu-prof")], {
  stdio: "inherit",
  env: { ...process.env, XYANG_REPO_ROOT: resolve(tsRoot, "..") }
});
process.exit(result.status ?? 1);
