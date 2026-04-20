import { build } from "esbuild";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(fileURLToPath(import.meta.url));
const tsRoot = resolve(rootDir, "..");
const fsShim = resolve(tsRoot, "src/shims/node-fs-browser.ts");
const pathShim = resolve(tsRoot, "src/shims/node-path-browser.ts");

/** @type {import("esbuild").Plugin} */
const browserBuiltinShims = {
  name: "xyang-browser-builtin-shims",
  setup(b) {
    b.onResolve({ filter: /^node:fs$/ }, () => ({ path: fsShim }));
    b.onResolve({ filter: /^fs$/ }, () => ({ path: fsShim }));
    b.onResolve({ filter: /^node:path$/ }, () => ({ path: pathShim }));
  }
};

await build({
  absWorkingDir: tsRoot,
  entryPoints: [resolve(tsRoot, "src/index.ts")],
  bundle: true,
  platform: "browser",
  format: "iife",
  globalName: "xYang",
  minify: true,
  target: "es2022",
  outfile: resolve(tsRoot, "dist/index.umd.min.global.js"),
  sourcemap: true,
  logLevel: "info",
  plugins: [browserBuiltinShims]
});

console.log("Browser IIFE written to dist/index.umd.min.global.js");
