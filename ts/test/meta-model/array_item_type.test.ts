import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { dm, ent, fArrayEntity, fp, loadMetaModel } from "./fixtures";

describe("python parity: meta-model/test_array_item_type", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("array_item_type_foreign_key_valid", () => {
    const data = dm({
      entities: [
        ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
        ent("child", "id", [
          fp("id", "integer", { description: "PK." }),
          fArrayEntity("parents", "parent", { description: "Parent refs." })
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("array_item_type_foreign_key_invalid", () => {
    const data = dm({
      entities: [
        ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
        ent("child", "id", [
          fp("id", "integer", { description: "PK." }),
          {
            name: "parents",
            description: "Invalid nested FK.",
            type: {
              array: {
                entity: "parent",
                foreignKeys: [{ entity: "parent" }]
              }
            }
          }
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.includes("foreignKeys") || e.includes("Unknown field"))).toBe(true);
  });
});
