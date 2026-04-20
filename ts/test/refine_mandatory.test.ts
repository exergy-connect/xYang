import { describe, expect, it } from "vitest";
import { YangParser } from "../src";

const YANG = `
module t {
  yang-version 1.1;
  namespace "urn:test:r";
  prefix "r";
  grouping g {
    leaf entity {
      type string;
      mandatory true;
    }
  }
  container c {
    uses g {
      refine entity {
        mandatory false;
      }
    }
  }
}
`;

describe("python parity: test_refine_mandatory", () => {
  it("refine mandatory false overrides grouping leaf mandatory true after uses expand", () => {
    const mod = new YangParser({ expand_uses: true }).parseString(YANG);
    const container = mod.findStatement("c");
    expect(container?.name).toBe("c");
    const leaf = container?.statements[0];
    expect(leaf?.keyword).toBe("leaf");
    expect(leaf?.name).toBe("entity");
    expect(leaf?.data.mandatory).toBe(false);
  });
});
