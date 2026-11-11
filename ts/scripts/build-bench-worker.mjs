// Bundle bench/worker.ts (library from src/) into one ESM file for benchmarks/release_bench.py.
// Usage: node scripts/build-bench-worker.mjs <outfile>
import { build } from "esbuild";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const outfile = process.argv[2];
if (!outfile) {
  console.error("usage: node scripts/build-bench-worker.mjs <outfile>");
  process.exit(2);
}
const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
await build({
  absWorkingDir: tsRoot,
  entryPoints: [resolve(tsRoot, "bench/worker.ts")],
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node24",
  outfile: resolve(outfile),
  logLevel: "warning"
});
