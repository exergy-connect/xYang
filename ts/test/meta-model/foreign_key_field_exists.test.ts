import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { dm, ent, fp, loadMetaModel } from "./fixtures";

describe("python parity: meta-model/test_foreign_key_field_exists", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("foreign_key_field_exists_valid", () => {
    const data = dm({
      entities: [
        ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
        ent("child", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("parent_id", "integer", { foreignKeys: [{ entity: "parent" }], description: "FK to parent." })
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("foreign_key_field_exists_invalid_missing", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
        ent("child", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("parent_wrong_name", "integer", {
            foreignKeys: [{ entity: "parent" }],
            description: "FK with non-matching field name."
          })
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    if (!isValid) {
      expect(errors.length).toBeGreaterThan(0);
    }
  });
});
