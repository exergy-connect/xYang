import { expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";

it.each(["", "leaf value { type string; mandatory true; }", "choice mode { leaf enabled { type boolean; } leaf label { type string; } }"])(
  "requires list keys without explicit mandatory (#224): %s", (extra) => {
    const module = parseYangString(`module m { namespace "urn:m"; prefix m;
      list items { key "a b"; leaf a { type string; } leaf b { type uint8; } ${extra} } }`);
    const schema = generateJsonSchema(module);
    type ItemSchema = { required?: string[]; oneOf?: ItemSchema[] };
    const items = (schema.properties as Record<string, { items: ItemSchema }>).items.items;
    for (const branch of items.oneOf ?? [items]) {
      expect([...(items.required ?? []), ...(branch.required ?? [])]).toEqual(expect.arrayContaining(["a", "b"]));
    }
    const restored = parseJsonSchema(schema);
    expect(generateJsonSchema(restored)).toEqual(schema);
    for (const leaf of restored.statements[0].statements) {
      if (["a", "b"].includes(leaf.name ?? "")) expect(leaf.mandatory).toBeFalsy();
    }
  }
);
