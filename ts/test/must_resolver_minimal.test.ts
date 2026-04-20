import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("must expressions", () => {
  it("accepts primary_key when matching sibling fields via current()", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  container data-model {
    list entities {
      key "name";
      leaf name { type string; }
      leaf primary_key {
        type string;
        must "../fields[name = current()]";
      }
      list fields {
        key "name";
        leaf name { type string; }
      }
    }
  }
}
`);

    const validator = new YangValidator(module);
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "users",
            primary_key: "id",
            fields: [{ name: "id" }, { name: "email" }]
          }
        ]
      }
    });

    expect(result.isValid).toBe(true);
  });

  it("rejects primary_key when no sibling field matches", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  container data-model {
    list entities {
      key "name";
      leaf name { type string; }
      leaf primary_key {
        type string;
        must "../fields[name = current()]" {
          error-message "primary_key must reference existing field";
        }
      }
      list fields {
        key "name";
        leaf name { type string; }
      }
    }
  }
}
`);

    const validator = new YangValidator(module);
    const result = validator.validate({
      "data-model": {
        entities: [
          {
            name: "users",
            primary_key: "missing",
            fields: [{ name: "id" }]
          }
        ]
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.includes("primary_key must reference existing field"))).toBe(true);
  });

  it("supports string-length(.) must on leaf", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  container root {
    leaf name {
      type string;
      must "string-length(.) > 0";
    }
  }
}
`);

    const validator = new YangValidator(module);
    const validResult = validator.validate({ root: { name: "ok" } });
    const invalidResult = validator.validate({ root: { name: "" } });

    expect(validResult.isValid).toBe(true);
    expect(invalidResult.isValid).toBe(false);
    expect(invalidResult.errors.some((error) => error.includes("must constraint not satisfied"))).toBe(true);
  });

  it("supports absolute path with OR logic", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  container data-model {
    leaf consolidated { type boolean; }
    list items {
      key "id";
      leaf id { type string; }
      leaf type { type string; }
      leaf value {
        type string;
        must "/data-model/consolidated = false() or ../type = 'test' or . != ''";
      }
    }
  }
}
`);

    const validator = new YangValidator(module);

    const validWhenConsolidatedFalse = validator.validate({
      "data-model": {
        consolidated: false,
        items: [{ id: "1", type: "other", value: "" }]
      }
    });
    const validWhenTypeTest = validator.validate({
      "data-model": {
        consolidated: true,
        items: [{ id: "1", type: "test", value: "" }]
      }
    });
    const invalid = validator.validate({
      "data-model": {
        consolidated: true,
        items: [{ id: "1", type: "other", value: "" }]
      }
    });

    expect(validWhenConsolidatedFalse.isValid).toBe(true);
    expect(validWhenTypeTest.isValid).toBe(true);
    expect(invalid.isValid).toBe(false);
  });
});
