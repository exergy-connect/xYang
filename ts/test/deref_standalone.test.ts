import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_deref_standalone", () => {
  const DEREF_YANG = `
module deref-test {
  yang-version 1.1;
  namespace "urn:test:deref";
  prefix "dt";

  container data-model {
    list entities {
      key "name";
      leaf name { type string; mandatory true; }
      leaf primary_key { type string; mandatory true; }
      list fields {
        key "name";
        leaf name { type string; mandatory true; }
        leaf type { type string; }
        list foreignKeys {
          key "entity";
          leaf entity {
            type leafref {
              path "/data-model/entities/name";
              require-instance true;
            }
            mandatory true;
          }
          must "count(deref(current()/entity)) = 1" {
            error-message "deref() in path expression must resolve to exactly one node";
          }
          must "/data-model/entities[name = string(deref(current()/entity))]" {
            error-message "deref() in predicate: referenced entity must exist";
          }
        }
      }
    }
  }
}
`;

  const CHILD_FK_DEREF_YANG = `
module deref-child-fk {
  yang-version 1.1;
  namespace "urn:test:deref-child-fk";
  prefix "dcf";

  container data-model {
    list entities {
      key "name";
      leaf name { type string; mandatory true; }
      leaf primary_key { type string; mandatory true; }
      list fields {
        key "name";
        leaf name { type string; mandatory true; }
        leaf type { type string; }
        list foreignKeys {
          key "entity";
          leaf entity {
            type leafref {
              path "/data-model/entities/name";
              require-instance true;
            }
            mandatory true;
          }
        }
      }
      list parents {
        key "child_fk";
        leaf child_fk {
          type leafref {
            path "../../fields/name";
            require-instance true;
          }
          mandatory true;
          must "deref(current())/../foreignKeys" {
            error-message "Child foreign key field must have a foreignKeys definition";
          }
        }
      }
    }
  }
}
`;

  function buildValidator(): YangValidator {
    return new YangValidator(parseYangString(DEREF_YANG));
  }

  it("deref in path expression passes when entity exists", () => {
    const validator = buildValidator();
    const result = validator.validate({
      "data-model": {
        entities: [
          { name: "company", primary_key: "id", fields: [{ name: "id", type: "string" }] },
          {
            name: "department",
            primary_key: "id",
            fields: [
              { name: "id", type: "string" },
              { name: "company_id", type: "string", foreignKeys: [{ entity: "company" }] }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("deref in path expression fails when entity is missing", () => {
    const validator = buildValidator();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "only",
            primary_key: "id",
            fields: [
              { name: "id", type: "string" },
              { name: "ref", type: "string", foreignKeys: [{ entity: "missing" }] }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(
      result.errors.some(
        (error) =>
          error.toLowerCase().includes("deref") || error.toLowerCase().includes("path") || error.toLowerCase().includes("leafref")
      )
    ).toBe(true);
  });

  it("deref in predicate passes when entity exists", () => {
    const validator = buildValidator();
    const result = validator.validate({
      "data-model": {
        entities: [
          { name: "parent", primary_key: "pk", fields: [{ name: "pk", type: "string" }] },
          {
            name: "child",
            primary_key: "pk",
            fields: [
              { name: "pk", type: "string" },
              { name: "parent_id", type: "string", foreignKeys: [{ entity: "parent" }] }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("deref in predicate fails when entity is missing", () => {
    const validator = buildValidator();
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "one",
            primary_key: "id",
            fields: [
              { name: "id", type: "string" },
              { name: "fk", type: "string", foreignKeys: [{ entity: "ghost" }] }
            ]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(
      result.errors.some(
        (error) =>
          error.toLowerCase().includes("deref") ||
          error.toLowerCase().includes("predicate") ||
          error.toLowerCase().includes("entity") ||
          error.toLowerCase().includes("leafref")
      )
    ).toBe(true);
  });

  it("deref(current())/../foreignKeys passes when child_fk field has foreignKeys", () => {
    const validator = new YangValidator(parseYangString(CHILD_FK_DEREF_YANG));
    const result = validator.validate({
      "data-model": {
        entities: [
          { name: "parent", primary_key: "id", fields: [{ name: "id", type: "string" }] },
          {
            name: "child",
            primary_key: "id",
            fields: [
              { name: "id", type: "string" },
              { name: "parent_id", type: "string", foreignKeys: [{ entity: "parent" }] }
            ],
            parents: [{ child_fk: "parent_id" }]
          }
        ]
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("deref(current())/../foreignKeys fails when child_fk field lacks foreignKeys", () => {
    const validator = new YangValidator(parseYangString(CHILD_FK_DEREF_YANG));
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "one",
            primary_key: "id",
            fields: [
              { name: "id", type: "string" },
              { name: "plain", type: "string" }
            ],
            parents: [{ child_fk: "plain" }]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.includes("foreignKeys") || error.toLowerCase().includes("foreign key"))).toBe(true);
  });
});
