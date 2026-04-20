import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString, YangModule, YangStatement, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const metaModelPath = resolve(repoRoot, "examples/meta-model.yang");

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

describe("python parity: test_must_on_leafref_list", () => {
  it("must on list with leafref: valid when ref_name matches", () => {
    const yang = `module test-must-leafref-list {
  namespace "urn:test:must-leafref-list";
  prefix "tml";
  yang-version 1.1;

  container data {
    list items {
      key id;
      leaf id {
        type string;
      }
      leaf name {
        type string;
      }

      must "name = /data/items[id = current()/id]/name" {
        error-message "Item name must match its own name";
        description "This constraint should always pass for valid data";
      }
    }

    list references {
      key ref_id;
      leaf ref_id {
        type leafref {
          path "/data/items/id";
          require-instance true;
        }
      }
      leaf ref_name {
        type leafref {
          path "/data/items[id = current()/../ref_id]/name";
          require-instance true;
        }
      }

      must "ref_name = /data/items[id = current()/ref_id]/name" {
        error-message "Referenced name must match the referenced item's name";
        description "Validates that ref_name matches the name of the item referenced by ref_id";
      }
    }
  }
}`;
    const v = new YangValidator(parseYangString(yang));
    const { isValid, errors } = v.validate({
      data: {
        items: [
          { id: "item1", name: "Item One" },
          { id: "item2", name: "Item Two" }
        ],
        references: [
          { ref_id: "item1", ref_name: "Item One" },
          { ref_id: "item2", ref_name: "Item Two" }
        ]
      }
    });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("must on list with leafref: invalid when ref_name mismatched", () => {
    const yang = `module test-must-leafref-list {
  namespace "urn:test:must-leafref-list";
  prefix "tml";
  yang-version 1.1;

  container data {
    list items {
      key id;
      leaf id {
        type string;
      }
      leaf name {
        type string;
      }
    }

    list references {
      key ref_id;
      leaf ref_id {
        type leafref {
          path "/data/items/id";
          require-instance true;
        }
      }
      leaf ref_name {
        type leafref {
          path "/data/items/name";
          require-instance true;
        }
      }

      must "ref_name = /data/items[id = current()/ref_id]/name" {
        error-message "Referenced name must match the referenced item's name";
        description "Validates that ref_name matches the name of the item referenced by ref_id";
      }
    }
  }
}`;
    const v = new YangValidator(parseYangString(yang));
    const { isValid, errors } = v.validate({
      data: {
        items: [
          { id: "item1", name: "Item One" },
          { id: "item2", name: "Item Two" }
        ],
        references: [{ ref_id: "item1", ref_name: "Item Two" }]
      }
    });
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.includes("Referenced name must match"))).toBe(true);
  });

  it("meta-model foreignKeys list: valid data", () => {
    const module = parseYangFile(metaModelPath);
    const v = new YangValidator(module);
    const { isValid, errors } = v.validate({
      "data-model": {
        name: "Test Model",
        version: "26.03.29.1",
        author: "Test",
        description: "FK list must test.",
        consolidated: true,
        entities: [
          {
            name: "parent",
            description: "Parent entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              { name: "name", description: "Name.", type: { primitive: "string" } }
            ]
          },
          {
            name: "child",
            description: "Child entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              {
                name: "parent_id",
                description: "FK to parent PK.",
                type: {
                  primitive: "integer",
                  foreignKeys: [{ entity: "parent" }]
                }
              }
            ]
          }
        ]
      }
    });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("meta-model foreignKeys list: invalid type mismatch (conditional like Python)", () => {
    const module = parseYangFile(metaModelPath);
    const v = new YangValidator(module);
    const { isValid, errors } = v.validate({
      "data-model": {
        name: "Test Model",
        version: "26.03.29.1",
        author: "Test",
        description: "FK mismatch test.",
        consolidated: true,
        entities: [
          {
            name: "parent",
            description: "Parent entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              { name: "name", description: "Name.", type: { primitive: "string" } }
            ]
          },
          {
            name: "child",
            description: "Child entity.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "integer" } },
              {
                name: "parent_name",
                description: "String FK to parent (type mismatch vs int PK).",
                type: {
                  primitive: "string",
                  foreignKeys: [{ entity: "parent" }]
                }
              }
            ]
          }
        ]
      }
    });
    if (!isValid) {
      const joined = errors.join(" ").toLowerCase();
      expect(joined.includes("type") || joined.includes("primary key")).toBe(true);
    }
  });

  it("must on list: current() is list entry for leafrefs", () => {
    const yang = `module test-must-leafref-current {
  namespace "urn:test:must-leafref-current";
  prefix "tmc";
  yang-version 1.1;

  container data {
    list source {
      key id;
      leaf id {
        type string;
      }
      leaf value {
        type string;
      }
    }

    list target {
      key target_id;
      leaf target_id {
        type leafref {
          path "/data/source/id";
          require-instance true;
        }
      }
      leaf source_value {
        type leafref {
          path "/data/source/value";
          require-instance true;
        }
      }

      must "source_value = /data/source[id = current()/target_id]/value" {
        error-message "source_value must match the value of the source referenced by target_id";
        description "current() should refer to the target list item.";
      }
    }
  }
}`;
    const v = new YangValidator(parseYangString(yang));
    expect(
      v.validate({
        data: {
          source: [
            { id: "s1", value: "value1" },
            { id: "s2", value: "value2" }
          ],
          target: [
            { target_id: "s1", source_value: "value1" },
            { target_id: "s2", source_value: "value2" }
          ]
        }
      }).isValid
    ).toBe(true);

    const bad = v.validate({
      data: {
        source: [
          { id: "s1", value: "value1" },
          { id: "s2", value: "value2" }
        ],
        target: [{ target_id: "s1", source_value: "value2" }]
      }
    });
    expect(bad.isValid).toBe(false);
    expect(bad.errors.some((e) => e.includes("source_value must match"))).toBe(true);
  });

  it("list must with concat() for string concatenation", () => {
    const yang = `module test-must-plus {
  namespace "urn:test:must-plus";
  prefix "tmp";
  yang-version 1.1;

  container data {
    list items {
      key id;
      leaf id {
        type string;
      }
      leaf type {
        type string;
      }
      leaf value {
        type string;
      }
      must "/data-model/consolidated = false() or type = 'test' or value != ''" {
        error-message "Type must be 'test' or value must not be empty";
      }
      must "concat(type, '-', value) != 'other-' or type = 'test'" {
        error-message "When type is 'other', value must not be empty";
      }
    }
  }
}`;
    const module = parseYangString(yang);
    const items = findListNamed(module, "items");
    expect(items).toBeDefined();
    const mustStmts = items?.statements.filter((s) => s.keyword === "must") ?? [];
    expect(mustStmts.length).toBeGreaterThanOrEqual(2);
    const exprs = mustStmts.map((m) => m.argument ?? "");
    expect(exprs.some((e) => e.includes("concat"))).toBe(true);

    const v = new YangValidator(module);
    expect(
      v.validate({ data: { items: [{ id: "item1", type: "test", value: "" }] } }).isValid
    ).toBe(true);
    expect(
      v.validate({ data: { items: [{ id: "item2", type: "other", value: "non-empty" }] } }).isValid
    ).toBe(true);
    const bad = v.validate({ data: { items: [{ id: "item3", type: "other", value: "" }] } });
    expect(bad.isValid).toBe(false);
    expect(
      bad.errors.some((e) => e.includes("value must not be empty") || e.includes("Type must be"))
    ).toBe(true);
  });

  it("foreignKeys-style must with deref (consolidated true/false)", () => {
    const yang = `module test-foreignkeys-plus {
  namespace "urn:test:foreignkeys-plus";
  prefix "tfp";
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
      leaf-list primary_key {
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
        list foreignKeys {
          key entity;
          must "/data-model/consolidated = false() or ../type = deref(current()/entity)/../fields[name = deref(current()/entity)/../primary_key]/type" {
            error-message "Foreign key field type must match the referenced entity's primary key field type";
          }
          leaf entity {
            type leafref {
              path "/data-model/entities/name";
              require-instance true;
            }
            mandatory true;
          }
        }
      }
    }
  }
}`;
    const module = parseYangString(yang);
    const fk = findListNamed(module, "foreignKeys");
    expect(fk).toBeDefined();
    const musts = fk?.statements.filter((s) => s.keyword === "must") ?? [];
    expect(musts.length).toBeGreaterThan(0);
    const expr = musts[0]?.argument ?? "";
    expect(expr).toContain("deref");
    expect(expr).toContain("current()/entity");

    const v = new YangValidator(module);
    expect(
      v.validate({
        "data-model": {
          consolidated: false,
          entities: [
            {
              name: "parent",
              primary_key: ["id"],
              fields: [{ name: "id", type: "integer" }]
            },
            {
              name: "child",
              primary_key: ["id"],
              fields: [
                { name: "id", type: "integer" },
                {
                  name: "parent_id",
                  type: "integer",
                  foreignKeys: [{ entity: "parent" }]
                }
              ]
            }
          ]
        }
      }).isValid
    ).toBe(true);

    expect(
      v.validate({
        "data-model": {
          consolidated: true,
          entities: [
            {
              name: "parent",
              primary_key: ["id"],
              fields: [{ name: "id", type: "integer" }]
            },
            {
              name: "child",
              primary_key: ["id"],
              fields: [
                { name: "id", type: "integer" },
                {
                  name: "parent_id",
                  type: "integer",
                  foreignKeys: [{ entity: "parent" }]
                }
              ]
            }
          ]
        }
      }).isValid
    ).toBe(true);

    const bad = v.validate({
      "data-model": {
        consolidated: true,
        entities: [
          {
            name: "parent",
            primary_key: ["id"],
            fields: [{ name: "id", type: "integer" }]
          },
          {
            name: "child",
            primary_key: ["id"],
            fields: [
              { name: "id", type: "integer" },
              {
                name: "parent_id",
                type: "string",
                foreignKeys: [{ entity: "parent" }]
              }
            ]
          }
        ]
      }
    });
    expect(bad.isValid).toBe(false);
    expect(
      bad.errors.some(
        (e) =>
          e.includes("Foreign key field type") || e.toLowerCase().includes("type")
      )
    ).toBe(true);
  });
});
