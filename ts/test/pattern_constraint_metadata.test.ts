import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator } from "../src";
import { YANG_SCHEMA_KEYS } from "../src/json/schema-keys";

const PATTERN_TYPEDEF_MODULE = `
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[0-9]+' {
        error-message "Must be decimal digits.";
        error-app-tag "t:bad-id";
      }
    }
  }
  container data-model {
    leaf x { type id; }
  }
}
`;

describe("python parity: test_pattern_constraint_metadata", () => {
  it("parse stores pattern and error metadata on typedef type", () => {
    const module = parseYangString(PATTERN_TYPEDEF_MODULE);
    const td = module.typedefs.id as { type?: Record<string, unknown> } | undefined;
    expect(td?.type).toBeDefined();
    expect(td?.type?.pattern).toBe("[0-9]+");
    expect(td?.type?.pattern_error_message).toBe("Must be decimal digits.");
    expect(td?.type?.pattern_error_app_tag).toBe("t:bad-id");
  });

  it("validate uses pattern error-message and error-app-tag", () => {
    const module = parseYangString(PATTERN_TYPEDEF_MODULE);
    const v = new YangValidator(module);
    const { isValid, errors } = v.validate({ "data-model": { x: "abc" } });
    expect(isValid).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
    const joined = errors.join(" ");
    expect(joined).toContain("Must be decimal digits.");
    expect(joined).toContain("error-app-tag: t:bad-id");
  });

  it("JSON Schema x-yang carries pattern metadata on typedef $def", () => {
    const module = parseYangString(PATTERN_TYPEDEF_MODULE);
    const schema = generateJsonSchema(module);
    const idDef = schema.$defs as Record<string, Record<string, unknown>>;
    const xy = idDef.id[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>;
    expect(xy["pattern-error-message"]).toBe("Must be decimal digits.");
    expect(xy["pattern-error-app-tag"]).toBe("t:bad-id");
  });

  it("JSON roundtrip restores pattern metadata on typedef", () => {
    const module = parseYangString(PATTERN_TYPEDEF_MODULE);
    const schema = generateJsonSchema(module);
    const module2 = parseJsonSchema(schema);
    const td = module2.typedefs.id as { type?: Record<string, unknown> } | undefined;
    expect(td?.type?.pattern_error_message).toBe("Must be decimal digits.");
    expect(td?.type?.pattern_error_app_tag).toBe("t:bad-id");
  });
});
