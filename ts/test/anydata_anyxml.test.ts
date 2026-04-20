import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator } from "../src";
import { YangTokenType } from "../src/parser/parser-context";

describe("python parity: test_anydata_anyxml", () => {
  const moduleSource = `
module adax {
  yang-version 1.1;
  namespace "urn:adax";
  prefix adax;
  container data-model {
    anydata payload { description "free-form"; }
    anyxml legacy { mandatory true; }
    leaf tag { type string; }
  }
}
`;

  function createModule() {
    return parseYangString(moduleSource);
  }

  it("parses anydata and anyxml keywords in the module AST", () => {
    const module = createModule();
    const dataModel = module.findStatement("data-model");

    expect(dataModel).toBeDefined();

    const byName = new Map(
      (dataModel?.statements ?? [])
        .filter((statement) => typeof statement.name === "string")
        .map((statement) => [statement.name as string, statement])
    );

    expect(byName.get("payload")?.keyword).toBe(YangTokenType.ANYDATA);
    expect(byName.get("legacy")?.keyword).toBe(YangTokenType.ANYXML);
    expect(byName.get("legacy")?.data.mandatory).toBe(true);
  });

  it("accepts arbitrary JSON payload under anydata and anyxml", () => {
    const module = createModule();
    const validator = new YangValidator(module);

    const result = validator.validate({
      "data-model": {
        payload: { nested: [1, 2, null], ok: true },
        legacy: "plain string is fine",
        tag: "x"
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("reports missing mandatory anyxml field", () => {
    const module = createModule();
    const validator = new YangValidator(module);

    const result = validator.validate({
      "data-model": {
        tag: "x"
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]).toContain("legacy");
    expect(result.errors[0].toLowerCase()).toContain(YangTokenType.ANYXML);
  });

  it("round-trips anydata/anyxml through JSON schema metadata", () => {
    const module = createModule();
    const schema = generateJsonSchema(module);
    const dataModelSchema = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    const props = (dataModelSchema.properties as Record<string, unknown>) ?? {};
    const payloadSchema = props.payload as Record<string, unknown>;
    const legacySchema = props.legacy as Record<string, unknown>;

    expect((payloadSchema["x-yang"] as Record<string, unknown>).type).toBe(YangTokenType.ANYDATA);
    expect((legacySchema["x-yang"] as Record<string, unknown>).type).toBe(YangTokenType.ANYXML);
    expect(Array.isArray(payloadSchema.type)).toBe(true);

    const reparsed = parseJsonSchema(schema);
    const dataModel = reparsed.findStatement("data-model");
    const byName = new Map(
      (dataModel?.statements ?? [])
        .filter((statement) => typeof statement.name === "string")
        .map((statement) => [statement.name as string, statement])
    );

    expect(byName.get("payload")?.keyword).toBe(YangTokenType.ANYDATA);
    expect(byName.get("legacy")?.keyword).toBe(YangTokenType.ANYXML);
    expect(byName.get("legacy")?.data.mandatory).toBe(true);
  });
});
