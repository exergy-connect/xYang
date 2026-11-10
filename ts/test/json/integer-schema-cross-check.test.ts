/**
 * The generated JSON Schema and YangValidator agree on RFC 7951 integers.
 * Issue #63 left JSON Schema for int64, uint64, and decimal64 out of scope.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, YangParser, YangValidator } from "../../src";

const CASE = join(dirname(fileURLToPath(import.meta.url)), "../../../tests/cases/types/integer");
const CROSS = JSON.parse(readFileSync(join(CASE, "schema-cross-check.json"), "utf8")) as {
  module: string;
  instances: Array<{ name: string; data: unknown; valid: boolean }>;
};

function schemaAccepts(schema: Record<string, unknown>, value: unknown): boolean {
  const options = (schema.oneOf ?? schema.anyOf) as Record<string, unknown>[] | undefined;
  if (Array.isArray(options)) {
    return options.some((option) => schemaAccepts(option, value));
  }
  const kind = schema.type;
  if (kind === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const props = (schema.properties ?? {}) as Record<string, Record<string, unknown>>;
    const row = value as Record<string, unknown>;
    if (schema.additionalProperties === false && Object.keys(row).some((key) => !(key in props))) {
      return false;
    }
    for (const [key, item] of Object.entries(row)) {
      if (key in props && !schemaAccepts(props[key], item)) return false;
    }
    const required = Array.isArray(schema.required) ? (schema.required as string[]) : [];
    return required.every((name) => name in row);
  }
  if (kind === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) return false;
    if (typeof schema.minimum === "number" && value < schema.minimum) return false;
    if (typeof schema.maximum === "number" && value > schema.maximum) return false;
    return true;
  }
  if (kind === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) return false;
    if (typeof schema.minimum === "number" && value < schema.minimum) return false;
    if (typeof schema.maximum === "number" && value > schema.maximum) return false;
    return true;
  }
  if (kind === "string") {
    if (typeof value !== "string") return false;
    if (typeof schema.pattern === "string" && !new RegExp(`^(?:${schema.pattern})$`).test(value)) return false;
    return true;
  }
  if (kind === "boolean") return typeof value === "boolean";
  if (kind === "array") {
    if (!Array.isArray(value)) return false;
    const items = schema.items;
    if (items && typeof items === "object" && !Array.isArray(items)) {
      return value.every((item) => schemaAccepts(items as Record<string, unknown>, item));
    }
    return true;
  }
  return false;
}

describe("integer schema and validator agree", () => {
  it("agrees on every cross-check instance", () => {
    const module = new YangParser().parseFile(join(CASE, CROSS.module));
    const schema = generateJsonSchema(module);
    const u8 = ((schema.properties as Record<string, Record<string, unknown>>).top.properties as Record<
      string,
      Record<string, unknown>
    >).u8;
    expect(u8.type).toBe("integer");
    const validator = new YangValidator(module);
    for (const inst of CROSS.instances) {
      const schemaOk = schemaAccepts(schema, inst.data);
      const validatorOk = validator.validateDetailed(inst.data).valid;
      expect(schemaOk, inst.name).toBe(inst.valid);
      expect(validatorOk, inst.name).toBe(inst.valid);
      expect(schemaOk, inst.name).toBe(validatorOk);
    }
  });
});
