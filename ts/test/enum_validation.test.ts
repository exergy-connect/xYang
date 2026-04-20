import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { YangSyntaxError } from "../src/core/errors";
import { parseYangFile, parseYangString, YangValidator } from "../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_MODEL_YANG = join(__dirname, "../../examples/meta-model.yang");

/** Inline module: full schema path is visible to the validator (no unexpanded `uses`). */
const ENUM_LEAF_MODULE = `
module enum-val-test {
  yang-version 1.1;
  namespace "urn:test:enum-val";
  prefix "ev";

  container data {
    leaf status {
      type enumeration {
        enum active;
        enum inactive;
        enum pending;
      }
    }
  }
}
`;

describe("python parity: test_enum_validation", () => {
  it("rejects invalid enum value on instance leaf", () => {
    const module = parseYangString(ENUM_LEAF_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { status: "not_a_member" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.some((e) => e.toLowerCase().includes("enum"))).toBe(true);
  });

  it("accepts valid enum value on instance leaf", () => {
    const module = parseYangString(ENUM_LEAF_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { status: "active" } });

    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("parses examples/meta-model.yang with grouping uses expansion", () => {
    const module = parseYangFile(META_MODEL_YANG);
    expect(module.name).toBe("meta-model");
    expect(module.findStatement("data-model")).toBeDefined();
  });

  it("rejects empty enumeration type body (RFC 7950)", () => {
    const yang = `
module test_empty_enum {
  yang-version 1.1;
  namespace "urn:test:empty-enum";
  prefix "t";

  leaf x {
    type enumeration {
    }
  }
}
`;
    try {
      parseYangString(yang);
      expect.fail("expected parse to throw");
    } catch (e) {
      expect(e).toBeInstanceOf(YangSyntaxError);
      expect(String((e as Error).message).toLowerCase()).toContain("enum");
    }
  });
});
