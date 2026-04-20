import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const metaModelPath = resolve(repoRoot, "examples/meta-model.yang");

function findXPathLikeErrors(errors: string[]): string[] {
  return errors.filter((message) => /xpath|syntax|unexpected|parse|token/i.test(message));
}

describe("python parity: test_absolute_paths", () => {
  it("parses meta-model containing absolute-path constraints", () => {
    const module = parseYangFile(metaModelPath);

    expect(module.name).toBe("meta-model");
    expect(module.findStatement("data-model")?.name).toBe("data-model");
  });

  it("parses inline module with absolute path in must expression", () => {
    const module = parseYangString(`
module abs-path-test {
  yang-version 1.1;
  namespace "urn:abs-path-test";
  prefix apt;

  container root {
    leaf value {
      type string;
      must "/root/value = string(current())";
    }
  }
}
`);

    expect(module.name).toBe("abs-path-test");
    expect(module.findStatement("root")?.findStatement("value")?.name).toBe("value");
  });

  it("parses inline module with absolute path and relative navigation", () => {
    const module = parseYangString(`
module abs-rel-test {
  yang-version 1.1;
  namespace "urn:abs-rel-test";
  prefix art;

  container data-model {
    list entities {
      key "name";
      leaf name { type string; }
      leaf parent { type string; }
      must "/data-model/entities[name = ../../data-model/entities[1]/name]";
    }
  }
}
`);

    expect(module.name).toBe("abs-rel-test");
    expect(module.findStatement("data-model")?.findStatement("entities")?.name).toBe("entities");
  });

  it("validation smoke: list-heavy data does not produce XPath syntax errors", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);

    const fields = [
      { name: "id", type: "integer", description: "PK." },
      ...Array.from({ length: 8 }, (_, idx) => ({
        name: `field${idx + 1}`,
        type: "integer",
        description: `Field ${idx + 1}.`
      }))
    ];

    const result = validator.validate({
      "data-model": {
        name: "Test Model",
        version: "25.01.27.1",
        author: "Test",
        entities: [
          {
            name: "test_entity",
            primary_key: "id",
            fields
          }
        ]
      }
    });

    expect(findXPathLikeErrors(result.errors)).toHaveLength(0);
  });

  it("validation smoke: absolute/relative mixed navigation input does not produce XPath syntax errors", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);

    const result = validator.validate({
      "data-model": {
        name: "Test Model",
        version: "25.01.27.1",
        author: "Test",
        entities: [
          {
            name: "test_entity",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" },
              {
                name: "computed_field",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ field: "field1", entity: "other_entity" }]
                }
              }
            ]
          },
          {
            name: "other_entity",
            primary_key: "id",
            fields: [{ name: "id", type: "integer" }]
          }
        ]
      }
    });

    expect(findXPathLikeErrors(result.errors)).toHaveLength(0);
  });
});
