import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile, YangValidator } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const YANG_FILE = join(__dirname, "../../../tests/json/data/change_history_policy/change_history_policy.yang");
const YANG_JSON_FILE = join(__dirname, "../../../tests/json/data/change_history_policy/change_history_policy.yang.json");

const DATA_VALID_INT = {
  "data-model": {
    change_history_policy: 3
  }
};

const DATA_VALID_STAR = {
  "data-model": {
    change_history_policy: "*"
  }
};

const DATA_INVALID_NEGATIVE = {
  "data-model": {
    change_history_policy: -1
  }
};

const DATA_INVALID_STRING = {
  "data-model": {
    change_history_policy: "unlimited"
  }
};

function loadModules() {
  const fromYang = parseYangFile(YANG_FILE);
  const fromJson = parseJsonSchema(JSON.parse(readFileSync(YANG_JSON_FILE, "utf-8")) as Record<string, unknown>);
  return { fromYang, fromJson };
}

function validate(moduleData: ReturnType<typeof loadModules>["fromYang"], data: Record<string, unknown>) {
  const result = new YangValidator(moduleData).validate(data);
  return { isValid: result.isValid, errors: result.errors };
}

describe("python parity: json/test_change_history_policy", () => {
  it("loads YANG and YANG-JSON with matching model shape", () => {
    const { fromYang, fromJson } = loadModules();

    expect(fromYang.name).toBe(fromJson.name);
    expect(Object.keys(fromYang.typedefs).sort()).toEqual(Object.keys(fromJson.typedefs).sort());
    expect(fromYang.findStatement("data-model")?.findStatement("change_history_policy")).toBeDefined();
    expect(fromJson.findStatement("data-model")?.findStatement("change_history_policy")).toBeDefined();
  });

  it("accepts valid integer value in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_VALID_INT);
    const j = validate(fromJson, DATA_VALID_INT);

    expect(y.isValid).toBe(true);
    expect(j.isValid).toBe(true);
  });

  it("accepts '*' value in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_VALID_STAR);
    const j = validate(fromJson, DATA_VALID_STAR);

    expect(y.isValid).toBe(true);
    expect(j.isValid).toBe(true);
  });

  it("rejects negative integer in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_INVALID_NEGATIVE);
    const j = validate(fromJson, DATA_INVALID_NEGATIVE);

    expect(y.isValid).toBe(j.isValid);
    expect(y.isValid).toBe(false);
    expect(y.errors.length).toBeGreaterThan(0);
    expect(j.errors.length).toBeGreaterThan(0);
  });

  it("rejects invalid string in both encodings", () => {
    const { fromYang, fromJson } = loadModules();
    const y = validate(fromYang, DATA_INVALID_STRING);
    const j = validate(fromJson, DATA_INVALID_STRING);

    expect(y.isValid).toBe(j.isValid);
    expect(y.isValid).toBe(false);
    expect(y.errors.length).toBeGreaterThan(0);
    expect(j.errors.length).toBeGreaterThan(0);
  });
});
