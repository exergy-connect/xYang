import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { beforeAll, afterAll, expect, it } from "vitest";
const dir = mkdtempSync(join(tmpdir(),"xyang-jsonld-"));
const cli = join(dir,"cli.mjs");
beforeAll(async () => {
  await build({ entryPoints:[resolve(__dirname,"../src/cli.ts")], bundle:true, platform:"node", format:"esm", target:"node22", outfile:cli, logLevel:"silent" });
});
afterAll(() => rmSync(dir,{recursive:true,force:true}));
it.each(["context","vocab"])("prints complete JSON-LD on stdout (#229): %s", (kind) => {
  const example = resolve(__dirname,"../../examples/jsonld");
  const result = spawnSync(process.execPath,[cli,"convert",kind === "context" ? "--jsonld" : "--jsonld-vocab",join(example,"catalog.yang")],{encoding:"utf8"});
  expect(result.status,result.stderr).toBe(0);
  expect(result.stderr).toBe("");
  expect(JSON.parse(result.stdout)).toEqual(JSON.parse(readFileSync(join(example,`catalog.${kind}.jsonld`),"utf8")));
});
