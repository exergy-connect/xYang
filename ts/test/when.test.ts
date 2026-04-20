import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";
import { parseXPath } from "../src/xpath/parser";
import { XPathContext, XPathEvaluator, XPathNode, XPathSchema } from "../src/xpath/evaluator";

describe("python parity: test_when", () => {
  function xpathBoolean(value: unknown): boolean {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0 && !Number.isNaN(value);
    }
    if (typeof value === "string") {
      return value.length > 0;
    }
    return value !== null && value !== undefined;
  }

  it("when condition true validates", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type {
      type string;
    }
    container item_type {
      when "../type = 'array'";
      description "Only present when type is array";
      leaf primitive {
        type string;
      }
    }
  }
}
`);

    const dataModel = module.findStatement("data");
    const itemType = dataModel?.findStatement("item_type");
    const whenShape = itemType?.data.when as Record<string, unknown> | undefined;
    expect(whenShape?.expression).toBe("../type = 'array'");

    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        type: "array",
        item_type: {
          primitive: "string"
        }
      }
    });
    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("parses braced when form with description", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf mode {
      type string;
    }
    leaf extra {
      when "../mode = 'on'" {
        description "Only when mode is on.";
      }
      type string;
    }
  }
}
`);

    const dataModel = module.findStatement("data");
    const extra = dataModel?.findStatement("extra");
    const whenShape = extra?.data.when as Record<string, unknown> | undefined;

    expect(whenShape?.expression).toBe("../mode = 'on'");
    expect(String(whenShape?.description ?? "")).toContain("Only when mode is on.");
  });

  it("when false: node is optional when missing and invalid when present", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type {
      type string;
    }
    container item_type {
      when "../type = 'array'";
      description "Only present when type is array";
      leaf primitive {
        type string;
        mandatory true;
      }
    }
  }
}
`);
    const validator = new YangValidator(module);

    const missingResult = validator.validate({
      data: {
        type: "string"
      }
    });
    expect(missingResult.isValid).toBe(true);
    expect(missingResult.errors).toEqual([]);

    const presentResult = validator.validate({
      data: {
        type: "string",
        item_type: {
          primitive: "string"
        }
      }
    });
    expect(presentResult.isValid).toBe(false);
    expect(presentResult.errors.some((error) => error.toLowerCase().includes("item_type"))).toBe(true);
  });

  it("when condition with empty leaf presence/absence", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type empty;
      description "Flag leaf - no value, only presence";
    }
    container optional_section {
      when "../enabled";
      description "Only present when enabled (type empty) is present";
      leaf note {
        type string;
      }
    }
  }
}
`);
    const validator = new YangValidator(module);

    const enabledResult = validator.validate({
      data: {
        enabled: null,
        optional_section: {
          note: "enabled is set"
        }
      }
    });
    expect(enabledResult.isValid).toBe(true);
    expect(enabledResult.errors).toEqual([]);

    const disabledResult = validator.validate({
      data: {}
    });
    expect(disabledResult.isValid).toBe(true);
    expect(disabledResult.errors).toEqual([]);

    const extraResult = validator.validate({
      data: {
        optional_section: {
          note: "ignored"
        }
      }
    });
    expect(extraResult.isValid).toBe(false);
    expect(extraResult.errors.some((error) => error.includes("optional_section"))).toBe(true);
  });

  it("when expressions evaluate with XPath evaluator", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type { type string; }
    container item_type {
      when "../type = 'array'";
      leaf primitive { type string; }
    }
  }
}
`);
    const rootSchema = module as unknown as XPathSchema;
    const dataSchema = module.findStatement("data") as unknown as XPathSchema;
    const itemTypeSchema = module.findStatement("data")?.findStatement("item_type") as unknown as XPathSchema;

    const trueData = { data: { type: "array", item_type: { primitive: "string" } } };
    const trueRoot: XPathNode = { data: trueData, schema: rootSchema, parent: null };
    const trueDataNode: XPathNode = { data: trueData.data, schema: dataSchema, parent: trueRoot };
    const trueItemNode: XPathNode = { data: trueData.data.item_type, schema: itemTypeSchema, parent: trueDataNode };
    const trueContext: XPathContext = { current: trueItemNode, root: trueRoot };

    const evaluator = new XPathEvaluator();
    const expression = parseXPath("../type = 'array'");
    const trueResult = evaluator.eval(expression, trueContext, trueItemNode);
    expect(xpathBoolean(trueResult)).toBe(true);

    const falseData = { data: { type: "string", item_type: {} } };
    const falseRoot: XPathNode = { data: falseData, schema: rootSchema, parent: null };
    const falseDataNode: XPathNode = { data: falseData.data, schema: dataSchema, parent: falseRoot };
    const falseItemNode: XPathNode = { data: falseData.data.item_type, schema: itemTypeSchema, parent: falseDataNode };
    const falseContext: XPathContext = { current: falseItemNode, root: falseRoot };
    const falseResult = evaluator.eval(expression, falseContext, falseItemNode);
    expect(xpathBoolean(falseResult)).toBe(false);
  });
});
