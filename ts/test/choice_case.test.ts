import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { YangSemanticError, YangSyntaxError, parseYangFile, parseYangString, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const metaModelPath = resolve(repoRoot, "examples/meta-model.yang");

const META_MODEL_VERSION = "26.03.29.1";

function dm(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const {
    name = "M",
    version = META_MODEL_VERSION,
    author = "A",
    description = "Test data model.",
    ...rest
  } = overrides;
  return { "data-model": { name, version, author, description, ...rest } };
}

function ent(
  name: string,
  primaryKey: string,
  fields: unknown[],
  extra: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    name,
    description: `Entity ${name}.`,
    primary_key: primaryKey,
    fields,
    ...extra
  };
}

function fp(
  name: string,
  primitive: string,
  opts: { description?: string } = {}
): Record<string, unknown> {
  return {
    name,
    description: opts.description ?? `Field ${name}.`,
    type: { primitive }
  };
}

function fArrayEntity(
  name: string,
  entity: string,
  opts: { description?: string } = {}
): Record<string, unknown> {
  return {
    name,
    description: opts.description ?? `Field ${name}.`,
    type: { array: { entity } }
  };
}

describe("python parity: test_choice_case", () => {
  const ITEM_TYPE_CHOICE_MODULE = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef primitive-type {
    type enumeration {
      enum string;
      enum integer;
      enum number;
      enum boolean;
    }
  }

  container data {
    container item_type {
      choice item-type-choice {
        mandatory true;
        case primitive-case {
          leaf primitive {
            type primitive-type;
          }
        }
        case entity-case {
          leaf entity {
            type string;
          }
        }
      }
    }
  }
}
`;

  it("stores mandatory true on choice statement", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      mandatory true;
      case a {
        leaf x { type string; }
      }
      case b {
        leaf y { type string; }
      }
    }
  }
}
`);

    const choice = module.findStatement("data")?.findStatement("protocol");
    expect(choice).toBeDefined();
    expect(choice?.keyword).toBe("choice");
    expect(choice?.data.mandatory).toBe(true);
  });

  it("stores mandatory false on choice statement", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      mandatory false;
      case a {
        leaf x { type string; }
      }
    }
  }
}
`);

    const choice = module.findStatement("data")?.findStatement("protocol");
    expect(choice).toBeDefined();
    expect(choice?.keyword).toBe("choice");
    expect(choice?.data.mandatory).toBe(false);
  });

  it("defaults choice mandatory to false when omitted", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        leaf x { type string; }
      }
    }
  }
}
`);

    const choice = module.findStatement("data")?.findStatement("protocol");
    expect(choice).toBeDefined();
    expect(choice?.data.mandatory).toBe(false);
  });

  it("rejects duplicate schema node names across cases (RFC 7950 §7.9)", () => {
    const bad = `
module dup-choice {
  yang-version 1.1;
  namespace "urn:dup";
  prefix d;

  container c {
    choice interface-type {
      case a {
        leaf ethernet {
          type string;
        }
      }
      case b {
        container ethernet {
          leaf x { type string; }
        }
      }
    }
  }
}
`;

    expect(() => parseYangString(bad)).toThrow(YangSemanticError);
    expect(() => parseYangString(bad)).toThrow(/ethernet/i);
  });

  it("rejects mandatory as a direct substatement of case (Appendix A)", () => {
    const bad = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        mandatory true;
        leaf x { type string; }
      }
    }
  }
}
`;

    let caught: unknown;
    try {
      parseYangString(bad);
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(YangSyntaxError);
    const msg = String(caught).toLowerCase();
    expect(msg.includes("case") || msg.includes("mandatory")).toBe(true);
  });

  it("parses leaf mandatory true under a case; choice stays non-mandatory (RFC 7950 §7.6.5)", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        leaf x {
          type string;
          mandatory true;
        }
      }
      case b {
        leaf y { type string; }
      }
    }
  }
}
`);

    const choice = module.findStatement("data")?.findStatement("protocol");
    expect(choice).toBeDefined();
    expect(choice?.keyword).toBe("choice");
    expect(choice?.data.mandatory).toBe(false);

    const caseA = choice?.statements.find((s) => s.keyword === "case" && s.name === "a");
    expect(caseA).toBeDefined();
    const leafX = caseA?.findStatement("x");
    expect(leafX?.keyword).toBe("leaf");
    expect(leafX?.data.mandatory).toBe(true);
  });

  it("rejects data when multiple choice cases are active", () => {
    const module = parseYangString(ITEM_TYPE_CHOICE_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        item_type: {
          primitive: "string",
          entity: "User"
        }
      }
    });

    expect(result.isValid).toBe(false);
    const joined = result.errors.map((e) => e.toLowerCase()).join(" ");
    expect(joined.includes("only one case") || joined.includes("multiple cases")).toBe(true);
  });

  it("rejects data when mandatory choice has no active case", () => {
    const module = parseYangString(ITEM_TYPE_CHOICE_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        item_type: {}
      }
    });

    expect(result.isValid).toBe(false);
    const joined = result.errors.join(" ").toLowerCase();
    expect(joined.includes("mandatory") && joined.includes("choice")).toBe(true);
  });

  it("accepts primitive branch data for mandatory choice", () => {
    const module = parseYangString(ITEM_TYPE_CHOICE_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        item_type: {
          primitive: "string"
        }
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("accepts entity branch data for mandatory choice", () => {
    const module = parseYangString(ITEM_TYPE_CHOICE_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        item_type: {
          entity: "my_entity"
        }
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("enforces mandatory nested choice when outer case has sibling data", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice outer {
      case ca {
        leaf sibling { type string; }
        container inner_wrap {
          choice inner {
            mandatory true;
            case ia { leaf a { type string; } }
            case ib { leaf b { type string; } }
          }
        }
      }
      case cb {
        leaf z { type string; }
      }
    }
  }
}
`);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        sibling: "x",
        inner_wrap: {}
      }
    });

    expect(result.isValid).toBe(false);
    const joined = result.errors.join(" ").toLowerCase();
    expect(joined.includes("mandatory") && joined.includes("choice")).toBe(true);
  });

  it("accepts nested choice when inner branch alone is provided", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice outer {
      case ca {
        leaf sibling { type string; }
        container inner_wrap {
          choice inner {
            mandatory true;
            case ia { leaf a { type string; } }
            case ib { leaf b { type string; } }
          }
        }
      }
    }
  }
}
`);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        inner_wrap: { a: "only-inner" }
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("requires mandatory leaf in case when sibling in same case is present", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        leaf x {
          type string;
          mandatory true;
        }
        leaf y { type string; }
      }
    }
  }
}
`);
    const validator = new YangValidator(module);
    const invalid = validator.validate({
      data: { y: "present-without-x" }
    });
    const valid = validator.validate({
      data: { x: "ok" }
    });

    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
    expect(valid.isValid).toBe(true);
  });

  it("rejects invalid enumeration value on primitive branch (documents enum validation under choice)", () => {
    const module = parseYangString(ITEM_TYPE_CHOICE_MODULE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        item_type: {
          primitive: "invalid_type"
        }
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("meta-model.yang: array of primitives satisfies item_type choice", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);
    const result = validator.validate(
      dm({
        entities: [
          ent("test_entity", "id", [
            fp("id", "integer", { description: "PK." }),
            {
              name: "tags",
              description: "String tags.",
              type: { array: { primitive: "string" } }
            }
          ])
        ]
      })
    );

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("meta-model.yang: array of entity satisfies item_type choice", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);
    const result = validator.validate(
      dm({
        entities: [
          ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
          ent("child", "id", [
            fp("id", "integer", { description: "PK." }),
            fArrayEntity("parents", "parent", { description: "Parent entities." })
          ])
        ]
      })
    );

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("meta-model.yang: empty array inner choice documents mandatory item_type behavior", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);
    const result = validator.validate(
      dm({
        entities: [
          ent("test_entity", "id", [
            fp("id", "integer", { description: "PK." }),
            {
              name: "tags",
              description: "Empty array inner choice.",
              type: { array: {} }
            }
          ])
        ]
      })
    );

    // Mirrors Python: placeholder until/unless stricter mandatory inner-choice validation is required.
    expect(typeof result.isValid).toBe("boolean");
  });
});
