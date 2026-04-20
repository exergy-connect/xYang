import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator } from "../src";

const MINIMAL_MODULE_YANG = `
module iid-test {
  yang-version 1.1;
  namespace "urn:iid-test";
  prefix "iid";

  container data-model {
    container top {
      leaf x {
        type string;
      }
    }
    leaf ptr {
      type instance-identifier {
        require-instance true;
      }
    }
    leaf ptr_loose {
      type instance-identifier {
        require-instance false;
      }
    }
  }
}
`;

describe("python parity: test_instance_identifier", () => {
  it("accepts absolute path when target exists and require-instance is true", () => {
    const module = parseYangString(MINIMAL_MODULE_YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      "data-model": {
        top: { x: "hello" },
        ptr: "/data-model/top/x",
        ptr_loose: "not-a-valid-path-syntax-("
      }
    });

    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("rejects path when require-instance is true and target is missing", () => {
    const module = parseYangString(MINIMAL_MODULE_YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      "data-model": {
        top: { x: "hello" },
        ptr: "/data-model/top/missing-leaf",
        ptr_loose: "/any"
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("instance-identifier"))).toBe(true);
  });

  it("rejects non-absolute paths when require-instance is true", () => {
    const module = parseYangString(MINIMAL_MODULE_YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      "data-model": {
        top: { x: "hello" },
        ptr: "top/x",
        ptr_loose: "x"
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("absolute"))).toBe(true);
  });

  it("generateJsonSchema → parseJsonSchema preserves instance-identifier and require-instance", () => {
    const module = parseYangString(MINIMAL_MODULE_YANG);
    const schema = generateJsonSchema(module);
    const module2 = parseJsonSchema(schema);
    const dm = module2.findStatement("data-model");
    expect(dm).toBeDefined();

    const ptr = dm?.findStatement("ptr");
    const ptrType = ptr?.data.type as Record<string, unknown> | undefined;
    expect(ptrType?.name).toBe("instance-identifier");
    expect(ptrType?.require_instance).toBe(true);

    const loose = dm?.findStatement("ptr_loose");
    const looseType = loose?.data.type as Record<string, unknown> | undefined;
    expect(looseType?.name).toBe("instance-identifier");
    expect(looseType?.require_instance).toBe(false);
  });

  it("validates instance data from a module reparsed from JSON Schema like the original YANG", () => {
    const module = parseYangString(MINIMAL_MODULE_YANG);
    const schema = generateJsonSchema(module);
    const reparsed = parseJsonSchema(schema);
    const validator = new YangValidator(reparsed);
    const result = validator.validate({
      "data-model": { top: { x: "a" }, ptr: "/data-model/top/x", ptr_loose: "x" }
    });

    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });
});
