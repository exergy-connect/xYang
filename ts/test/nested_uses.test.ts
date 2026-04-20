import { describe, expect, it } from "vitest";
import { YangCircularUsesError } from "../src/core/errors";
import { parseYangString, YangValidator } from "../src";

const YANG_NESTED_USES = `
module nested_uses {
  yang-version 1.1;
  namespace "urn:test:nested-uses";
  prefix "nu";

  grouping inner {
    leaf x {
      type string;
      description "From inner grouping";
    }
  }

  grouping middle {
    uses inner;
    leaf y {
      type string;
      description "From middle grouping";
    }
  }

  grouping outer {
    uses middle;
    leaf z {
      type string;
      description "From outer grouping";
    }
  }

  container root {
    description "Root container that uses the nested grouping chain";
    uses outer;
  }
}
`;

const YANG_REFINE_NESTED_LIST_PATH = `
module refine_nested_list_path {
  yang-version 1.1;
  namespace "urn:test:refine-nested-list-path";
  prefix "rnlp";

  grouping list_g {
    list L {
      key k;
      leaf k {
        type string;
      }
    }
  }

  grouping base_g {
    choice outer_ch {
      case oc {
        uses list_g;
      }
    }
  }

  grouping refined_g {
    uses base_g {
      refine outer_ch/oc/L {
        max-elements 0;
        min-elements 0;
      }
    }
  }

  container root {
    uses refined_g;
  }
}
`;

const YANG_USES_CYCLE_BROKEN_BY_REFINE_ON_LIST = `
module uses_cycle_broken_by_refine {
  yang-version 1.1;
  namespace "urn:test:uses-cycle-broken-by-refine";
  prefix "ucbr";

  grouping sink {
    leaf ok { type string; }
  }

  grouping core {
    choice branch {
      case escape {
        uses sink;
      }
      case recurse {
        list hold {
          key id;
          leaf id { type string; }
          uses loop_back;
        }
      }
    }
  }

  grouping loop_back {
    uses core {
      refine branch/recurse/hold {
        max-elements 0;
        min-elements 0;
      }
    }
  }

  container root {
    uses loop_back;
  }
}
`;

describe("python parity: test_nested_uses", () => {
  it("parses a module with nested uses", () => {
    const module = parseYangString(YANG_NESTED_USES);
    expect(module.name).toBe("nested_uses");
    expect(module.yangVersion).toBe("1.1");
    const root = module.findStatement("root");
    expect(root).toBeDefined();
  });

  it("validates instance data against nested uses expansion", () => {
    const module = parseYangString(YANG_NESTED_USES);
    const validator = new YangValidator(module);
    const result = validator.validate({ root: { x: "a", y: "b", z: "c" } });
    expect(result.isValid, result.errors.join("; ")).toBe(true);
  });

  it("parses refine path over list behind nested uses", () => {
    const module = parseYangString(YANG_REFINE_NESTED_LIST_PATH);
    expect(module.name).toBe("refine_nested_list_path");
    expect(module.findStatement("root")).toBeDefined();
  });

  it("throws YangCircularUsesError for recursive uses through list", () => {
    try {
      parseYangString(YANG_USES_CYCLE_BROKEN_BY_REFINE_ON_LIST);
      expect.fail("expected circular uses error");
    } catch (e) {
      expect(e).toBeInstanceOf(YangCircularUsesError);
      expect(String((e as Error).message)).toMatch(/loop_back/);
    }
  });
});
