import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_bits", () => {
  const BITS_TYPEDEF_MODULE = `
module bits-test {
  yang-version 1.1;
  namespace "urn:test:bits";
  prefix "t";

  typedef flags {
    type bits {
      bit execute { position 0; description "run"; }
      bit read { position 2; }
      bit write;
    }
  }

  container top {
    leaf mode {
      type flags;
    }
  }
}
`;

  const UNION_BITS_MODULE = `
module bits-union {
  yang-version 1.1;
  namespace "urn:test:bits-u";
  prefix "u";

  leaf val {
    type union {
      type int32;
      type bits {
        bit a;
        bit b;
      };
    };
  }
}
`;

  it("parses bits typedef metadata", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const typedef = module.typedefs.flags as { type?: { name?: string; bits?: Array<{ name: string }> } } | undefined;

    expect(typedef?.type?.name).toBe("bits");
    expect((typedef?.type?.bits ?? []).map((bit) => bit.name)).toEqual(["execute", "read", "write"]);
  });

  it("accepts empty and valid bit sets", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const validator = new YangValidator(module);

    const emptyResult = validator.validate({ top: { mode: "" } });
    const multiResult = validator.validate({ top: { mode: "execute read" } });
    const singleResult = validator.validate({ top: { mode: "write" } });

    expect(emptyResult.isValid).toBe(true);
    expect(multiResult.isValid).toBe(true);
    expect(singleResult.isValid).toBe(true);
  });

  it("rejects unknown bit token", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({ top: { mode: "nope" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects duplicate bit token", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({ top: { mode: "execute execute" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects non-string bits value", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({ top: { mode: 1 } });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("supports bits as union member", () => {
    const module = parseYangString(UNION_BITS_MODULE);
    const validator = new YangValidator(module);

    const intResult = validator.validate({ val: 42 });
    const bitsResult = validator.validate({ val: "a b" });
    const invalidResult = validator.validate({ val: "not-a-bit" });

    expect(intResult.isValid).toBe(true);
    expect(bitsResult.isValid).toBe(true);
    expect(invalidResult.isValid).toBe(false);
  });
});
