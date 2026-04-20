import { describe, expect, it } from "vitest";
import {
  YangCircularUsesError,
  YangParser,
  YangStatement,
  YangModule,
  parseYangString
} from "../src";

function* walkStatements(stmt: YangStatement): Generator<YangStatement> {
  yield stmt;
  for (const child of stmt.statements) {
    yield* walkStatements(child);
  }
}

function findListNamed(module: YangModule, name: string): YangStatement | undefined {
  for (const top of module.statements) {
    for (const node of walkStatements(top)) {
      if (node.keyword === "list" && node.name === name) {
        return node;
      }
    }
  }
  return undefined;
}

function findLeafNamed(module: YangModule, name: string): YangStatement | undefined {
  for (const top of module.statements) {
    for (const node of walkStatements(top)) {
      if (node.keyword === "leaf" && node.name === name) {
        return node;
      }
    }
  }
  return undefined;
}

const YANG_REFINE_LIST_CARDINALITY = `
module refine_list_cardinality {
  yang-version 1.1;
  namespace "urn:test:refine-list-cardinality";
  prefix "rlc";

  grouping g {
    list items {
      key k;
      leaf k {
        type string;
      }
    }
  }

  container c {
    uses g {
      refine items {
        max-elements 3;
        min-elements 1;
      }
    }
  }
}
`;

const YANG_REFINE_LIST_UNDER_CHOICE_CASE = `
module refine_list_under_choice {
  yang-version 1.1;
  namespace "urn:test:refine-list-under-choice";
  prefix "rluc";

  grouping g {
    choice ch {
      case only {
        list rows {
          key id;
          leaf id {
            type string;
          }
        }
      }
    }
  }

  container root {
    uses g {
      refine ch/only/rows {
        max-elements 0;
        min-elements 0;
      }
    }
  }
}
`;

const YANG_USES_IN_LIST_WITH_REFINE = `
module uses_in_list_with_refine {
  yang-version 1.1;
  namespace "urn:test:uses-in-list-with-refine";
  prefix "uil";

  grouping payload {
    leaf payload_leaf {
      type string;
    }
  }

  container c {
    list L {
      key k;
      leaf k {
        type string;
      }
      uses payload {
        refine payload_leaf {
          must "false()";
          description "Refine on a leaf inside grouping used from list body.";
        }
      }
    }
  }
}
`;

const YANG_GENERIC_FIELD_NO_ARRAY_CASE = `
module generic_field_no_array {
  yang-version 1.1;
  namespace "urn:test:generic-field-no-array";
  prefix "gfna";

  typedef primitive-type-name {
    type enumeration {
      enum string;
      enum integer;
    }
    description "Primitive type tag.";
  }

  grouping generic-field {
    description "Like examples/generic-field.yang but without the case-array branch.";
    leaf name {
      type string {
        length "1..128";
      }
      mandatory true;
      description "Field name.";
    }
    container type {
      description "Field type: primitive or composite only.";
      choice choice-type {
        mandatory true;
        description "Primitive or composite object.";
        case primitive {
          leaf primitive {
            type primitive-type-name;
            mandatory true;
            description "Primitive type.";
          }
        }
        case case-composite {
          description "Composite field: named subfields, each a full generic-field.";
          list fields {
            key name;
            min-elements 1;
            description "Subfields (recursive generic field).";
            uses generic-field {
              refine type/choice-type/case-composite/fields {
                max-elements 0;
                description "Exclude nested composite subfields; breaks recursive uses expansion.";
              }
            }
          }
        }
      }
    }
  }

  container field {
    description "Example instance root for one generic field.";
    uses generic-field;
  }
}
`;

describe("python parity: test_refine_list", () => {
  it("refine applies max/min-elements to list after expansion", () => {
    const module = parseYangString(YANG_REFINE_LIST_CARDINALITY);
    expect(module.name).toBe("refine_list_cardinality");
    const lst = findListNamed(module, "items");
    expect(lst).toBeDefined();
    expect(lst?.data.max_elements).toBe(3);
    expect(lst?.data.min_elements).toBe(1);
  });

  it("refine path through choice/case reaches the list", () => {
    const module = parseYangString(YANG_REFINE_LIST_UNDER_CHOICE_CASE);
    const lst = findListNamed(module, "rows");
    expect(lst).toBeDefined();
    expect(lst?.data.max_elements).toBe(0);
    expect(lst?.data.min_elements).toBe(0);
  });

  it("uses inside list with refine applies must to grouping leaf", () => {
    const module = parseYangString(YANG_USES_IN_LIST_WITH_REFINE);
    expect(module.name).toBe("uses_in_list_with_refine");
    const lst = findListNamed(module, "L");
    expect(lst).toBeDefined();
    const leaf = findLeafNamed(module, "payload_leaf");
    expect(leaf).toBeDefined();
    const musts = leaf?.statements.filter((s) => s.keyword === "must" && typeof s.argument === "string") ?? [];
    expect(musts.some((m) => m.argument === "false()")).toBe(true);
  });

  it("recursive uses generic-field under list fields throws when expanding", () => {
    expect(() => parseYangString(YANG_GENERIC_FIELD_NO_ARRAY_CASE)).toThrow(YangCircularUsesError);
    try {
      parseYangString(YANG_GENERIC_FIELD_NO_ARRAY_CASE);
    } catch (e) {
      expect(e).toBeInstanceOf(YangCircularUsesError);
      expect(String(e)).toContain("generic-field");
    }
  });

  it("same module parses with expand_uses disabled", () => {
    const parser = new YangParser({ expand_uses: false });
    const module = parser.parseString(YANG_GENERIC_FIELD_NO_ARRAY_CASE);
    expect(module.name).toBe("generic_field_no_array");
  });
});
