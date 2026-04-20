import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";
import { TypeConstraint, TypeSystem } from "../src/types";

describe("basic TypeScript parity tests", () => {
  it("parses a simple module", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    expect(module.name).toBe("test");
    expect(module.yangVersion).toBe("1.1");
    expect(module.namespace).toBe("urn:test");
    expect(module.prefix).toBe("t");
  });

  it("parses block comments and preserves comment-like text in strings", () => {
    const yangContent = `
module test {
  /* single-line block comment */
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  /*
   * multi-line
   * block comment
   */
  container data {
    leaf name {
      type string;
      description "path /* not a comment */ here";
    }
  }
}
`;
    const module = parseYangString(yangContent);
    expect(module.name).toBe("test");
    expect(module.yangVersion).toBe("1.1");

    const data = module.findStatement("data");
    expect(data).toBeDefined();
    const nameLeaf = data?.findStatement("name");
    expect(nameLeaf).toBeDefined();
    expect(String(nameLeaf?.data.description ?? "")).toContain("/* not a comment */");
  });

  it("parses typedef declarations", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef entity-name {
    type string {
      length "1..64";
      pattern '[a-z_][a-z0-9_]*';
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const typedef = module.typedefs["entity-name"] as { type?: { name?: string } } | undefined;
    expect(typedef).toBeDefined();
    expect(typedef?.type).toBeDefined();
    expect(typedef?.type?.name).toBe("string");
  });

  it("validates core built-in types", () => {
    const typeSystem = new TypeSystem();

    let isValid = typeSystem.validate("test", "string")[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate(42, "int32")[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate(9_999_999_999, "int32")[0];
    expect(isValid).toBe(false);

    isValid = typeSystem.validate(255, "uint8")[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate(256, "uint8")[0];
    expect(isValid).toBe(false);

    isValid = typeSystem.validate(true, "boolean")[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate("true", "boolean")[0];
    expect(isValid).toBe(true);
  });

  it("validates pattern and length constraints", () => {
    const typeSystem = new TypeSystem();

    let constraint = new TypeConstraint({ pattern: "[a-z_][a-z0-9_]*" });
    let isValid = typeSystem.validate("valid_name", "string", constraint)[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate("InvalidName", "string", constraint)[0];
    expect(isValid).toBe(false);

    constraint = new TypeConstraint({ length: "1..10" });
    isValid = typeSystem.validate("short", "string", constraint)[0];
    expect(isValid).toBe(true);

    isValid = typeSystem.validate("this is too long", "string", constraint)[0];
    expect(isValid).toBe(false);
  });

  it("validates simple module data and mandatory leaves", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
      mandatory true;
    }
    leaf count {
      type uint8;
      default 0;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const validator = new YangValidator(module);

    const validResult = validator.validate({
      data: {
        name: "test"
      }
    });
    expect(validResult.isValid).toBe(true);

    const invalidResult = validator.validate({
      data: {
        count: 5
      }
    });
    expect(invalidResult.isValid).toBe(false);
    expect(invalidResult.errors.length).toBeGreaterThan(0);
  });

  it("accepts ordered-by on list and leaf-list", () => {
    const yangContent = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    list items {
      key "name";
      ordered-by user;
      leaf name {
        type string;
      }
    }
    leaf-list tags {
      type string;
      ordered-by system;
    }
  }
}
`;
    const module = parseYangString(yangContent);
    const data = module.findStatement("data");
    expect(data).toBeDefined();
    expect(data?.findStatement("items")).toBeDefined();
    expect(data?.findStatement("tags")).toBeDefined();
  });
});
