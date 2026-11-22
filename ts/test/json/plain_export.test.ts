import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";
import { parseConvertArgs } from "../../src/cli/args";

const module = parseYangString(`module p { namespace "urn:p"; prefix p;
  typedef amount { type decimal64 { fraction-digits 2; } description "Money."; }
  container top {
    leaf x-tag { type string; description "Named like an extension keyword."; }
    leaf price { type amount; }
    leaf kind { type enumeration { enum a; enum b; } }
    list items { key "id"; leaf id { type uint8; } }
  }
}`);

const NAME_MAPS = new Set(["properties", "patternProperties", "$defs", "dependentSchemas"]);
/** Every object key that is a schema keyword, skipping data-name maps. */
function keywords(value: unknown, names = false): Set<string> {
  const found = new Set<string>();
  if (Array.isArray(value)) for (const child of value) for (const key of keywords(child)) found.add(key);
  else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (!names) found.add(key);
      for (const nested of keywords(child, !names && NAME_MAPS.has(key))) found.add(nested);
    }
  }
  return found;
}
const extensions = (schema: unknown) => [...keywords(schema)].filter(key => key.startsWith("x-"));
type Obj = Record<string, any>;

describe("plain JSON Schema export (xYang: false)", () => {
  it("omits xYang keywords and keeps the schema", () => {
    const full = generateJsonSchema(module).schema;
    const plain = generateJsonSchema(module, { xYang: false }).schema as Obj;
    expect(extensions(full)).toContain("x-yang");
    expect(extensions(plain)).toEqual([]);
    const top = plain.properties.top;
    expect(top.properties["x-tag"].description).toBe("Named like an extension keyword.");
    expect(top.properties.kind.enum).toEqual(["a", "b"]);
    expect(plain.$defs.amount.description).toBe("Money.");
    expect(top.properties.items.type).toBe("array");
    expect(generateJsonSchema(module).schema).toEqual(full);
  });
  it("projects a subtree before removing annotations", () => {
    const annotated = generateJsonSchema(module, { path: "/p:top/p:items" });
    const plain = generateJsonSchema(module, { path: "/p:top/p:items", xYang: false });
    expect(plain.diagnostics).toEqual(annotated.diagnostics);
    expect((plain.schema as Obj).type).toBe("array");
    expect(extensions(plain.schema)).toEqual([]);
  });
  it("cannot be read back as YANG", () => {
    expect(() => parseJsonSchema(generateJsonSchema(module, { xYang: false }).schema)).toThrow();
  });
  it("parses convert --no-x-yang and rejects it with JSON-LD", () => {
    expect(parseConvertArgs(["--no-x-yang", "m.yang"])).toMatchObject({ xYang: false, positional: ["m.yang"] });
    expect(() => parseConvertArgs(["--jsonld", "--no-x-yang", "m.yang"])).toThrow(/JSON-LD/);
  });
});
