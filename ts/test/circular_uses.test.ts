import { describe, expect, it } from "vitest";
import { YangParser } from "../src";

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
  it("parses cyclic text without error when uses expansion is disabled", () => {
    const mod = new YangParser({ expandUses: false }).parseString(SELF_REFERENTIAL_YANG);
    expect(mod.name).toBe("c");
  });
});
