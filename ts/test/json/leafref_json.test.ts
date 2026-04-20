import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator } from "../../src";
import { XPathSyntaxError } from "../../src/core/errors";

function makeSchema(path: string): Record<string, unknown> {
  return {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: "urn:test:leafref-json",
    description: "Minimal schema for leafref path tests",
    "x-yang": {
      module: "leafref-json-test",
      "yang-version": "1.1",
      namespace: "urn:test:leafref-json",
      prefix: "lr"
    },
    type: "object",
    properties: {
      "data-model": {
        type: "object",
        description: "Root container",
        "x-yang": { type: "container" },
        properties: {
          target: {
            type: "string",
            description: "Target value referenced by ref",
            "x-yang": { type: "leaf" }
          },
          ref: {
            type: "string",
            description: "Leafref to /data-model/target",
            "x-yang": {
              type: "leafref",
              path,
              "require-instance": true
            }
          }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
}

function validate(schema: Record<string, unknown>, data: Record<string, unknown>) {
  const module = parseJsonSchema(schema);
  const result = new YangValidator(module).validate(data);
  return { isValid: result.isValid, errors: result.errors };
}

describe("python parity: json/test_leafref_json", () => {
  it("accepts valid leafref path when target exists", () => {
    const schema = makeSchema("/data-model/target");
    const data = { "data-model": { target: "x", ref: "x" } };

    const result = validate(schema, data);
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });

  it("rejects data when leafref target is missing", () => {
    const schema = makeSchema("/data-model/target");
    const data = { "data-model": { ref: "x" } };

    const result = validate(schema, data);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => /leafref|require-instance/i.test(e))).toBe(true);
  });

  it("throws XPathSyntaxError for invalid leafref path expression", () => {
    const schema = makeSchema("/data-model/target[");

    expect(() => parseJsonSchema(schema)).toThrow(XPathSyntaxError);
  });

  it("emits integer JSON type for leafref to integer target leaf", () => {
    const module = parseYangString(`
module lr-int {
  yang-version 1.1;
  namespace "urn:lr-int";
  prefix "lri";
  container data-model {
    leaf port {
      type int32;
    }
    leaf peer {
      type leafref {
        path "/data-model/port";
      }
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const peer = (((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
      .properties as Record<string, unknown>).peer as Record<string, unknown>;

    expect(peer.type).toBe("integer");
    expect((peer["x-yang"] as Record<string, unknown>).type).toBe("leafref");
    expect((peer["x-yang"] as Record<string, unknown>).path).toBe("/data-model/port");

    const round = parseJsonSchema(schema);
    const result = new YangValidator(round).validate({ "data-model": { port: 42, peer: 42 } });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });
});
