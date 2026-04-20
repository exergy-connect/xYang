import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const META_MODEL_SUBSET = `
module meta-model {
  yang-version 1.1;
  namespace "urn:xframe:meta-model";
  prefix "mm";

  typedef field-type {
    type enumeration {
      enum string; enum integer; enum number; enum boolean; enum array;
      enum datetime; enum date; enum composite;
    }
  }

  container data-model {
    leaf consolidated { type boolean; default false; }
    leaf allow_unlimited_fields { type boolean; default false; }
    list entities {
      key name;
      min-elements 1;
      leaf name { type string; mandatory true; }
      leaf primary_key {
        type string;
        mandatory true;
        must "../fields[name = current()]" {
          error-message "primary_key must reference an existing field";
        }
      }
      list fields {
        key name;
        min-elements 1;
        leaf name { type string; mandatory true; }
        leaf type { type field-type; mandatory true; }
        list foreignKeys {
          key entity;
          leaf entity {
            type leafref { path "/data-model/entities/name"; require-instance true; }
            mandatory true;
            must "/data-model/consolidated = false() or /data-model/entities[name = string(current())]" {
              error-message "Foreign key entity must exist in the data model";
            }
          }
        }
        container computed {
          presence " ";
          leaf operation {
            type enumeration {
              enum add; enum subtraction; enum multiplication; enum division;
              enum min; enum max;
            }
            mandatory true;
          }
          list fields {
            key field;
            min-elements 2;
            max-elements 100;
            leaf field {
              type string;
              mandatory true;
              must "/data-model/consolidated = false() or ((not(../entity) and count(../../../../fields[name = current()]) = 1) or (../entity and count(deref(../entity)/../fields[name = current()]) = 1))" {
                error-message "Computed field reference must exist in the specified entity (or current entity if not specified)";
              }
            }
            leaf entity {
              type leafref { path "/data-model/entities/name"; require-instance true; }
              must "/data-model/consolidated = false() or count(../../../../fields[foreignKeys/entity = current()]) = 1" {
                error-message "Cross-entity computed field references require a foreign key field in the current entity that references the target entity";
              }
            }
          }
          must "count(fields) >= 2" {
            error-message "Computed operation requires at least 2 field references";
          }
        }
      }
      must "/data-model/consolidated = true() or ../../allow_unlimited_fields = 'true' or ../../allow_unlimited_fields = true() or count(fields[type != 'array']) <= 7" {
        error-message "Entity has more than 7 non-array fields.";
      }
    }
  }
}
`;

function validatorForSubset(): YangValidator {
  return new YangValidator(parseYangString(META_MODEL_SUBSET));
}

describe("python parity: test_computed_fields", () => {
  it("computed field with missing same-entity reference fails", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        consolidated: true,
        entities: [
          {
            name: "test_entity",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" },
              {
                name: "invalid_computed",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ field: "field1" }, { field: "nonexistent" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("exist") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("valid computed field in same entity passes", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "test_entity",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" },
              { name: "field2", type: "integer" },
              {
                name: "valid_computed",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ field: "field1" }, { field: "field2" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid, result.errors.join("; ")).toBe(true);
  });

  it("missing field in cross-entity reference fails", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        consolidated: true,
        entities: [
          {
            name: "entity1",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" }
            ]
          },
          {
            name: "entity2",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "entity1_id", type: "integer", foreignKeys: [{ entity: "entity1" }] },
              {
                name: "invalid_computed",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ entity: "entity1", field: "nonexistent" }, { field: "field1" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
  });

  it("cross-entity computed field without foreign key fails", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        consolidated: true,
        entities: [
          {
            name: "entity1",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" }
            ]
          },
          {
            name: "entity2",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              {
                name: "invalid_computed",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ entity: "entity1", field: "field1" }, { field: "field1" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
  });

  it("cross-entity computed field with foreign key passes", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "entity1",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "field1", type: "integer" }
            ]
          },
          {
            name: "entity2",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "entity1_id", type: "integer", foreignKeys: [{ entity: "entity1" }] },
              {
                name: "valid_computed",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ entity: "entity1", field: "field1" }, { field: "entity1_id" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid, result.errors.join("; ")).toBe(true);
  });

  it("computed operation with too few field refs fails", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "e1",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "a", type: "integer" },
              {
                name: "bad",
                type: "integer",
                computed: {
                  operation: "subtraction",
                  fields: [{ field: "a" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("2") || e.toLowerCase().includes("field"))).toBe(true);
  });

  it("aggregation with multiple fields passes", () => {
    const validator = validatorForSubset();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "e1",
            primary_key: "id",
            fields: [
              { name: "id", type: "integer" },
              { name: "f1", type: "integer" },
              { name: "f2", type: "integer" },
              { name: "f3", type: "integer" },
              {
                name: "valid_computed",
                type: "integer",
                computed: {
                  operation: "max",
                  fields: [{ field: "f1" }, { field: "f2" }, { field: "f3" }]
                }
              }
            ]
          }
        ]
      }
    });

    expect(result.isValid, result.errors.join("; ")).toBe(true);
  });
});
