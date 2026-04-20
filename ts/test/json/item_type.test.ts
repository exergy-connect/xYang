import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile, YangValidator } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_MODEL_YANG = join(__dirname, "../../../examples/meta-model.yang");
const META_MODEL_YANG_JSON = join(__dirname, "../../../examples/meta-model.yang.json");

function minimalDataModel(entities: unknown[]): Record<string, unknown> {
  return {
    "data-model": {
      name: "M",
      version: "25.03.11.1",
      author: "A",
      description: "Minimal model for item_type encoding tests.",
      consolidated: false,
      max_name_underscores: 2,
      entities
    }
  };
}

const DATA_ITEM_TYPE_PRIMITIVE_VALID = minimalDataModel([
  {
    name: "e",
    description: "Entity with string array field.",
    primary_key: "id",
    fields: [
      {
        name: "id",
        description: "Primary key.",
        type: { primitive: "integer" }
      },
      {
        name: "tags",
        description: "Tag strings.",
        type: { array: { primitive: "string" } }
      }
    ]
  }
]);

const DATA_ITEM_TYPE_ENTITY_VALID = minimalDataModel([
  {
    name: "server",
    description: "Server entity.",
    primary_key: "id",
    fields: [{ name: "id", description: "Server id.", type: { primitive: "integer" } }]
  },
  {
    name: "client",
    description: "Client with FK array to servers.",
    primary_key: "id",
    fields: [
      { name: "id", description: "Client id.", type: { primitive: "integer" } },
      {
        name: "servers",
        description: "Attached servers.",
        type: { array: { entity: "server" } }
      }
    ]
  }
]);

const DATA_ITEM_TYPE_EMPTY_INVALID = minimalDataModel([
  {
    name: "e",
    description: "Entity with empty array type branch.",
    primary_key: "id",
    fields: [
      { name: "id", description: "Primary key.", type: { primitive: "integer" } },
      { name: "tags", description: "Tags.", type: { array: {} } }
    ]
  }
]);

const DATA_ITEM_TYPE_WHEN_FALSE_INVALID = minimalDataModel([
  {
    name: "e",
    description: "Entity with invalid item_type on primitive field.",
    primary_key: "id",
    fields: [
      { name: "id", description: "Primary key.", type: { primitive: "integer" } },
      {
        name: "title",
        description: "Title string.",
        type: { primitive: "string" },
        item_type: { primitive: "string" }
      }
    ]
  }
]);

function loadModules() {
  return {
    fromYang: parseYangFile(META_MODEL_YANG),
    fromJson: parseJsonSchema(JSON.parse(readFileSync(META_MODEL_YANG_JSON, "utf-8")) as Record<string, unknown>)
  };
}

function validate(moduleData: ReturnType<typeof loadModules>["fromYang"], data: Record<string, unknown>) {
  const result = new YangValidator(moduleData).validate(data);
  return { isValid: result.isValid, errors: result.errors };
}

describe("python parity: json/test_item_type", () => {
  it("accepts item_type.primitive for array fields in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_ITEM_TYPE_PRIMITIVE_VALID);
    const j = validate(fromJson, DATA_ITEM_TYPE_PRIMITIVE_VALID);

    expect(y.isValid, y.errors.join("\n")).toBe(true);
    expect(j.isValid, j.errors.join("\n")).toBe(true);
  });

  it("accepts item_type.entity for array fields in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_ITEM_TYPE_ENTITY_VALID);
    const j = validate(fromJson, DATA_ITEM_TYPE_ENTITY_VALID);

    expect(y.isValid, y.errors.join("\n")).toBe(true);
    expect(j.isValid, j.errors.join("\n")).toBe(true);
  });

  it("rejects empty item_type under array in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_ITEM_TYPE_EMPTY_INVALID);
    const j = validate(fromJson, DATA_ITEM_TYPE_EMPTY_INVALID);

    expect(y.isValid).toBe(j.isValid);
    expect(y.isValid, y.errors.join("\n")).toBe(false);
    expect(y.errors.length).toBeGreaterThan(0);
    expect(j.errors.length).toBeGreaterThan(0);
  });

  it("rejects item_type when type is not array in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_ITEM_TYPE_WHEN_FALSE_INVALID);
    const j = validate(fromJson, DATA_ITEM_TYPE_WHEN_FALSE_INVALID);

    expect(y.isValid).toBe(j.isValid);
    expect(y.isValid, y.errors.join("\n")).toBe(false);
    expect(y.errors.some((e) => e.toLowerCase().includes("item_type"))).toBe(true);
    expect(j.errors.some((e) => e.toLowerCase().includes("item_type"))).toBe(true);
  });
});
