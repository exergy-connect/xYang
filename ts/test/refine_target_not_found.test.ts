import { describe, expect, it } from "vitest";
import { parseYangString, YangRefineTargetNotFoundError } from "../src";

describe("python parity: test_refine_target_not_found", () => {
  it("raises when refine targets a node that does not exist in the grouping", () => {
    const yang = `
module t {
  yang-version 1.1;
  namespace "urn:test:t";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine does_not_exist {
        description "x";
      }
    }
  }
}
`;
    try {
      parseYangString(yang);
      expect.fail("expected parse to throw");
    } catch (e) {
      expect(e).toBeInstanceOf(YangRefineTargetNotFoundError);
      expect(String((e as Error).message)).toContain("does_not_exist");
    }
  });

  it("raises when refine path targets missing list node", () => {
    const yang = `
module t2 {
  yang-version 1.1;
  namespace "urn:test:t2";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine missing/list {
        max-elements 0;
      }
    }
  }
}
`;
    try {
      parseYangString(yang);
      expect.fail("expected parse to throw");
    } catch (e) {
      expect(e).toBeInstanceOf(YangRefineTargetNotFoundError);
      const err = e as YangRefineTargetNotFoundError;
      expect(err.target_path).toContain("missing/list");
    }
  });
});
