import { describe, expect, it, vi } from "vitest";
import { parseYangString, YangValidator } from "../src";
import * as xpathTokenizer from "../src/xpath/tokenizer";

function sumCounts(counts: Map<string, number>): number {
  return [...counts.values()].reduce((acc, count) => acc + count, 0);
}

describe("python parity: test_single_parse", () => {
  it("parses YANG XPath expressions once per unique expression during validation and reuses cache across runs", () => {
    const parsePhaseCount = new Map<string, number>();
    const validationPhaseCount = new Map<string, number>();
    let yangParsingComplete = false;

    const originalTokenize = xpathTokenizer.tokenizeXPath;
    const spy = vi.spyOn(xpathTokenizer, "tokenizeXPath").mockImplementation((expression: string) => {
      const target = yangParsingComplete ? validationPhaseCount : parsePhaseCount;
      target.set(expression, (target.get(expression) ?? 0) + 1);
      return originalTokenize(expression);
    });

    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
      must "string-length(.) > 0";
      must "string-length(.) <= 64";
    }

    leaf count {
      type uint8;
      must ". >= 0";
      must ". <= 255";
    }

    leaf status {
      type string;
      when "../count > 0";
      must ". != ''";
    }

    list items {
      key "id";
      leaf id {
        type string;
        must "string-length(.) > 0";
      }
      leaf value {
        type uint8;
        must ". >= 0";
      }
    }
  }
}
`;

    try {
      const module = parseYangString(yangContent);
      yangParsingComplete = true;

      const validator = new YangValidator(module);
      const testData = {
        data: {
          name: "test",
          count: 10,
          status: "active",
          items: [
            { id: "item1", value: 5 },
            { id: "item2", value: 10 }
          ]
        }
      };

      let firstValidationTokenizeTotal = -1;
      for (let i = 0; i < 3; i += 1) {
        const result = validator.validate(testData);
        expect(result.isValid, result.errors.join("; ")).toBe(true);

        const currentTotal = sumCounts(validationPhaseCount);
        if (i === 0) {
          firstValidationTokenizeTotal = currentTotal;
          expect(firstValidationTokenizeTotal).toBeGreaterThan(0);
        } else {
          expect(currentTotal).toBe(firstValidationTokenizeTotal);
        }
      }

      const expectedExpressions = [
        "string-length(.) > 0",
        "string-length(.) <= 64",
        ". >= 0",
        ". <= 255",
        "../count > 0",
        ". != ''"
      ];

      for (const expression of expectedExpressions) {
        expect(parsePhaseCount.has(expression), `missing parse-phase expression: ${expression}`).toBe(true);
        expect(validationPhaseCount.has(expression), `missing validation-phase expression: ${expression}`).toBe(true);
      }

      expect(parsePhaseCount.get("string-length(.) > 0")).toBeGreaterThanOrEqual(2);
      expect(parsePhaseCount.get(". >= 0")).toBeGreaterThanOrEqual(2);
      expect(validationPhaseCount.get("string-length(.) > 0")).toBe(1);
      expect(validationPhaseCount.get(". >= 0")).toBe(1);
    } finally {
      spy.mockRestore();
    }
  });
});
