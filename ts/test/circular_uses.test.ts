import { describe, expect, it } from "vitest";
import { YangCircularUsesError, YangParser } from "../src";

const SELF_REFERENTIAL_YANG = `
module c {
  yang-version 1.1;
  namespace "urn:test:c";
  prefix "c";
  grouping a {
    uses a;
    leaf x { type string; }
  }
  container r { uses a; }
}
`;

describe("python parity: test_circular_uses", () => {
  it("raises when uses of the same grouping inside that grouping forms a cycle", () => {
    try {
      new YangParser().parseString(SELF_REFERENTIAL_YANG);
      expect.fail("expected parse to throw YangCircularUsesError");
    } catch (e) {
      expect(e).toBeInstanceOf(YangCircularUsesError);
      const err = e as YangCircularUsesError;
      expect(err.repeated).toBe("a");
      expect(String(err.message)).toContain("a");
    }
  });


  it("parses cyclic text without error when uses expansion is disabled", () => {
    const mod = new YangParser({ expand_uses: false }).parseString(SELF_REFERENTIAL_YANG);
    expect(mod.name).toBe("c");
  });
});
