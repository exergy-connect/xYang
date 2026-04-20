import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";
import { XPathEvaluator, type XPathContext, type XPathNode, type XPathSchema } from "../src/xpath/evaluator";
import { parseXPath } from "../src/xpath/parser";
import type { YangModule } from "../src/core/model";

/** One schema covering absolute, predicate, relative, and current() must cases (Python test_xpath_caching). */
const XPATH_CACHING_YANG = `
module xpath-caching {
  yang-version 1.1;
  namespace "urn:test:xpath-caching";
  prefix "xc";

  container top {
    leaf flag {
      type int32;
      default 0;
    }
    list items {
      key id;
      leaf id { type int32; }
      leaf ref_abs {
        type string;
        must "/top/flag = 1";
      }
      leaf ref_abs_pred {
        type string;
        must "count(/top/items[id = 1]) >= 1";
      }
      leaf ref_rel {
        type string;
        must "../../flag = 1";
      }
      leaf ref_current {
        type int32;
        must "current() = 1";
      }
      leaf ref_abs_rel_pred {
        type string;
        must "count(/top/items[../flag = 1]) >= 1";
      }
      leaf ref_abs_current_pred {
        type string;
        must "count(/top/items[current() = 1]) >= 0";
      }
    }
  }
}
`;

function cachingValidator(): YangValidator {
  return new YangValidator(parseYangString(XPATH_CACHING_YANG) as YangModule);
}

describe("python parity: test_xpath_caching", () => {
  it("absolute path must: valid when flag=1, invalid when flag=0", () => {
    const validator = cachingValidator();
    const doc1 = {
      top: {
        flag: 1,
        items: [{ id: 1, ref_abs: "ok" }]
      }
    };
    const doc2 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_abs: "bad" }]
      }
    };
    const r1 = validator.validate(doc1);
    const r2 = validator.validate(doc2);
    expect(r1.isValid, r1.errors.join("\n")).toBe(true);
    expect(r2.isValid).toBe(false);
    expect(r2.errors.some((e) => e.includes("ref_abs") || e.includes("flag"))).toBe(true);
  });

  it("absolute path with literal predicate: valid only when id=1 row exists", () => {
    const validator = cachingValidator();
    const doc1 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_abs_pred: "ok" }]
      }
    };
    const doc2 = {
      top: {
        flag: 0,
        items: [{ id: 2, ref_abs_pred: "bad" }]
      }
    };
    expect(validator.validate(doc1).isValid).toBe(true);
    const r2 = validator.validate(doc2);
    expect(r2.isValid).toBe(false);
    expect(r2.errors.some((e) => e.includes("ref_abs_pred"))).toBe(true);
  });

  it("relative path must on leaf: ../../flag = 1", () => {
    const validator = cachingValidator();
    const doc1 = {
      top: {
        flag: 1,
        items: [{ id: 1, ref_rel: "ok" }]
      }
    };
    const doc2 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_rel: "bad" }]
      }
    };
    expect(validator.validate(doc1).isValid).toBe(true);
    const r2 = validator.validate(doc2);
    expect(r2.isValid).toBe(false);
    expect(r2.errors.some((e) => e.includes("ref_rel"))).toBe(true);
  });

  it("absolute path with relative predicate in brackets", () => {
    const validator = cachingValidator();
    const doc1 = {
      top: {
        flag: 1,
        items: [{ id: 1, ref_abs_rel_pred: "ok" }]
      }
    };
    const doc2 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_abs_rel_pred: "bad" }]
      }
    };
    expect(validator.validate(doc1).isValid).toBe(true);
    const r2 = validator.validate(doc2);
    expect(r2.isValid).toBe(false);
    expect(r2.errors.some((e) => e.includes("ref_abs_rel_pred"))).toBe(true);
  });

  it("current() = 1 on leaf ref_current", () => {
    const validator = cachingValidator();
    const doc1 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_current: 1 }]
      }
    };
    const doc2 = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_current: 2 }]
      }
    };
    expect(validator.validate(doc1).isValid).toBe(true);
    const r2 = validator.validate(doc2);
    expect(r2.isValid).toBe(false);
    expect(r2.errors.some((e) => e.includes("ref_current"))).toBe(true);
  });

  it("non-cacheable predicate with current() still validates", () => {
    const validator = cachingValidator();
    const doc = {
      top: {
        flag: 0,
        items: [{ id: 1, ref_abs_current_pred: "ok" }]
      }
    };
    const r = validator.validate(doc);
    expect(r.isValid, r.errors.join("\n")).toBe(true);
  });

  it("XPathEvaluator: /top/flag = 1 and /top/flag = 1 evaluates true on instance", () => {
    const mod = parseYangString(XPATH_CACHING_YANG) as YangModule;
    const data = { top: { flag: 1 } };
    const root: XPathNode = { data, schema: mod as unknown as XPathSchema, parent: null };
    const ctx: XPathContext = { current: root, root };
    const ev = new XPathEvaluator();
    const ast = parseXPath("/top/flag = 1 and /top/flag = 1");
    const result = ev.eval(ast, ctx, root);
    expect(result).toBe(true);
  });
});
