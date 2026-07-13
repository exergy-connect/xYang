import { build } from "esbuild";
import { chmodSync, copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const tsRoot = resolve(scriptsDir, "..");
const repoRoot = resolve(tsRoot, "..");
const artifactsDir = resolve(repoRoot, "artifacts");
const cliArtifact = resolve(artifactsDir, "xyang-ts.mjs");
const browserDist = resolve(tsRoot, "dist/index.umd.min.global.js");
const browserDocs = resolve(repoRoot, "docs/xyang.umd.min.js");
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

mkdirSync(artifactsDir, { recursive: true });
mkdirSync(dirname(browserDist), { recursive: true });

await build({
  absWorkingDir: tsRoot,
  entryPoints: [resolve(tsRoot, "src/cli.ts")],
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node24",
  outfile: cliArtifact,
  banner: { js: "#!/usr/bin/env node" },
  minifySyntax: true,
  minifyWhitespace: true,
  sourcemap: false,
  logLevel: "info"
});
chmodSync(cliArtifact, 0o755);
console.log(`CLI bundle written to ${cliArtifact}`);

await build({
  absWorkingDir: tsRoot,
  entryPoints: [resolve(tsRoot, "src/index.ts")],
  bundle: true,
  platform: "browser",
  format: "iife",
  globalName: "xYang",
  minifyIdentifiers: false,
  minifySyntax: true,
  minifyWhitespace: true,
  target: "es2022",
  outfile: browserDist,
  sourcemap: false,
  logLevel: "info",
  plugins: [browserBuiltinShims]
});
console.log(`Browser IIFE written to ${browserDist}`);

mkdirSync(dirname(browserDocs), { recursive: true });
copyFileSync(browserDist, browserDocs);
console.log(`Synced browser bundle to ${browserDocs}`);
