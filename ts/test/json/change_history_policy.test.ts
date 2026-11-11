import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile, type YangModule } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const YANG_FILE = join(__dirname, "../../../tests/json/data/change_history_policy/change_history_policy.yang");
const YANG_JSON_FILE = join(__dirname, "../../../tests/json/data/change_history_policy/change_history_policy.yang.json");

// Validation of uint32 | '*': tests/cases/types/typedef-union-star
describe("python parity: json/test_change_history_policy", () => {
  let fromYang: YangModule;
  let fromJson: YangModule;

  beforeAll(() => {
    fromYang = parseYangFile(YANG_FILE);
    fromJson = parseJsonSchema(JSON.parse(readFileSync(YANG_JSON_FILE, "utf-8")) as Record<string, unknown>);
  });

  it("loads YANG and YANG-JSON with matching model shape", () => {
    expect(fromYang.name).toBe(fromJson.name);
    expect(Object.keys(fromYang.typedefs).sort()).toEqual(Object.keys(fromJson.typedefs).sort());
    expect(fromYang.findStatement("data-model")?.findStatement("change_history_policy")).toBeDefined();
    expect(fromJson.findStatement("data-model")?.findStatement("change_history_policy")).toBeDefined();
  });
});
