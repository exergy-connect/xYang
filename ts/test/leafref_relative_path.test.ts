import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

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
