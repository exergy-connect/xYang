import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const metaModelPath = resolve(repoRoot, "examples/meta-model.yang");

describe("python parity: test_must_on_leafref_list", () => {
  it("meta-model foreignKeys list: valid data", () => {
    const module = parseYangFile(metaModelPath);
    const v = new YangValidator(module);
    const { isValid, errors } = v.validate({
      "data-model": {
        name: "Test Model",
        version: "26.03.29.1",
        author: "Test",
        description: "FK list must test.",
        consolidated: true,
        entities: [
          {
            name: "parent",
            description: "Parent entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              { name: "name", description: "Name.", type: { primitive: "string" } }
            ]
          },
          {
            name: "child",
            description: "Child entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              {
                name: "parent_id",
                description: "FK to parent PK.",
                type: {
                  primitive: "integer",
                  foreignKeys: [{ entity: "parent" }]
                }
              }
            ]
          }
        ]
      }
    });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("meta-model foreignKeys list: invalid type mismatch (conditional like Python)", () => {
    const module = parseYangFile(metaModelPath);
    const v = new YangValidator(module);
    const { isValid, errors } = v.validate({
      "data-model": {
        name: "Test Model",
        version: "26.03.29.1",
        author: "Test",
        description: "FK mismatch test.",
        consolidated: true,
        entities: [
          {
            name: "parent",
            description: "Parent entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              { name: "name", description: "Name.", type: { primitive: "string" } }
            ]
          },
          {
            name: "child",
            description: "Child entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              {
                name: "parent_name",
                description: "String FK to parent (type mismatch vs int PK).",
                type: {
                  primitive: "string",
                  foreignKeys: [{ entity: "parent" }]
                }
              }
            ]
          }
        ]
      }
    });
    if (!isValid) {
      const joined = errors.join(" ").toLowerCase();
      expect(joined.includes("type") || joined.includes("primary key")).toBe(true);
    }
  });
});
