import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile, type YangModule } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const VERSION_TYPEDEF_YANG = join(__dirname, "../../../tests/json/data/version_typedef/version_typedef.yang");
const VERSION_TYPEDEF_JSON = join(__dirname, "../../../tests/json/data/version_typedef/version_typedef.yang.json");

// Validation of typedef pattern values: tests/cases/types/typedef-pattern
describe("python parity: json/test_typedef", () => {
  let fromYang: YangModule;
  let fromJson: YangModule;

  beforeAll(() => {
    fromYang = parseYangFile(VERSION_TYPEDEF_YANG);
    fromJson = parseJsonSchema(JSON.parse(readFileSync(VERSION_TYPEDEF_JSON, "utf-8")) as Record<string, unknown>);
  });

  it("loads typedef model from .yang and .yang.json with same key shape", () => {
    expect(fromYang.name).toBe(fromJson.name);
    expect(Object.keys(fromYang.typedefs).sort()).toEqual(Object.keys(fromJson.typedefs).sort());
    expect(fromYang.findStatement("data-model")?.findStatement("version")).toBeDefined();
    expect(fromJson.findStatement("data-model")?.findStatement("version")).toBeDefined();
  });
});
