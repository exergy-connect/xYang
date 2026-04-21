import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseYangFile } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_MODEL_YANG = join(__dirname, "../../../examples/meta-model.yang");

function collectInvalidPropertyKeys(node: unknown, out: string[]): void {
  if (!node || typeof node !== "object" || Array.isArray(node)) {
    return;
  }
  const obj = node as Record<string, unknown>;
  const props = obj.properties;
  if (props && typeof props === "object" && !Array.isArray(props)) {
    for (const key of Object.keys(props as Record<string, unknown>)) {
      // YANG identifiers cannot be XPath expressions; these showed up when MUST
      // statements were accidentally serialized as JSON properties.
      if (key.includes("/") || key.includes("(") || key.includes(")")) {
        out.push(key);
      }
      collectInvalidPropertyKeys((props as Record<string, unknown>)[key], out);
    }
  }
  for (const value of Object.values(obj)) {
    collectInvalidPropertyKeys(value, out);
  }
}

describe("meta-model target: schema converter", () => {
  it("does not emit XPath/must expressions as JSON property names", () => {
    const module = parseYangFile(META_MODEL_YANG);
    const schema = generateJsonSchema(module);
    const invalid: string[] = [];
    collectInvalidPropertyKeys(schema, invalid);
    expect(invalid).toEqual([]);
  });

  it("emits minItems/maxItems for computed.fields list", () => {
    const module = parseYangFile(META_MODEL_YANG);
    const schema = generateJsonSchema(module);

    const dm = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    const entities = (dm.properties as Record<string, unknown>).entities as Record<string, unknown>;
    const entityItems = entities.items as Record<string, unknown>;
    const fieldDefinitions = (entityItems.properties as Record<string, unknown>).field_definitions as Record<string, unknown>;
    const fieldDefItems = fieldDefinitions.items as Record<string, unknown>;
    const computed = (fieldDefItems.properties as Record<string, unknown>).computed as Record<string, unknown>;
    const fields = (computed.properties as Record<string, unknown>).fields as Record<string, unknown>;

    expect(fields.minItems).toBe(2);
    expect(fields.maxItems).toBe(100);
  });

  it("preserves must description text", () => {
    const module = parseYangFile(META_MODEL_YANG);
    const schema = generateJsonSchema(module);

    const dm = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    const allowUnlimited = (dm.properties as Record<string, unknown>).allow_unlimited_fields as Record<string, unknown>;
    const xYang = allowUnlimited["x-yang"] as Record<string, unknown>;
    const must = (xYang.must as Array<Record<string, unknown>>)[0];

    expect(typeof must.description).toBe("string");
    expect((must.description as string).length).toBeGreaterThan(0);
  });
});
