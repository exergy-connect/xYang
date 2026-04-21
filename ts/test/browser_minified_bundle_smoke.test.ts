import { createContext, runInContext } from "node:vm";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const minifiedBundlePath = resolve(__dirname, "../dist/index.umd.min.global.js");

type XyIndexModule = typeof import("../src/index");

/**
 * Regression: AST serialization used `constructor.name`, which esbuild minify rewrites so YANG
 * `keyword` values became wrong and validation silently broke. The bundle must reject bad data.
 */
describe("minified browser bundle (IIFE)", () => {
  it.skipIf(!existsSync(minifiedBundlePath))("parses schema and validates uint64", () => {
    const code = readFileSync(minifiedBundlePath, "utf8");
    const sandbox = { console } as { xYang?: XyIndexModule; console: typeof console };
    runInContext(code, createContext(sandbox));
    expect(sandbox.xYang).toBeDefined();
    const x = sandbox.xYang!;
    const yang = `module a {
  yang-version 1.1;
  namespace "urn:xyang:test:min-bundle";
  prefix t;
  leaf n { type uint64; }
}`;
    const mod = x.parseYangString(yang);
    const v = new x.YangValidator(mod);
    expect(v.validate({ n: -1 }).isValid).toBe(false);
    expect(v.validate({ n: 42 }).isValid).toBe(true);
  });
});
