import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseYangFile, YangModule, YangStatement, YangValidator } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const YANG_FILE = join(__dirname, "../../../tests/json/data/choice_cases/choice_cases.yang");

function minimalDataModel(reqChoice?: Record<string, unknown>, optChoice?: Record<string, unknown>): Record<string, unknown> {
  return {
    "data-model": {
      ...(reqChoice ? { req_choice_container: reqChoice } : {}),
      ...(optChoice ? { opt_choice_container: optChoice } : {})
    }
  };
}

function collectXYangChoicePaths(node: unknown, path = "$"): string[] {
  const out: string[] = [];
  if (!node || typeof node !== "object" || Array.isArray(node)) {
    return out;
  }
  const obj = node as Record<string, unknown>;
  const xYang = obj["x-yang"];
  if (xYang && typeof xYang === "object" && !Array.isArray(xYang) && (xYang as Record<string, unknown>).type === "choice") {
    out.push(path);
  }

  const properties = obj.properties;
  if (properties && typeof properties === "object" && !Array.isArray(properties)) {
    for (const [key, value] of Object.entries(properties as Record<string, unknown>)) {
      out.push(...collectXYangChoicePaths(value, `${path}.properties.${key}`));
    }
  }

  const items = obj.items;
  if (items && typeof items === "object" && !Array.isArray(items)) {
    out.push(...collectXYangChoicePaths(items, `${path}.items`));
  }

  for (const combo of ["oneOf", "anyOf", "allOf"]) {
    const branch = obj[combo];
    if (!Array.isArray(branch)) {
      continue;
    }
    for (let i = 0; i < branch.length; i += 1) {
      out.push(...collectXYangChoicePaths(branch[i], `${path}.${combo}[${i}]`));
    }
  }

  return out;
}

function collectPropertyKeys(node: unknown): string[] {
  if (!node || typeof node !== "object" || Array.isArray(node)) {
    return [];
  }
  const obj = node as Record<string, unknown>;
  const out: string[] = [];

  const properties = obj.properties;
  if (properties && typeof properties === "object" && !Array.isArray(properties)) {
    for (const [key, value] of Object.entries(properties as Record<string, unknown>)) {
      out.push(key, ...collectPropertyKeys(value));
    }
  }

  const items = obj.items;
  if (items && typeof items === "object" && !Array.isArray(items)) {
    out.push(...collectPropertyKeys(items));
  }

  for (const combo of ["oneOf", "anyOf", "allOf"]) {
    const branch = obj[combo];
    if (!Array.isArray(branch)) {
      continue;
    }
    for (const item of branch) {
      out.push(...collectPropertyKeys(item));
    }
  }

  return out;
}

function collectChoiceNames(module: YangModule): Set<string> {
  const names = new Set<string>();
  const visit = (statements: YangStatement[]) => {
    for (const statement of statements) {
      if (statement.keyword === "choice" && statement.name) {
        names.add(statement.name);
      }
      visit(statement.statements);
    }
  };
  visit(module.statements);
  return names;
}

describe("python parity: json/test_choice_cases", () => {
  it("emits hoisted choice schema (no x-yang.type=choice nodes, no choice-name properties)", () => {
    const module = parseYangFile(YANG_FILE);
    const schema = generateJsonSchema(module);

    const choicePaths = collectXYangChoicePaths(schema);
    expect(choicePaths).toEqual([]);

    const choiceNames = collectChoiceNames(module);
    const propertyKeys = new Set(collectPropertyKeys(schema));
    const clashes = [...choiceNames].filter((name) => propertyKeys.has(name));
    expect(clashes).toEqual([]);
  });

  it("emits oneOf for mandatory and optional choices", () => {
    const schema = generateJsonSchema(parseYangFile(YANG_FILE));
    const dm = ((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>);
    const dmProps = dm.properties as Record<string, unknown>;

    const req = dmProps.req_choice_container as Record<string, unknown>;
    expect(Array.isArray(req.oneOf)).toBe(true);
    expect((req.oneOf as unknown[]).length).toBe(2);

    const reqKeys = new Set<string>();
    for (const branch of req.oneOf as Array<Record<string, unknown>>) {
      expect(branch.type).toBe("object");
      expect(branch.additionalProperties).toBe(false);
      const props = branch.properties as Record<string, unknown>;
      const required = branch.required as string[];
      expect(new Set(required)).toEqual(new Set(Object.keys(props)));
      for (const key of Object.keys(props)) {
        reqKeys.add(key);
      }
    }
    expect(reqKeys).toEqual(new Set(["primitive", "entity"]));

    const opt = dmProps.opt_choice_container as Record<string, unknown>;
    expect(Array.isArray(opt.oneOf)).toBe(true);
    expect((opt.oneOf as unknown[]).length).toBe(3);
    expect((opt.oneOf as Array<Record<string, unknown>>)[0]).toEqual({ type: "object", maxProperties: 0 });
  });

  it("validates mandatory choice cases", () => {
    const validator = new YangValidator(parseYangFile(YANG_FILE));

    expect(validator.validate(minimalDataModel({ primitive: "string" })).isValid).toBe(true);
    expect(validator.validate(minimalDataModel({ entity: "e1" })).isValid).toBe(true);
    expect(validator.validate(minimalDataModel({})).isValid).toBe(false);
    expect(validator.validate(minimalDataModel({ primitive: "string", entity: "e1" })).isValid).toBe(false);
  });

  it("validates optional choice cases", () => {
    const validator = new YangValidator(parseYangFile(YANG_FILE));

    expect(validator.validate(minimalDataModel(undefined, {})).isValid).toBe(true);
    expect(validator.validate(minimalDataModel(undefined, { a: "x" })).isValid).toBe(true);
    expect(validator.validate(minimalDataModel(undefined, { b: "y" })).isValid).toBe(true);
    expect(validator.validate(minimalDataModel(undefined, { a: "x", b: "y" })).isValid).toBe(false);
  });
});
