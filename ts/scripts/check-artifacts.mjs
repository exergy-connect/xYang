import { existsSync } from "node:fs";
import { resolve } from "node:path";

const required = ["dist/index.js", "dist/index.d.ts", "dist/index.umd.min.global.js"];
const missing = required.filter((path) => !existsSync(resolve(process.cwd(), path)));

if (missing.length > 0) {
  console.error("Missing build artifacts:");
  for (const file of missing) {
    console.error(`- ${file}`);
  }
  process.exit(1);
}

console.log("All expected build artifacts are present.");
