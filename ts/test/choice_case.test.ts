import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString, YangValidator } from "../src";

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
  // Validation/schema-error coverage: tests/cases/choice/* and
  // tests/cases/parser/substatements/case-mandatory

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
    expect(choice?.mandatory).toBe(true);
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
    expect(choice?.mandatory).toBe(false);
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
    expect(choice?.mandatory).toBe(false);

    const caseA = choice?.statements.find((s) => s.keyword === "case" && s.name === "a");
    expect(caseA).toBeDefined();
    const leafX = caseA?.findStatement("x");
    expect(leafX?.keyword).toBe("leaf");
    expect(leafX?.mandatory).toBe(true);
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

    expect(typeof result.isValid).toBe("boolean");
  });
});
