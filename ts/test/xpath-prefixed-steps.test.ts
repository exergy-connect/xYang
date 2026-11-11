import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangParser, YangValidator } from "../src";

// Prefixed XPath steps resolve by module, also after the native JSON round trip.
// Shared cases: tests/cases/xpath/prefixed-steps (and the unknown-prefix cases next to it).

const CASE = resolve(dirname(fileURLToPath(import.meta.url)), "../../tests/cases/xpath/prefixed-steps");

function loadCase() {
  const parser = new YangParser({ includePath: [CASE], expandUses: true });
  const module = parser.parseFile(join(CASE, "m.yang"));
  for (const file of readdirSync(CASE)) {
    if (file.endsWith(".yang") && file !== "m.yang") parser.parseFile(join(CASE, file));
  }
  return module;
}

type Instance = { name: string; data: unknown; valid: boolean; encoding?: string; errors?: Array<{ path: string; code: string }> };
const instances: Instance[] = JSON.parse(readFileSync(join(CASE, "case.json"), "utf8")).instances;
const pairs = (errors: Array<{ path: string; code: string }>) => errors.map((e) => `${e.path} ${e.code}`).sort();

describe("prefixed XPath steps after the native JSON round trip", () => {
  const schema = generateJsonSchema(loadCase());
  const roundTripped = parseJsonSchema(schema);

  it("records the module of each prefix and qualifies augmented members", () => {
    const sys = (schema.properties as Record<string, any>).sys;
    expect(Object.keys(sys.properties)).toEqual(expect.arrayContaining(["name", "ext:name", "ext:tag", "ext:iref"]));
    expect(sys.properties["ext:tag"]["x-yang"].must[0]["xpath-prefixes"]).toEqual({ e: "ext", mm: "m" });
    expect(sys.properties["ext:iref"]["x-yang"]["xpath-prefixes"]).toEqual({ mm: "m" });
    expect(generateJsonSchema(roundTripped)).toEqual(schema);
  });

  it.each(instances.map((inst) => [inst.name, inst] as const))("%s", (_name, inst) => {
    const result = new YangValidator(roundTripped).validateDetailed(inst.data, { nativeJson: inst.encoding === "native" });
    expect(pairs(result.errors)).toEqual(pairs(inst.errors ?? []));
    expect(result.valid).toBe(inst.valid);
  });

  it("a JSON form without a recorded map binds only the module's own prefix", () => {
    const own = parseYangString(`module m { yang-version 1.1; namespace "urn:m"; prefix m;
      container top { leaf a { type string; must "/m:top/m:b = 'y'"; } leaf b { type string; } } }`);
    const json = generateJsonSchema(own) as any;
    delete json.properties.top.properties.a["x-yang"].must[0]["xpath-prefixes"];
    const parsed = parseJsonSchema(json);
    expect(new YangValidator(parsed).validateDetailed({ "m:top": { a: "x", b: "y" } }).valid).toBe(true);
    json.properties.top.properties.a["x-yang"].must[0].must = "/x:top/x:b = 'y'";
    expect(() => parseJsonSchema(json)).toThrow("unknown prefix 'x'");
  });
});
