import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { loadMetaModel } from "./fixtures";

function baseDataModel(): Record<string, unknown> {
  return {
    name: "t",
    version: "26.03.29.1",
    author: "test",
    description: "required/default tests",
    consolidated: true,
    entities: [
      {
        name: "e",
        description: "Entity e.",
        primary_key: "pk",
        fields: [
          {
            name: "pk",
            description: "Primary key.",
            type: { primitive: "string" }
          }
        ]
      }
    ]
  };
}

describe("python parity: meta-model/test_new_meta_model_required_default", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("required_and_default_valid_when_exclusive", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "with_default",
      description: "Has default.",
      type: { primitive: "integer" },
      required: false,
      default: 42
    });
    fields.push({
      name: "mandatory_flag",
      description: "Required flag.",
      type: { primitive: "string" },
      required: true
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("required_true_with_default_fails_must", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "bad",
      description: "Invalid required+default.",
      type: { primitive: "string" },
      required: true,
      default: "x"
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("required") || e.toLowerCase().includes("default"))).toBe(true);
  });

  it("primitive_enum_valid_for_string", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "status",
      description: "Status enum.",
      type: { enum: ["a", "b"] }
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("primitive_enum_invalid_for_boolean", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "bad_enum",
      description: "Invalid enum on boolean.",
      type: { primitive: "boolean", enum: [true, false] }
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("enum"))).toBe(true);
  });

  it("min_max_and_minDate_on_field_valid", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "qty",
      description: "Quantity bounds.",
      type: { primitive: "integer", min: 0, max: 100 }
    });
    fields.push({
      name: "dob",
      description: "Date of birth.",
      type: {
        primitive: "date",
        minDate: "2020-01-01",
        maxDate: "2030-12-31"
      }
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("minDate_rejected_for_string_primitive", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const fields = (ent0[0].fields as Record<string, unknown>[]).slice();
    fields.push({
      name: "bad_dates",
      description: "minDate on string.",
      type: { primitive: "string", minDate: "2020-01-01" }
    });
    ent0[0] = { ...ent0[0], fields };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("mindate"))).toBe(true);
  });

  it("default_on_composite_subfield_valid", () => {
    const dm = baseDataModel();
    const ent0 = dm.entities as Record<string, unknown>[];
    const pkField = (ent0[0].fields as Record<string, unknown>[])[0];
    ent0[0] = {
      ...ent0[0],
      primary_key: "pk",
      fields: [
        pkField,
        {
          name: "comp",
          description: "Composite with default subfield.",
          type: {
            composite: [
              {
                name: "sub",
                description: "Sub with default.",
                type: { primitive: "number" },
                default: 1.5
              }
            ]
          }
        }
      ]
    };
    const data = { "data-model": { ...dm, entities: ent0 } };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });
});
