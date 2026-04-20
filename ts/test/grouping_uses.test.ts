import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

describe("python parity: test_grouping_uses", () => {
  it("basic grouping and uses validates mandatory leaf from grouping", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping common-fields {
    leaf name {
      type string;
      mandatory true;
    }
    leaf description {
      type string;
    }
  }

  container data {
    uses common-fields;
    leaf value {
      type int32;
    }
  }
}
`;
    const module = parseYangString(yang);
    expect(module.name).toBe("test");
    const validator = new YangValidator(module);

    const valid = validator.validate({
      data: { name: "test_name", description: "test description", value: 42 }
    });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({
      data: { description: "test description", value: 42 }
    });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
  });

  it("grouping with refine adds must on refined leaf", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-field {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      default "string";
    }
  }

  container data {
    uses base-field {
      refine type {
        must ". != 'invalid'" {
          error-message "Type cannot be invalid";
        }
      }
    }
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({ data: { name: "test", type: "string" } });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ data: { name: "field1", type: "invalid" } });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.length).toBeGreaterThan(0);
    expect(
      invalid.errors.some(
        (e) => e.includes("Type cannot be invalid") || e.toLowerCase().includes("type")
      )
    ).toBe(true);
  });

  it("nested grouping (uses base inside extended)", () => {
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
  }

  grouping extended-fields {
    uses base-fields;
    leaf name {
      type string;
    }
  }

  container data {
    uses extended-fields;
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({ data: { id: "123", name: "test" } });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ data: { name: "test" } });
    expect(invalid.isValid).toBe(false);
  });

  it("uses inside list", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping item-fields {
    leaf name {
      type string;
      mandatory true;
    }
    leaf value {
      type int32;
    }
  }

  list items {
    key name;
    uses item-fields;
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({
      items: [
        { name: "item1", value: 10 },
        { name: "item2", value: 20 }
      ]
    });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ items: [{ value: 10 }] });
    expect(invalid.isValid).toBe(false);
  });

  it("composite-style nested groupings in list", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping composite-field {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      mandatory true;
    }
  }

  grouping field-definition {
    uses composite-field;
    leaf required {
      type boolean;
      default false;
    }
  }

  list fields {
    key name;
    uses field-definition;
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({
      fields: [
        { name: "field1", type: "string", required: true },
        { name: "field2", type: "integer" }
      ]
    });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ fields: [{ type: "string" }] });
    expect(invalid.isValid).toBe(false);
  });

  it("must in grouping uses correct sibling context", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping field-with-constraint {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      mandatory true;
    }
    leaf min {
      type int32;
      must "../type = 'integer' or ../type = 'number'" {
        error-message "min can only be used with integer or number types";
      }
    }
  }

  container data {
    uses field-with-constraint;
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    const valid = validator.validate({ data: { name: "age", type: "integer", min: 0 } });
    expect(valid.isValid, valid.errors.join("; ")).toBe(true);

    const invalid = validator.validate({ data: { name: "name", type: "string", min: 0 } });
    expect(invalid.isValid).toBe(false);
    expect(
      invalid.errors.some(
        (e) =>
          e.includes("min can only be used with integer or number types") ||
          e.toLowerCase().includes("min")
      )
    ).toBe(true);
  });

  it("must from refine on leaf under uses", () => {
    const yang = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-field {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      mandatory true;
    }
  }

  container data {
    uses base-field {
      refine type {
        must ". != 'invalid'" {
          error-message "Type cannot be invalid";
        }
      }
    }
  }
}
`;
    const module = parseYangString(yang);
    const validator = new YangValidator(module);

    expect(validator.validate({ data: { name: "field1", type: "string" } }).isValid).toBe(true);

    const invalid = validator.validate({ data: { name: "field1", type: "invalid" } });
    expect(invalid.isValid).toBe(false);
    expect(
      invalid.errors.some(
        (e) => e.includes("Type cannot be invalid") || e.toLowerCase().includes("type")
      )
    ).toBe(true);
  });

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
