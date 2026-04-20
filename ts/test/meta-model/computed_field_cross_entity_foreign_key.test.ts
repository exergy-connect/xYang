import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { dm, ent, fComputed, fp, loadMetaModel } from "./fixtures";

describe("python parity: meta-model/test_computed_field_cross_entity_foreign_key", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("computed_field_cross_entity_foreign_key_valid", () => {
    const data = dm({
      entities: [
        ent("entity1", "id", [fp("id", "integer", { description: "PK." }), fp("value", "integer", { description: "Value." })]),
        ent("entity2", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("entity1_id", "integer", { foreignKeys: [{ entity: "entity1" }], description: "FK to entity1." }),
          fComputed("computed_value", "integer", "add", [{ field: "entity1_id" }, { field: "value", entity: "entity1" }])
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("computed_field_cross_entity_foreign_key_invalid_no_foreign_key", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("entity1", "id", [fp("id", "integer", { description: "PK." }), fp("value", "integer", { description: "Value." })]),
        ent("entity2", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("entity1_id", "integer", { description: "Scalar without FK to entity1." }),
          {
            name: "computed_value",
            description: "Computed without FK.",
            type: { primitive: "integer" },
            computed: {
              operation: "add",
              fields: [{ field: "entity1_id" }, { field: "value", entity: "entity1" }]
            }
          }
        ])
      ]
    });
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("foreign key"))).toBe(true);
  });
});
