import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { loadMetaModel, loadYamlDataModel } from "./fixtures";

describe("python parity: meta-model/test_composite_primary_key_sample", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("composite_primary_key_sample_validates", () => {
    const data = loadYamlDataModel("tests/data/composite_primary_key_sample.yaml");
    const { isValid, errors, warnings } = new YangValidator(metaModel).validate(data);
    expect(isValid, `errors=${errors} warnings=${warnings}`).toBe(true);
  });

  it("composite_primary_key_points_at_composite_field", () => {
    const data = loadYamlDataModel("tests/data/composite_primary_key_sample.yaml");
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);

    const root = data["data-model"] as Record<string, unknown>;
    const entities = Object.fromEntries((root.entities as Record<string, unknown>[]).map((e) => [e.name, e]));
    const loc = entities.location as Record<string, unknown>;
    expect(loc.primary_key).toBe("location_key");

    const locFields = Object.fromEntries((loc.fields as Record<string, unknown>[]).map((f) => [f.name, f]));
    expect((locFields.location_key.type as Record<string, unknown>).definition).toBe("location_key_ref");

    const defs = Object.fromEntries((loc.field_definitions as Record<string, unknown>[]).map((d) => [d.name, d]));
    const defType = defs.location_key_ref.type as Record<string, unknown>;
    const composite = defType.composite as Record<string, unknown>[];
    expect(composite[0].name).toBe("region_code");
    expect(composite[1].name).toBe("location_id");

    const wh = entities.warehouse as Record<string, unknown>;
    expect(wh.primary_key).toBe("warehouse_id");
    const whFields = Object.fromEntries((wh.fields as Record<string, unknown>[]).map((f) => [f.name, f]));
    const atLoc = whFields.at_location.type as Record<string, unknown>;
    expect(atLoc.definition).toBe("location_key_ref");
    expect((atLoc.foreignKeys as Record<string, unknown>[])[0].entity).toBe("location");
  });
});
