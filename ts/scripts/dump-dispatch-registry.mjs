import * as esbuild from "esbuild";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const outfile = join(tmpdir(), "xyang-dispatch-registry.mjs");
await esbuild.build({
  absWorkingDir: new URL("..", import.meta.url).pathname,
  entryPoints: ["src/parser/dispatch-registry.ts"],
  bundle: true,
  format: "esm",
  platform: "node",
  outfile,
  logLevel: "silent"
});
const mod = await import(pathToFileURL(outfile).href);
process.stdout.write(JSON.stringify(mod.dispatchRegistryParitySnapshot()));
