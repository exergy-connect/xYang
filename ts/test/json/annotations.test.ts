import { expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator, validate } from "../../src";
const module = parseYangString(`module m { namespace "urn:m"; prefix m;
  leaf name { type string; mandatory true; }
  container top { list items { key id; leaf id { type string; } } }
  container mode { choice mode { leaf a { type string; } leaf b { type string; } } }
}`);
it.each([[true,true],[false,true],[true,false],[false,false]])("annotation schema policy (#225): %s %s", (allowJsonld, allowJsonSchema) => {
  const options = { allowJsonld, allowJsonSchema };
  const schema = generateJsonSchema(module, options);
  const props = schema.properties as Record<string, Record<string, unknown>>;
  const items = ((props.top.properties as Record<string, Record<string, unknown>>).items.items) as Record<string, unknown>;
  const patterns = [...(allowJsonld ? ["^@[A-Za-z]+$"] : []), ...(allowJsonSchema ? ["^\\$[A-Za-z]+$"] : [])];
  for (const obj of [schema, props.top, items]) {
    expect(Object.keys((obj.patternProperties as object) ?? {})).toEqual(patterns);
    expect(obj.additionalProperties).toBe(false);
  }
  expect(generateJsonSchema(parseJsonSchema(schema), options)).toEqual(schema);
});
it("keeps annotation policy per call without mutating data (#225)", () => {
  const data = { name: "ok", "@context": { opaque: { missing: "not walked" } } };
  const before = JSON.stringify(data);
  const validator = new YangValidator(module);
  expect(validator.validate(data).isValid).toBe(true);
  expect(validator.validateDetailed(data, { allowJsonld: false }).valid).toBe(false);
  expect(validator.validateDetailed(data).valid).toBe(true);
  expect(validate(module, data, { allowJsonld: false }).valid).toBe(false);
  expect(JSON.stringify(data)).toBe(before);
});
