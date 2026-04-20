import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const metaModelPath = resolve(repoRoot, "examples/meta-model.yang");

function leafrefResolutionErrors(errors: string[]): string[] {
  return errors.filter((e) => {
    const msg = e.toLowerCase();
    return msg.includes("no target instance") || msg.includes("relative path resolution");
  });
}

describe("python parity: test_leafref_relative_path", () => {
  it("resolves ../../fields/name for parents.child_fk in meta-model without relative-path resolver errors", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);

    const result = validator.validate({
      "data-model": {
        name: "Test Model",
        version: "25.01.27.1",
        author: "Test",
        consolidated: false,
        entities: [
          {
            name: "parent_entity",
            primary_key: "parent_id",
            fields: [
              { name: "parent_id", type: "string" },
              { name: "children", type: "array", item_type: { entity: "child_entity" } }
            ]
          },
          {
            name: "child_entity",
            primary_key: "child_id",
            fields: [
              { name: "child_id", type: "string" },
              {
                name: "parent_id",
                type: "string",
                foreignKeys: [{ entity: "parent_entity" }]
              }
            ],
            parents: [{ child_fk: "parent_id", parent_array: "children" }]
          }
        ]
      }
    });

    expect(leafrefResolutionErrors(result.errors)).toHaveLength(0);
  });

  it("invalid relative-path leafref reference is rejected", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    list entities {
      key name;
      leaf name { type string; }
      list fields {
        key name;
        leaf name { type string; }
      }
      leaf ref {
        type leafref {
          path "../fields/name";
          require-instance true;
        }
        must "../fields[name = current()]" {
          error-message "leafref value must resolve to an existing field";
        }
      }
    }
  }
}
`);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        entities: [
          {
            name: "e1",
            fields: [{ name: "id" }, { name: "other" }],
            ref: "nonexistent_field"
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    const joined = result.errors.join(" ").toLowerCase();
    expect(joined.includes("leafref") || joined.includes("nonexistent_field") || joined.includes("field")).toBe(true);
  });

  it("with multiple entities, relative path resolution stays scoped to the current entity context", () => {
    const module = parseYangFile(metaModelPath);
    const validator = new YangValidator(module);

    const result = validator.validate({
      "data-model": {
        name: "Test Model",
        version: "25.01.27.1",
        author: "Test",
        consolidated: false,
        entities: [
          {
            name: "entity1",
            primary_key: "id1",
            fields: [
              { name: "id1", type: "string" },
              { name: "field1", type: "string" }
            ]
          },
          {
            name: "entity2",
            primary_key: "id2",
            fields: [
              { name: "id2", type: "string" },
              { name: "fk_field", type: "string", foreignKeys: [{ entity: "entity1" }] },
              { name: "children", type: "array", item_type: { entity: "entity3" } }
            ],
            parents: [{ child_fk: "fk_field", parent_array: "children" }]
          },
          {
            name: "entity3",
            primary_key: "id3",
            fields: [{ name: "id3", type: "string" }]
          }
        ]
      }
    });

    expect(leafrefResolutionErrors(result.errors)).toHaveLength(0);
  });
});
