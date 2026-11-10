import { describe, expect, it } from "vitest";
import { parseJsonSchema } from "../../src";

const ROOT_MESSAGE =
  'JSON Schema has no root "x-yang" annotation; xYang needs a .yang.json produced by "xyang convert" (see design/json-schema-xyang-profile.md)';
const PROPERTY_MESSAGE = 'JSON Schema property "city" has no "x-yang" annotation';

const plain = { type: "object", properties: { city: { type: "string" } } };
const bareProperty = {
  type: "object",
  "x-yang": { module: "example", namespace: "urn:example", prefix: "ex" },
  properties: { city: { type: "string" } }
};

describe("plain JSON Schema is rejected (#80)", () => {
  it("raises when the root has no x-yang", () => {
    expect(() => parseJsonSchema(plain)).toThrow(ROOT_MESSAGE);
  });

  it("raises when a root property has no x-yang", () => {
    expect(() => parseJsonSchema(bareProperty)).toThrow(PROPERTY_MESSAGE);
  });
});
