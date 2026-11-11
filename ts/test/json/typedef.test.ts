import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile, YangValidator } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const VERSION_TYPEDEF_YANG = join(__dirname, "../../../tests/json/data/version_typedef/version_typedef.yang");
const VERSION_TYPEDEF_JSON = join(__dirname, "../../../tests/json/data/version_typedef/version_typedef.yang.json");

describe("python parity: json/test_typedef", () => {
  it("loads typedef model from .yang and .yang.json with same key shape", () => {
    const fromYang = parseYangFile(VERSION_TYPEDEF_YANG);
    const fromJson = parseJsonSchema(JSON.parse(readFileSync(VERSION_TYPEDEF_JSON, "utf-8")) as Record<string, unknown>);

    expect(fromYang.name).toBe(fromJson.name);
    expect(Object.keys(fromYang.typedefs).sort()).toEqual(Object.keys(fromJson.typedefs).sort());
    expect(fromYang.findStatement("data-model")?.findStatement("version")).toBeDefined();
    expect(fromJson.findStatement("data-model")?.findStatement("version")).toBeDefined();
  });

  it("accepts valid typedef-constrained value in both parsers", () => {
    const data = { "data-model": { version: "25.03.11.1" } };
    const fromYang = parseYangFile(VERSION_TYPEDEF_YANG);
    const fromJson = parseJsonSchema(JSON.parse(readFileSync(VERSION_TYPEDEF_JSON, "utf-8")) as Record<string, unknown>);

    const validYang = new YangValidator(fromYang).validate(data);
    const validJson = new YangValidator(fromJson).validate(data);

    expect(validYang.isValid).toBe(true);
    expect(validJson.isValid).toBe(true);
  });

  it("rejects invalid typedef-constrained value in both parsers", () => {
    const data = { "data-model": { version: "invalid" } };
    const fromYang = parseYangFile(VERSION_TYPEDEF_YANG);
    const fromJson = parseJsonSchema(JSON.parse(readFileSync(VERSION_TYPEDEF_JSON, "utf-8")) as Record<string, unknown>);

    const invalidYang = new YangValidator(fromYang).validate(data);
    const invalidJson = new YangValidator(fromJson).validate(data);

    expect(invalidYang.isValid).toBe(false);
    expect(invalidJson.isValid).toBe(false);
    expect(invalidYang.errors.length).toBeGreaterThan(0);
    expect(invalidJson.errors.length).toBeGreaterThan(0);
  });
});
