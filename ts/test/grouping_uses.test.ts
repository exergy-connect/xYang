import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_grouping_uses", () => {
  it("must in nested grouping with list", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-fields {
    leaf id {
      type string;
      mandatory true;
    }
    leaf status {
      type string;
      must "../id != ''" {
        error-message "id must not be empty when status is set";
      }
    }
  }

  grouping extended-fields {
    uses base-fields;
    leaf name {
      type string;
    }
  }

  list items {
    key id;
    uses extended-fields;
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({
      items: [{ id: "item1", status: "active", name: "Item 1" }]
    });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);
  });

  it("when on choice, case, and uses under case (flat data under container)", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test:uses-when-choice";
  prefix "t";

  grouping extended-body {
    leaf extension-note {
      type string;
      mandatory true;
    }
  }

  container data {
    leaf profile {
      type string;
      default "basic";
    }
    choice payload {
      when "./profile != 'off'";
      case basic-case {
        when "./profile = 'basic'";
        leaf title {
          type string;
          mandatory true;
        }
      }
      case extended-case {
        uses extended-body {
          when "./profile = 'extended'";
        }
      }
    }
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    expect(validator.validate({ data: { profile: "basic", title: "Hello" } }).isValid).toBe(true);
    expect(
      validator.validate({ data: { profile: "extended", "extension-note": "more detail" } }).isValid
    ).toBe(true);

    const off = validator.validate({ data: { profile: "off", title: "no payload when profile is off" } });
    expect(off.isValid).toBe(false);
    expect(off.errors.length).toBeGreaterThan(0);

    const wrongCase = validator.validate({
      data: { profile: "extended", title: "wrong case for profile=extended" }
    });
    expect(wrongCase.isValid).toBe(false);

    const wrongNote = validator.validate({
      data: { profile: "basic", "extension-note": "should not apply" }
    });
    expect(wrongNote.isValid).toBe(false);
    expect(wrongNote.errors.length).toBeGreaterThan(0);
  });
});
