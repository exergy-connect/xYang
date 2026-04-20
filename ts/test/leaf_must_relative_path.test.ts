import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container top {
    leaf flag {
      type int32;
      default 0;
    }
    list items {
      key id;
      leaf id { type int32; }
      leaf ref_rel {
        type string;
        must "../../flag = 1";
      }
    }
  }
}
`;

describe("python parity: test_leaf_must_relative_path", () => {
  it("accepts ref_rel when top/flag = 1 (must ../../flag = 1)", () => {
    const module = parseYangString(YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      top: {
        flag: 1,
        items: [{ id: 1, ref_rel: "ok" }]
      }
    });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });

  it("rejects ref_rel when top/flag = 0", () => {
    const module = parseYangString(YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      top: {
        flag: 0,
        items: [{ id: 1, ref_rel: "bad" }]
      }
    });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("ref_rel"))).toBe(true);
  });
});
