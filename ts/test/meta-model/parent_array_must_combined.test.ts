import { beforeAll, describe, expect, it } from "vitest";
import { YangValidator, type YangModule } from "../../src";
import { loadMetaModel } from "./fixtures";

function strField(name: string, description: string): Record<string, unknown> {
  return { name, description, type: { primitive: "string" } };
}

function combinedBasecaseData(): Record<string, unknown> {
  return {
    "data-model": {
      name: "Base Case Test Model",
      version: "25.11.29.1",
      author: "Test",
      description: "Hierarchical org sample.",
      consolidated: true,
      entities: [
        {
          name: "company",
          description: "Company root.",
          primary_key: "company_id",
          fields: [
            strField("company_id", "Company PK."),
            strField("company_name", "Name."),
            {
              name: "departments",
              description: "Nested departments.",
              type: { array: { entity: "department" } }
            }
          ]
        },
        {
          name: "department",
          description: "Department under company.",
          primary_key: "department_id",
          fields: [
            strField("department_id", "Dept PK."),
            strField("department_name", "Dept name."),
            {
              name: "company_id",
              description: "FK to company via departments array.",
              type: {
                primitive: "string",
                foreignKeys: [{ entity: "company", parent_array: "departments" }]
              }
            },
            {
              name: "employees",
              description: "Nested employees.",
              type: { array: { entity: "employee" } }
            }
          ]
        },
        {
          name: "employee",
          description: "Employee under department.",
          primary_key: "employee_id",
          fields: [
            strField("employee_id", "Employee PK."),
            strField("employee_name", "Employee name."),
            {
              name: "manager_id",
              description: "Self-FK via reports array.",
              type: {
                primitive: "string",
                foreignKeys: [{ entity: "employee", parent_array: "reports" }]
              }
            },
            {
              name: "department_id",
              description: "FK to department via employees array.",
              type: {
                primitive: "string",
                foreignKeys: [{ entity: "department", parent_array: "employees" }]
              }
            },
            strField("email", "Email."),
            {
              name: "reports",
              description: "Nested reports (employees).",
              type: { array: { entity: "employee" } }
            }
          ]
        }
      ]
    }
  };
}

describe("python parity: meta-model/test_parent_array_must_combined", () => {
  let metaModel: YangModule;

  beforeAll(() => {
    metaModel = loadMetaModel();
  });

  it("parent_array_must_combined_with_cache", () => {
    const data = combinedBasecaseData();
    const { isValid, errors } = new YangValidator(metaModel).validate(data);
    expect(
      isValid,
      `Combined model with valid parent_array refs should pass. Errors:\n${errors.join("\n")}`
    ).toBe(true);
  });
});
