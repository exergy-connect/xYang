import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { loadMetaModel, loadYamlDataModel } from "./fixtures";

const PRIMITIVE_TYPE_NAME_ENUMS = new Set([
  "string",
  "integer",
  "number",
  "boolean",
  "array",
  "datetime",
  "date",
  "year",
  "duration_in_days",
  "qualified_string",
  "qualified_integer",
  "qualified_number"
]);

const TYPE_SHAPE_FIELD_NAMES = new Set([
  "pk",
  "via_definition",
  "arr_items_primitive",
  "arr_items_composite",
  "top_composite"
]);

const GENERIC_FIELD_TYPE_FRAGMENTS: { id: string; fragment: Record<string, unknown> }[] = [
  {
    id: "primitive",
    fragment: {
      name: "p",
      version: "26.03.29.1",
      author: "t",
      description: "Minimal primitive branch.",
      consolidated: true,
      entities: [
        {
          name: "e",
          description: "Entity e.",
          primary_key: "id",
          fields: [{ name: "id", description: "PK.", type: { primitive: "string" } }]
        }
      ]
    }
  },
  {
    id: "definition_ref",
    fragment: {
      name: "p",
      version: "26.03.29.1",
      author: "t",
      description: "Definition ref branch.",
      consolidated: true,
      entities: [
        {
          name: "e",
          description: "Entity e.",
          primary_key: "id",
          field_definitions: [{ name: "d", description: "Reusable int.", type: { primitive: "integer" } }],
          fields: [
            { name: "id", description: "PK.", type: { primitive: "string" } },
            { name: "r", description: "Via definition.", type: { definition: "d" } }
          ]
        }
      ]
    }
  },
  {
    id: "array_primitive_element",
    fragment: {
      name: "p",
      version: "26.03.29.1",
      author: "t",
      description: "Array of primitives.",
      consolidated: true,
      entities: [
        {
          name: "e",
          description: "Entity e.",
          primary_key: "id",
          fields: [
            { name: "id", description: "PK.", type: { primitive: "string" } },
            { name: "a", description: "Number array.", type: { array: { primitive: "number" } } }
          ]
        }
      ]
    }
  },
  {
    id: "array_composite_element",
    fragment: {
      name: "p",
      version: "26.03.29.1",
      author: "t",
      description: "Array of composite.",
      consolidated: true,
      entities: [
        {
          name: "e",
          description: "Entity e.",
          primary_key: "id",
          fields: [
            { name: "id", description: "PK.", type: { primitive: "string" } },
            {
              name: "a",
              description: "Composite array.",
              type: {
                array: {
                  composite: [{ name: "x", description: "Sub x.", type: { primitive: "boolean" } }]
                }
              }
            }
          ]
        }
      ]
    }
  },
  {
    id: "top_level_composite",
    fragment: {
      name: "p",
      version: "26.03.29.1",
      author: "t",
      description: "Top composite.",
      consolidated: true,
      entities: [
        {
          name: "e",
          description: "Entity e.",
          primary_key: "id",
          fields: [
            { name: "id", description: "PK.", type: { primitive: "string" } },
            {
              name: "c",
              description: "Composite field.",
              type: {
                composite: [
                  { name: "u", description: "U.", type: { primitive: "date" } },
                  { name: "v", description: "V.", type: { primitive: "datetime" } }
                ]
              }
            }
          ]
        }
      ]
    }
  }
];

describe("python parity: meta-model/test_new_meta_model_sample", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("new_meta_model_sample_yaml_validates", () => {
    const data = loadYamlDataModel("tests/data/new_meta_model_sample.yaml");
    const { isValid, errors, warnings } = new YangValidator(metaModel).validate(data);
    expect(isValid, `Validation errors: ${errors}; warnings: ${warnings}`).toBe(true);
  });

  it("new_meta_model_sample_covers_all_primitive_enums_and_type_shapes", () => {
    const data = loadYamlDataModel("tests/data/new_meta_model_sample.yaml");
    const { isValid, errors, warnings } = new YangValidator(metaModel).validate(data);
    expect(isValid, `Validation errors: ${errors}; warnings: ${warnings}`).toBe(true);

    const root = data["data-model"] as Record<string, unknown>;
    const entities = root.entities as Record<string, unknown>[];
    const demo = entities.find((e) => e.name === "demo");
    expect(demo).toBeDefined();
    const fields = demo!.fields as Record<string, unknown>[];
    const byName = new Map(fields.map((f) => [f.name as string, f]));
    const names = new Set(byName.keys());

    for (const enumVal of PRIMITIVE_TYPE_NAME_ENUMS) {
      const fname = `prim_${enumVal}`;
      expect(names.has(fname), `Sample missing field for primitive enum ${enumVal}`).toBe(true);
      const prim = (byName.get(fname)!.type as Record<string, unknown>).primitive;
      expect(prim).toBe(enumVal);
    }

    for (const required of TYPE_SHAPE_FIELD_NAMES) {
      expect(names.has(required), `Sample missing type-shape field ${required}`).toBe(true);
    }

    expect((byName.get("via_definition")!.type as Record<string, unknown>).definition).toBe("reusable_string");
    expect(((byName.get("arr_items_primitive")!.type as Record<string, unknown>).array as Record<string, unknown>).primitive).toBe(
      "integer"
    );
    expect(
      (((byName.get("arr_items_composite")!.type as Record<string, unknown>).array as Record<string, unknown>).composite as unknown[])
        .length
    ).toBeGreaterThanOrEqual(1);
    expect(((byName.get("top_composite")!.type as Record<string, unknown>).composite as unknown[]).length).toBeGreaterThanOrEqual(1);
  });

  it.each(GENERIC_FIELD_TYPE_FRAGMENTS)("generic_field_type_branch_minimal_valid ($id)", ({ fragment }) => {
    const data = { "data-model": fragment };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("field_definition_definition_ref_rejected", () => {
    const data = {
      "data-model": {
        name: "Bad",
        version: "26.03.29.1",
        author: "t",
        description: "Nested definition ref (invalid).",
        consolidated: false,
        entities: [
          {
            name: "e",
            description: "Entity e.",
            primary_key: "id",
            field_definitions: [
              { name: "base", description: "Base.", type: { primitive: "string" } },
              { name: "nested_ref", description: "Invalid chained def.", type: { definition: "base" } }
            ],
            fields: [{ name: "id", description: "PK.", type: { primitive: "string" } }]
          }
        ]
      }
    };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.includes("field_definition cannot reference another"))).toBe(true);
  });

  it("new_meta_model_parent_array_must_rejects_non_array_target", () => {
    const data = {
      "data-model": {
        name: "t",
        version: "26.03.29.1",
        author: "t",
        description: "parent_array negative test.",
        consolidated: true,
        entities: [
          {
            name: "company",
            brief: "c",
            description: "Company.",
            primary_key: "id",
            fields: [
              { name: "id", description: "PK.", type: { primitive: "string" } },
              { name: "departments", description: "Not an entity array.", type: { array: { primitive: "string" } } }
            ]
          },
          {
            name: "department",
            brief: "d",
            description: "Department.",
            primary_key: "did",
            fields: [
              { name: "did", description: "PK.", type: { primitive: "string" } },
              {
                name: "company_id",
                description: "Broken parent_array target.",
                type: {
                  primitive: "string",
                  foreignKeys: [{ entity: "company", parent_array: "id" }]
                }
              }
            ]
          }
        ]
      }
    };
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.includes("parent_array must name"))).toBe(true);
  });
});
