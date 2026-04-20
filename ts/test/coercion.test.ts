import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

function validateWithYang(yang: string, data: Record<string, unknown>) {
  const module = parseYangString(yang);
  const validator = new YangValidator(module);
  return validator.validate(data);
}

describe("python parity: test_coercion", () => {
  const BOOLEAN_EQ_TRUE_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type boolean;
      must "current() = true()";
    }
  }
}
`;

  const BOOLEAN_NE_FALSE_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type boolean;
      must "current() != false()";
    }
  }
}
`;

  const BOOLEAN_FN_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type boolean;
      must "boolean(current()) = true()";
    }
  }
}
`;

  const INT_GT_ZERO_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
`;

  const LEAF_LIST_BOOL_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list flags {
      type boolean;
      must "current() = true()";
    }
  }
}
`;

  const LEAF_LIST_INT_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list counts {
      type int32;
      must "current() > 0";
    }
  }
}
`;

  const NESTED_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    container inner {
      leaf enabled {
        type boolean;
        must "current() = true()";
      }
      leaf count {
        type int32;
        must "current() > 0";
      }
    }
  }
}
`;

  it("boolean coercion: string true passes current() = true() and input is unchanged", () => {
    const data = { data: { enabled: "true" } };
    const result = validateWithYang(BOOLEAN_EQ_TRUE_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(typeof data.data.enabled).toBe("string");
    expect(data.data.enabled).toBe("true");
  });

  it("boolean coercion: string false passes current() != false() and input is unchanged", () => {
    const data = { data: { enabled: "false" } };
    const result = validateWithYang(BOOLEAN_NE_FALSE_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(typeof data.data.enabled).toBe("string");
    expect(data.data.enabled).toBe("false");
  });

  it("boolean(current()) treats non-empty strings as truthy", () => {
    const data1 = { data: { enabled: "true" } };
    const data2 = { data: { enabled: "false" } };
    const result1 = validateWithYang(BOOLEAN_FN_YANG, data1);
    const result2 = validateWithYang(BOOLEAN_FN_YANG, data2);
    expect(result1.isValid, result1.errors.join("; ")).toBe(true);
    expect(result2.isValid, result2.errors.join("; ")).toBe(true);
  });

  it("int32 coercion: positive digit string passes current() > 0 and input is unchanged", () => {
    const data = { data: { count: "123" } };
    const result = validateWithYang(INT_GT_ZERO_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(typeof data.data.count).toBe("string");
    expect(data.data.count).toBe("123");
  });

  it("int32 coercion: negative digit string fails current() > 0 and input is unchanged", () => {
    const data = { data: { count: "-5" } };
    const result = validateWithYang(INT_GT_ZERO_YANG, data);
    expect(result.isValid).toBe(false);
    expect(typeof data.data.count).toBe("string");
    expect(data.data.count).toBe("-5");
  });

  it("int32 must constraint works for both passing and failing coerced string values", () => {
    const passData = { data: { count: "123" } };
    const failData = { data: { count: "-5" } };
    expect(validateWithYang(INT_GT_ZERO_YANG, passData).isValid).toBe(true);
    expect(validateWithYang(INT_GT_ZERO_YANG, failData).isValid).toBe(false);
  });

  it("already-typed boolean remains unchanged and validates", () => {
    const data = { data: { enabled: true } };
    const originalValue = data.data.enabled;
    const result = validateWithYang(BOOLEAN_EQ_TRUE_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(data.data.enabled).toBe(originalValue);
  });

  it("already-typed int32 remains unchanged and validates", () => {
    const data = { data: { count: 42 } };
    const originalValue = data.data.count;
    const result = validateWithYang(INT_GT_ZERO_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(data.data.count).toBe(originalValue);
  });

  it("leaf-list boolean coercion accepts string boolean members without mutating them", () => {
    const data = { data: { flags: ["true", "false", "true"] } };
    const result = validateWithYang(LEAF_LIST_BOOL_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(data.data.flags).toEqual(["true", "false", "true"]);
    expect(data.data.flags.every((v) => typeof v === "string")).toBe(true);
  });

  it("leaf-list int32 coercion accepts string digit members without mutating them", () => {
    const data = { data: { counts: ["1", "2", "3"] } };
    const result = validateWithYang(LEAF_LIST_INT_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(data.data.counts).toEqual(["1", "2", "3"]);
    expect(data.data.counts.every((v) => typeof v === "string")).toBe(true);
  });

  it("nested container coercion works for boolean and int32 string values", () => {
    const data = {
      data: {
        inner: {
          enabled: "true",
          count: "42"
        }
      }
    };
    const result = validateWithYang(NESTED_YANG, data);
    expect(result.isValid, result.errors.join("; ")).toBe(true);
    expect(data.data.inner.enabled).toBe("true");
    expect(data.data.inner.count).toBe("42");
  });
});
