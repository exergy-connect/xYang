import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tsRoot = resolve(__dirname, "..");
const repoRoot = resolve(tsRoot, "..");
const src = resolve(tsRoot, "dist/index.umd.min.global.js");
const dest = resolve(repoRoot, "docs/xyang.umd.min.js");

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log(`Synced browser bundle to ${dest}`);
