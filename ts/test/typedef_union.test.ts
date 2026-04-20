import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_typedef_union", () => {
  it("typedef union: primitive-type and composite-type enumerations", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef primitive-type {
    type enumeration {
      enum string;
      enum integer;
      enum number;
      enum boolean;
    }
  }

  typedef composite-type {
    type enumeration {
      enum composite;
    }
  }

  typedef field-type {
    type union {
      type primitive-type;
      type composite-type;
    }
  }

  container data {
    leaf type {
      type field-type;
      mandatory true;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    for (const v of ["string", "integer", "number", "boolean"]) {
      const result = validator.validate({ data: { type: v } });
      expect(result.isValid, `primitive '${v}': ${result.errors.join("; ")}`).toBe(true);
      expect(result.errors).toEqual([]);
    }

    const composite = validator.validate({ data: { type: "composite" } });
    expect(composite.isValid, composite.errors.join("; ")).toBe(true);
    expect(composite.errors).toEqual([]);

    const invalid = validator.validate({ data: { type: "invalid_type" } });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
    expect(invalid.errors.some((e) => e.toLowerCase().includes("union member type"))).toBe(true);
  });

  it("typedef union: string pattern and enumeration", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef string-pattern {
    type string {
      pattern '^[A-Z][a-z]+$';
    }
  }

  typedef status-enum {
    type enumeration {
      enum active;
      enum inactive;
      enum pending;
    }
  }

  typedef status-type {
    type union {
      type string-pattern;
      type status-enum;
    }
  }

  container data {
    leaf status {
      type status-type;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    for (const status of ["active", "inactive"]) {
      const result = validator.validate({ data: { status } });
      expect(result.isValid, result.errors.join("; ")).toBe(true);
    }

    for (const status of ["Hello", "World"]) {
      const result = validator.validate({ data: { status } });
      expect(result.isValid, result.errors.join("; ")).toBe(true);
    }

    const invalid1 = validator.validate({ data: { status: "invalid" } });
    expect(invalid1.isValid).toBe(false);
    expect(invalid1.errors.length).toBeGreaterThan(0);

    const invalid2 = validator.validate({ data: { status: "hello" } });
    expect(invalid2.isValid).toBe(false);
    expect(invalid2.errors.length).toBeGreaterThan(0);
  });

  it("typedef union: three member typedefs", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef type-a {
    type enumeration {
      enum a1;
      enum a2;
    }
  }

  typedef type-b {
    type enumeration {
      enum b1;
      enum b2;
    }
  }

  typedef type-c {
    type enumeration {
      enum c1;
      enum c2;
    }
  }

  typedef multi-union {
    type union {
      type type-a;
      type type-b;
      type type-c;
    }
  }

  container data {
    leaf value {
      type multi-union;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    for (const value of ["a1", "b2", "c1"]) {
      const result = validator.validate({ data: { value } });
      expect(result.isValid, result.errors.join("; ")).toBe(true);
    }

    const invalid = validator.validate({ data: { value: "invalid" } });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
  });

  it("typedef union: nested typedefs (field-type)", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef primitive-type {
    type enumeration {
      enum string;
      enum integer;
      enum number;
      enum boolean;
      enum array;
    }
  }

  typedef composite-type {
    type enumeration {
      enum composite;
    }
  }

  typedef field-type {
    type union {
      type primitive-type;
      type composite-type;
    }
  }

  container data {
    leaf field_type {
      type field-type;
      mandatory true;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    for (const primitive of ["string", "integer", "number", "boolean", "array"]) {
      const result = validator.validate({ data: { field_type: primitive } });
      expect(result.isValid, `'${primitive}': ${result.errors.join("; ")}`).toBe(true);
    }

    const composite = validator.validate({ data: { field_type: "composite" } });
    expect(composite.isValid, composite.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ data: { field_type: "invalid" } });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
  });

  it("typedef union: empty union rejects values", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef empty-union {
    type union {
    }
  }

  container data {
    leaf value {
      type empty-union;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    const result = validator.validate({ data: { value: "anything" } });
    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("typedef union: used on list leaf", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef primitive-type {
    type enumeration {
      enum string;
      enum integer;
    }
  }

  typedef composite-type {
    type enumeration {
      enum composite;
    }
  }

  typedef field-type {
    type union {
      type primitive-type;
      type composite-type;
    }
  }

  list items {
    key id;
    leaf id {
      type string;
    }
    leaf type {
      type field-type;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    const valid = validator.validate({
      items: [
        { id: "item1", type: "string" },
        { id: "item2", type: "integer" },
        { id: "item3", type: "composite" }
      ]
    });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({
      items: [
        { id: "item1", type: "string" },
        { id: "item2", type: "invalid" }
      ]
    });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
  });
});
