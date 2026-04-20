import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

function generateYangModel(mustCondition: string): string {
  return `module minimal-test {
  namespace "urn:test:minimal";
  prefix "mt";
  yang-version 1.1;

  container data-model {
    leaf consolidated {
      type boolean;
      default false;
    }

    list entities {
      key name;
      leaf name {
        type string;
      }
      leaf primary_key {
        type string;
      }

      list fields {
        key name;
        leaf name {
          type string;
        }
        leaf type {
          type string;
        }
        container foreignKey {
          presence "Foreign key is defined";
          leaf entity {
            type leafref {
              path "/data-model/entities/name";
              require-instance true;
            }
            mandatory true;
          }
          leaf field {
            type leafref {
              path "/data-model/entities/fields/name";
              require-instance true;
            }
          }
        }
      }

      list parents {
        key child_fk;
        leaf child_fk {
          type leafref {
            path "../../fields/name";
            require-instance true;
          }
          mandatory true;

          must "${mustCondition}" {
            error-message "Child foreign key field type must match parent primary key field type";
          }
        }
      }
    }
  }
}
`;
}

const testData = {
  "data-model": {
    consolidated: true,
    entities: [
      {
        name: "parent",
        primary_key: "id",
        fields: [{ name: "id", type: "string" }]
      },
      {
        name: "child",
        fields: [
          {
            name: "parent_id",
            type: "string",
            foreignKey: {
              entity: "parent"
            }
          }
        ],
        parents: [
          {
            child_fk: "parent_id"
          }
        ]
      }
    ]
  }
};

describe("python parity: test_current_context_in_predicate", () => {
  it("accepts nested deref() in must (preserves current() through relative navigation)", () => {
    const mustCondition =
      "/data-model/consolidated = false() or " +
      "(deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type or " +
      "(count(deref(current())/../foreignKey/field) = 0 and " +
      "deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(deref(current())/../foreignKey/entity)/../primary_key]/type))";
    const module = parseYangString(generateYangModel(mustCondition));
    const validator = new YangValidator(module);
    const result = validator.validate(testData);
    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("accepts absolute path with predicate in must (current() in predicate refers to must context node)", () => {
    const mustCondition =
      "/data-model/consolidated = false() or " +
      "(deref(current())/../type = /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = deref(current())/../foreignKey/field]/type or " +
      "(count(deref(current())/../foreignKey/field) = 0 and " +
      "deref(current())/../type = /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = /data-model/entities[name = deref(current())/../foreignKey/entity]/primary_key]/type))";
    const module = parseYangString(generateYangModel(mustCondition));
    const validator = new YangValidator(module);
    const result = validator.validate(testData);
    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });
});
