import { expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";
import { parseConvertArgs } from "../../src/cli/args";

const module = parseYangString('module m { namespace "urn:m"; prefix m; leaf name { type string; } }');
it.each([undefined, "https://example.invalid/m.schema.json", ""])("schemaId preserves the namespace (#227): %s", (schemaId) => {
  const schema = generateJsonSchema(module, { schemaId }).schema;
  expect(schema.$id).toBe(schemaId ?? "urn:m");
  expect((schema["x-yang"] as Record<string, unknown>).namespace).toBe("urn:m");
  expect(parseJsonSchema(schema).namespace).toBe("urn:m");
  expect(generateJsonSchema(module).schema.$id).toBe("urn:m");
});
it("parses convert --schema-id (#227)", () => {
  expect(parseConvertArgs(["--schema-id", "https://example.invalid/m.json", "m.yang"]))
    .toMatchObject({ schemaId: "https://example.invalid/m.json", positional: ["m.yang"] });
});
