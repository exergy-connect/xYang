import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema } from "../src";

function schemaFor(context: string[], scope: unknown, kind = "leaf"): Record<string, unknown> {
  const ref = { $ref: "#/$defs/code" };
  let leaf: Record<string, unknown> = { ...ref, "x-yang": { type: "leaf" } };
  if (kind === "leaf-list") leaf = { type: "array", items: ref, "x-yang": { type: "leaf-list" } };
  if (kind === "union") leaf = { oneOf: [ref, { type: "boolean" }], "x-yang": { type: "leaf" } };
  let properties: Record<string, unknown> = { value: leaf };
  for (const name of [...context].reverse()) properties = { [name]: { type: "object", properties, "x-yang": { type: "container" } } };
  return { "x-yang": { module: "m", namespace: "urn:m", prefix: "m" }, $defs: { code: { type: "string", "x-yang": scope === undefined ? {} : { scope } } }, properties };
}

describe("native JSON global typedef scope", () => {
  it.each([
    [["a"], "/a", "leaf", true],
    [["a~b"], "/a~0b", "leaf", true],
    [["a", "child"], "/a", "leaf", true],
    [["b"], "/a", "leaf", false],
    [["ab"], "/a", "leaf", false],
    [[], "/a", "leaf", false],
    [["b"], undefined, "leaf", true],
    [["a"], "/a", "leaf-list", true],
    [["b"], "/a", "leaf-list", false],
    [["a"], "/a", "union", true],
    [["b"], "/a", "union", false]
  ] as Array<[string[], unknown, string, boolean]>)("context %j scope %j %s allowed %s", (context, scope, kind, allowed) => {
    const schema = schemaFor(context, scope, kind);
    if (!allowed) {
      expect(() => parseJsonSchema(schema)).toThrow("Unknown typedef");
      return;
    }
    const exported = generateJsonSchema(parseJsonSchema(schema));
    expect((exported.$defs as Record<string, Record<string, Record<string, unknown>>>).code["x-yang"]?.scope).toBe(scope);
    expect(() => parseJsonSchema(exported)).not.toThrow();
  });
  it.each([null, 42, "", "a", "/a/", "/a//b", "/a~2b"])("rejects malformed scope %j", (scope) => {
    expect(() => parseJsonSchema(schemaFor(["a"], scope))).toThrow("typedef scope");
  });
});

it("re-export retains distinct keys for identical private names from two modules", () => {
  const source = JSON.parse(readFileSync(new URL("../../tests/cases/types/typedef-scope-imported-collisions/expected.yang.json", import.meta.url), "utf8"));
  const first = generateJsonSchema(parseJsonSchema(source));
  expect(first).toEqual(source);
  const second = generateJsonSchema(parseJsonSchema(first));
  expect(second).toEqual(first);
  const properties = second.properties as Record<string, { properties: { value: { $ref: string } } }>;
  expect(properties.a.properties.value.$ref).not.toBe(properties.b.properties.value.$ref);
});
