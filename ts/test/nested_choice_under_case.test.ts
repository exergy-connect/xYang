import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const YANG_NESTED_UNDER_CASE = `
module nested_choice_under_case {
  yang-version 1.1;
  namespace "urn:test:nested-choice-under-case";
  prefix "nc";

  container root {
    choice outer {
      mandatory true;
      case inner_wrap {
        choice inner {
          mandatory true;
          case a_case {
            leaf primitive {
              type string;
            }
          }
          case b_case {
            leaf other {
              type string;
            }
          }
        }
      }
      case c_case {
        leaf alt {
          type string;
        }
      }
    }
  }
}
`;

const YANG_NESTED_PRIMITIVE_OR_ENUM = `
module nested_primitive_or_enum {
  yang-version 1.1;
  namespace "urn:test:nested-primitive-or-enum";
  prefix "pe";

  container root {
    choice outer {
      mandatory true;
      case inner_wrap {
        choice inner {
          mandatory true;
          case open_primitive {
            leaf primitive {
              type string;
            }
          }
          case closed_enum {
            leaf-list enum {
              type string;
            }
          }
        }
      }
      case c_case {
        leaf alt {
          type string;
        }
      }
    }
  }
}
`;

describe("python parity: test_nested_choice_under_case", () => {
  const validator = new YangValidator(parseYangString(YANG_NESTED_UNDER_CASE));

  it("outer leaf branch still validates", () => {
    const { isValid, errors } = validator.validate({ root: { alt: "z" } });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("flat inner primitive validates", () => {
    const { isValid, errors } = validator.validate({ root: { primitive: "hello" } });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("flat inner other validates", () => {
    const { isValid, errors } = validator.validate({ root: { other: "y" } });
    expect(isValid, errors.join("\n")).toBe(true);
  });

  it("both inner branches invalid", () => {
    const { isValid, errors } = validator.validate({ root: { primitive: "a", other: "b" } });
    expect(isValid).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
    const joined = errors.join(" ").toLowerCase();
    expect(joined.includes("only one case") || joined.includes("multiple cases")).toBe(true);
  });

  it("inner and outer alt invalid", () => {
    const { isValid, errors } = validator.validate({ root: { primitive: "a", alt: "z" } });
    expect(isValid).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
    const joined = errors.join(" ").toLowerCase();
    expect(joined.includes("only one case") || joined.includes("multiple cases")).toBe(true);
    expect(joined.includes("outer")).toBe(true);
  });

  const validatorPrimitiveOrEnum = new YangValidator(parseYangString(YANG_NESTED_PRIMITIVE_OR_ENUM));

  it("primitive and enum list together invalid", () => {
    const { isValid, errors } = validatorPrimitiveOrEnum.validate({
      root: { primitive: "string", enum: ["G", "O"] }
    });
    expect(isValid).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
    const joined = errors.join(" ").toLowerCase();
    expect(joined.includes("only one case") || joined.includes("multiple cases")).toBe(true);
  });
});
