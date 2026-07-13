import { existsSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "../..");
const required = [
  "artifacts/xyang-ts.mjs",
  "docs/xyang.umd.min.js"
];

const missing = required.filter((path) => !existsSync(resolve(repoRoot, path)));

if (missing.length > 0) {
  console.error("Missing CI build artifacts:");
  for (const file of missing) {
    console.error(`- ${file}`);
  }
  process.exit(1);
}

console.log("All expected CI build artifacts are present.");
