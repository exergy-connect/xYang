import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_leaf_list_current", () => {
  it("current() is bound to each leaf-list value (single constraint)", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));

    expect(v.validate({ data: { values: [1, 5, 10, 50, 99] } }).isValid).toBe(true);

    const neg = v.validate({ data: { values: [1, 5, -1, 50, 99] } });
    expect(neg.isValid).toBe(false);
    expect(neg.errors.length).toBeGreaterThan(0);
    expect(neg.errors.some((e) => e.includes("values[2]") || e.includes("values"))).toBe(true);

    const zero = v.validate({ data: { values: [1, 5, 0, 50, 99] } });
    expect(zero.isValid).toBe(false);
    expect(zero.errors.length).toBeGreaterThan(0);
  });

  it("multiple must constraints with current() per element", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list scores {
      type int32;
      must "current() >= 0";
      must "current() <= 100";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));
    expect(v.validate({ data: { scores: [85, 90, 95, 100, 0] } }).isValid).toBe(true);

    const low = v.validate({ data: { scores: [85, -5, 95] } });
    expect(low.isValid).toBe(false);
    expect(low.errors.length).toBeGreaterThan(0);

    const high = v.validate({ data: { scores: [85, 150, 95] } });
    expect(high.isValid).toBe(false);
    expect(high.errors.length).toBeGreaterThan(0);
  });

  it("current() with relative path to sibling leaf", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf min_value {
      type int32;
    }
    leaf-list values {
      type int32;
      must "current() >= ../min_value";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));
    expect(
      v.validate({ data: { min_value: 10, values: [10, 15, 20, 25] } }).isValid
    ).toBe(true);

    const bad = v.validate({ data: { min_value: 10, values: [10, 5, 20, 25] } });
    expect(bad.isValid).toBe(false);
    expect(bad.errors.length).toBeGreaterThan(0);
  });

  it("empty leaf-list skips must", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));
    const r = v.validate({ data: { values: [] } });
    expect(r.isValid, r.errors.join("\n")).toBe(true);
  });

  it("single element leaf-list", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
      must "current() < 100";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));
    expect(v.validate({ data: { values: [50] } }).isValid).toBe(true);
    const bad = v.validate({ data: { values: [-1] } });
    expect(bad.isValid).toBe(false);
    expect(bad.errors.length).toBeGreaterThan(0);
  });

  it("leaf-list current() vs leaf: error targets leaf-list", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf single_value {
      type int32;
      must "current() > 0";
    }
    leaf-list multiple_values {
      type int32;
      must "current() > 0";
    }
  }
}
`;
    const v = new YangValidator(parseYangString(yang));
    const r = v.validate({ data: { single_value: 5, multiple_values: [1, -1, 3] } });
    expect(r.isValid).toBe(false);
    expect(r.errors.length).toBeGreaterThan(0);
    expect(r.errors.some((e) => e.includes("multiple_values"))).toBe(true);
  });
});
