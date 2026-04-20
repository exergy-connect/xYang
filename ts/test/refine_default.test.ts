import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangModule, YangParser } from "../src";

const REFINE_DEFAULT_FALSE = `
module refine_default_false {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-default";
  prefix rd;

  grouping g {
    leaf flag {
      type boolean;
    }
  }

  container c {
    uses g {
      refine flag {
        default false;
      }
    }
  }
}
`;

const REFINE_REQUIRED_DEFAULT = `
module refine_required_default {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-required-default";
  prefix rrd;

  grouping field_common {
    leaf required {
      type boolean;
    }
  }

  grouping generic_field {
    uses field_common {
      refine required {
        default false;
      }
    }
  }

  container c {
    uses generic_field;
  }
}
`;

const REFINE_LEAF_LIST_TWO_DEFAULTS = `
module refine_ll_defaults {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-ll";
  prefix rll;

  grouping g {
    leaf-list tags {
      type string;
    }
  }

  container c {
    uses g {
      refine tags {
        default "alpha";
        default "beta";
      }
    }
  }
}
`;

function leafUnderContainerC(module: YangModule, name: string) {
  const c = module.findStatement("c");
  expect(c?.name).toBe("c");
  const leaf = c?.findStatement(name);
  expect(leaf?.keyword).toBe("leaf");
  return leaf!;
}

function leafListUnderContainerC(module: YangModule, name: string) {
  const c = module.findStatement("c");
  expect(c?.name).toBe("c");
  const node = c?.findStatement(name);
  expect(node?.keyword).toBe("leaf-list");
  return node!;
}

describe("python parity: test_refine_default", () => {
  it("refine default false on leaf from grouping applies after uses expand", () => {
    const mod = parseYangString(REFINE_DEFAULT_FALSE);
    const leaf = leafUnderContainerC(mod, "flag");
    expect(leaf.data.default).toBe("false");
  });

  it("refine default false applies through nested groupings (generic_field pattern)", () => {
    const mod = parseYangString(REFINE_REQUIRED_DEFAULT);
    const leaf = leafUnderContainerC(mod, "required");
    expect(leaf.data.default).toBe("false");
  });

  it("JSON Schema carries leaf default and parseJsonSchema round-trips it", () => {
    const mod = parseYangString(REFINE_DEFAULT_FALSE);
    const schema = generateJsonSchema(mod);
    const cSchema = (schema.properties as Record<string, unknown>).c as Record<string, unknown>;
    const flagSchema = (cSchema.properties as Record<string, unknown>).flag as Record<string, unknown>;
    expect(flagSchema.default).toBe("false");

    const mod2 = parseJsonSchema(JSON.stringify(schema));
    const leaf = leafUnderContainerC(mod2, "flag");
    expect(leaf.data.default).toBe("false");
  });

  it("with expand_uses false, refined_defaults stay on the refine AST under uses", () => {
    const mod = new YangParser({ expand_uses: false }).parseString(REFINE_DEFAULT_FALSE);
    const c = mod.findStatement("c");
    const uses = c?.statements[0];
    expect(uses?.keyword).toBe("uses");
    const refines = (uses!.data as { refines?: Array<Record<string, unknown>> }).refines;
    expect(refines?.length).toBe(1);
    expect(refines?.[0]?.refine_target_path).toBe("flag");
    expect(refines?.[0]?.refined_defaults).toEqual(["false"]);
  });

  it("refine applies multiple defaults to leaf-list", () => {
    const mod = parseYangString(REFINE_LEAF_LIST_TWO_DEFAULTS);
    const ll = leafListUnderContainerC(mod, "tags");
    expect(ll.data.defaults).toEqual(["alpha", "beta"]);
  });

  it("refine single default on leaf-list (int32)", () => {
    const yang = `
module refine_ll_one {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-ll-one";
  prefix o;

  grouping g {
    leaf-list ids {
      type int32;
    }
  }
  container c {
    uses g {
      refine ids {
        default 7;
      }
    }
  }
}
`;
    const mod = parseYangString(yang);
    const ll = leafListUnderContainerC(mod, "ids");
    const defaults = ll.data.defaults as unknown[] | undefined;
    expect(defaults?.length).toBe(1);
    const v = defaults![0];
    expect(v === 7 || v === "7").toBe(true);
  });

  it("leaf-list default array in JSON Schema round-trips", () => {
    const mod = parseYangString(REFINE_LEAF_LIST_TWO_DEFAULTS);
    const schema = generateJsonSchema(mod);
    const cSchema = (schema.properties as Record<string, unknown>).c as Record<string, unknown>;
    const tagsSchema = (cSchema.properties as Record<string, unknown>).tags as Record<string, unknown>;
    expect(tagsSchema.default).toEqual(["alpha", "beta"]);

    const mod2 = parseJsonSchema(JSON.stringify(schema));
    const ll = leafListUnderContainerC(mod2, "tags");
    expect(ll.data.defaults).toEqual(["alpha", "beta"]);
  });
});
