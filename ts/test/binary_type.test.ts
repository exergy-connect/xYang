import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_binary_type", () => {
  const MODULE = `
module bin-test {
  yang-version 1.1;
  namespace "urn:test:bin";
  prefix "b";

  container top {
    leaf data {
      type binary {
        length "0..16";
      }
    }
  }
}
`;

  it("accepts valid base64 binary value", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);
    const base64 = Buffer.from("hello", "utf8").toString("base64");

    const result = validator.validate({ top: { data: base64 } });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("rejects invalid base64 binary value", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);

    const result = validator.validate({ top: { data: "not!!!base64" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.toLowerCase().includes("base64"))).toBe(true);
  });

  it("rejects binary value that exceeds decoded length constraint", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);
    const tooLong = Buffer.alloc(20, "x").toString("base64");

    const result = validator.validate({ top: { data: tooLong } });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});
