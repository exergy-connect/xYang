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
    const pats = td?.type?.patterns ?? [];
    expect(pats.length).toBe(1);
    expect(pats[0]?.pattern).toBe("[0-9]+");
    expect(pats[0]?.error_message).toBe("Must be decimal digits.");
    expect(pats[0]?.error_app_tag).toBe("t:bad-id");
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
    const pats = td?.type?.patterns ?? [];
    expect(pats.length).toBe(1);
    expect(pats[0]?.error_message).toBe("Must be decimal digits.");
    expect(pats[0]?.error_app_tag).toBe("t:bad-id");
  });

  it("parse stores pattern modifier and multiple pattern entries", () => {
    const module = parseYangString(`
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' {
        modifier invert-match;
        error-message "digits forbidden";
        error-app-tag "t:forbidden-digits";
      }
    }
  }
}
`);
    const td = module.typedefs.id as { type?: Record<string, unknown> } | undefined;
    const patterns = (td?.type?.patterns as Array<Record<string, unknown>> | undefined) ?? [];
    expect(patterns.length).toBe(2);
    expect(patterns[0].pattern).toBe("[a-z]+");
    expect(patterns[0].invert_match).toBe(false);
    expect(patterns[1].pattern).toBe("[0-9]+");
    expect(patterns[1].invert_match).toBe(true);
    expect(patterns[1].error_message).toBe("digits forbidden");
    expect(patterns[1].error_app_tag).toBe("t:forbidden-digits");
  });

  it("JSON schema emits allOf and string-patterns for invert-match", () => {
    const module = parseYangString(`
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' { modifier invert-match; }
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const idDef = (schema.$defs as Record<string, Record<string, unknown>>).id;
    expect(Array.isArray(idDef.allOf)).toBe(true);
    const xy = idDef[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>;
    const entries = (xy["string-patterns"] as Array<Record<string, unknown>> | undefined) ?? [];
    expect(entries.length).toBe(2);
    expect(entries[1]["invert-match"]).toBe(true);
  });

  it("JSON roundtrip restores invert-match entries", () => {
    const module = parseYangString(`
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' { modifier invert-match; }
    }
  }
}
`);
    const module2 = parseJsonSchema(generateJsonSchema(module));
    const td = module2.typedefs.id as { type?: Record<string, unknown> } | undefined;
    const patterns = (td?.type?.patterns as Array<Record<string, unknown>> | undefined) ?? [];
    expect(patterns.length).toBe(2);
    expect(patterns[0].invert_match).toBe(false);
    expect(patterns[1].invert_match).toBe(true);
  });
});
