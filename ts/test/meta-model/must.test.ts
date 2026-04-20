import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import {
  dm,
  ent,
  fComposite,
  fComputed,
  fp,
  loadMetaModel,
  subf
} from "./fixtures";

describe("python parity: meta-model/test_must", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  function validate(data: Record<string, unknown>): { ok: boolean; errors: string[] } {
    const r = new YangValidator(metaModel).validate(data);
    return { ok: r.isValid, errors: r.errors };
  }

  it("allow_unlimited_fields_valid", () => {
    const data = dm({
      allow_unlimited_fields: null,
      entities: [
        ent(
          "big",
          "id",
          [fp("id", "integer", { description: "PK." }), ...Array.from({ length: 8 }, (_, i) => fp(`f${i}`, "string", { description: `F${i}.` }))]
        )
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("allow_unlimited_fields_invalid", () => {
    const data = dm({
      allow_unlimited_fields: null,
      entities: [
        ent("small", "id", [fp("id", "integer", { description: "PK." }), fp("a", "string", { description: "A." })])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("allow_unlimited_fields"))).toBe(true);
  });

  it("entity_field_limit_valid", () => {
    const data = dm({
      entities: [ent("e", "id", [fp("id", "integer", { description: "PK." }), fp("x", "string", { description: "X." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("entity_field_limit_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [fp("id", "integer", { description: "PK." }), ...Array.from({ length: 8 }, (_, i) => fp(`f${i}`, "string", { description: `F${i}.` }))])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("7") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("entity_name_underscore_valid", () => {
    const data = dm({
      entities: [ent("entity_a", "id", [fp("id", "integer", { description: "PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("entity_name_underscore_invalid", () => {
    const data = dm({
      entities: [ent("a_b_c_d", "id", [fp("id", "integer", { description: "PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("underscore") || e.toLowerCase().includes("name"))).toBe(true);
  });

  it("primary_key_reference_valid", () => {
    const data = dm({
      entities: [ent("e", "id", [fp("id", "integer", { description: "PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("primary_key_reference_invalid", () => {
    const data = dm({
      entities: [ent("e", "missing", [fp("id", "integer", { description: "PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("primary_key") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("mindate_type_valid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("d", "date", { minDate: "2020-01-01", description: "D." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("mindate_type_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("t", "string", { minDate: "2020-01-01", description: "T." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("minDate") || e.toLowerCase().includes("date"))).toBe(true);
  });

  it("maxdate_type_valid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("d", "date", { maxDate: "2020-12-31", description: "D." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("maxdate_ordering_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("d", "date", { minDate: "2020-12-31", maxDate: "2020-01-01", description: "D." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("maxDate") || e.includes("minDate"))).toBe(true);
  });

  it("foreign_key_type_match_valid", () => {
    const data = dm({
      entities: [
        ent("parent", "id", [fp("id", "integer", { description: "PK." })]),
        ent("child", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("parent_id", "integer", { foreignKeys: [{ entity: "parent" }], description: "FK to parent." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("foreign_key_unknown_entity_invalid", () => {
    const data = dm({
      entities: [
        ent("child", "id", [fp("id", "integer", { description: "PK." })]),
        ent("other", "oid", [
          fp("oid", "integer", { description: "PK." }),
          fp("bad_fk", "integer", { foreignKeys: [{ entity: "no_such_entity" }], description: "Broken FK target." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("computed_binary_two_fields_valid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("a", "integer", { description: "A." }),
          fp("b", "integer", { description: "B." }),
          fComputed("sum", "integer", "add", [{ field: "a" }, { field: "b" }])
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("computed_binary_two_fields_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("a", "integer", { description: "A." }),
          fComputed("bad", "integer", "add", [{ field: "a" }])
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("2") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("computed_aggregation_min_two_fields_valid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("x", "integer", { description: "X." }),
          fp("y", "integer", { description: "Y." }),
          fComputed("m", "integer", "min", [{ field: "x" }, { field: "y" }])
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("computed_aggregation_min_two_fields_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("x", "integer", { description: "X." }),
          fComputed("m", "integer", "min", [{ field: "x" }])
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("2") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("computed_reference_exists_valid", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("a", "integer", { description: "A." }),
          fp("b", "integer", { description: "B." }),
          fComputed("sum", "integer", "add", [{ field: "a" }, { field: "b" }])
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("computed_reference_missing_invalid", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("a", "integer", { description: "A." }),
          {
            name: "bad",
            description: "Bad computed.",
            type: { primitive: "integer" },
            computed: {
              operation: "subtraction",
              fields: [{ field: "a" }, { field: "nonexistent_field" }]
            }
          }
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes("Computed field reference") || e.includes("must exist"))).toBe(true);
  });

  it("computed_cross_entity_fk_valid", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("property_detail", "mls_number", [
          fp("mls_number", "integer", { description: "MLS." }),
          fp("sqft", "integer", { description: "Sqft." })
        ]),
        ent("property_economics", "mls_number", [
          fp("mls_number", "integer", { foreignKeys: [{ entity: "property_detail" }], description: "FK MLS." }),
          fp("price", "integer", { description: "Price." }),
          {
            name: "price_per_sqft",
            description: "Price per sqft.",
            type: { primitive: "number" },
            computed: {
              operation: "division",
              fields: [{ field: "price" }, { field: "sqft", entity: "property_detail" }]
            }
          }
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("computed_cross_entity_no_fk_invalid", () => {
    const data = dm({
      consolidated: true,
      entities: [
        ent("entity1", "id", [fp("id", "integer", { description: "PK." }), fp("field1", "integer", { description: "F1." })]),
        ent("entity2", "id", [
          fp("id", "integer", { description: "PK." }),
          {
            name: "invalid_computed",
            description: "Invalid cross-entity.",
            type: { primitive: "integer" },
            computed: {
              operation: "subtraction",
              fields: [{ field: "field1", entity: "entity1" }, { field: "id" }]
            }
          }
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("foreign key") || e.includes("Cross-entity"))).toBe(true);
  });

  it("required_no_default_valid", () => {
    const data = dm({
      entities: [ent("e", "id", [fp("id", "integer", { description: "PK." }), fp("x", "string", { required: true, description: "X." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("required_with_default_invalid", () => {
    const data = dm({
      entities: [
        ent("e", "id", [
          fp("id", "integer", { description: "PK." }),
          fp("x", "string", { required: true, default: "v", description: "X." })
        ])
      ]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("required") || e.toLowerCase().includes("default"))).toBe(true);
  });

  it("composite_subcomponent_type_valid", () => {
    const data = dm({
      entities: [ent("e", "pk", [fComposite("pk", [subf("a", "integer"), subf("b", "string")], { description: "Composite PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("composite_subcomponent_type_invalid", () => {
    const nested = {
      name: "nested",
      description: "Nested composite.",
      type: { composite: [subf("x", "string")] }
    };
    const data = dm({
      entities: [ent("e", "pk", [fComposite("pk", [subf("a", "integer"), nested], { description: "Composite PK." })])]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("composite"))).toBe(true);
  });

  it("change_id_valid", () => {
    const data = dm({
      consolidated: true,
      changes: [{ id: 1, timestamp: "2025-01-01T00:00:00Z" }],
      entities: [ent("e", "id", [fp("id", "integer", { description: "PK." })], { c: 1 })]
    });
    const { ok, errors } = validate(data);
    expect(ok, errors.join("\n")).toBe(true);
  });

  it("change_id_invalid", () => {
    const data = dm({
      consolidated: true,
      changes: [{ id: 1, timestamp: "2025-01-01T00:00:00Z" }],
      entities: [ent("e", "id", [fp("id", "integer", { description: "PK." })], { c: 99 })]
    });
    const { ok, errors } = validate(data);
    expect(ok).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("change") || e.toLowerCase().includes(" c "))).toBe(true);
  });
});
