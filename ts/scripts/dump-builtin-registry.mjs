import * as esbuild from "esbuild";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const outfile = join(tmpdir(), "xyang-builtin-registry.mjs");
await esbuild.build({
  absWorkingDir: new URL("..", import.meta.url).pathname,
  entryPoints: ["src/types/registry.ts"],
  bundle: true,
  format: "esm",
  platform: "node",
  outfile,
  logLevel: "silent"
});
const mod = await import(pathToFileURL(outfile).href);
process.stdout.write(JSON.stringify(mod.registryParitySnapshot()));
