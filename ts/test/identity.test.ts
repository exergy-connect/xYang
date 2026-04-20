import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

/** Minimal YANG 1.1 module: base identity, derived identity, leaf with identityref. */
const MINIMAL_IDENTITY_YANG = `
module identity-test {
  yang-version 1.1;
  namespace "urn:identity-test";
  prefix "it";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
`;

/** `must` on `data`: `kind` must name an identity derived from `mammal` */
const IDENTITY_YANG_MUST_DERIVED_FROM = `
module identity-must-derived-from {
  yang-version 1.1;
  namespace "urn:identity-must-derived-from";
  prefix "im";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    must "derived-from(kind, 'im:mammal')";

    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
`;

const IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF = `
module identity-must-derived-from-or-self {
  yang-version 1.1;
  namespace "urn:identity-must-derived-from-or-self";
  prefix "io";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    must "derived-from-or-self(kind, 'io:mammal')";

    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
`;

const IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING = `
module identity-must-sibling {
  yang-version 1.1;
  namespace "urn:identity-must-sibling";
  prefix "is";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    leaf kind {
      type identityref {
        base animal;
      }
    }
    leaf label {
      type string;
      must "derived-from(../kind, 'is:mammal')";
    }
  }
}
`;

describe("python parity: test_identity", () => {
  it("parses a module with identity statements and an identityref leaf", () => {
    const module = parseYangString(MINIMAL_IDENTITY_YANG);
    expect(module.name).toBe("identity-test");
    expect("animal" in module.identities).toBe(true);
    expect(module.identities.dog?.bases).toEqual(["mammal"]);
  });

  it("parses must using derived-from(identityref, identity) (RFC 7950)", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM);
    expect(module.name).toBe("identity-must-derived-from");
  });

  it("parses must using derived-from-or-self(identityref, identity) (RFC 7950)", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF);
    expect(module.name).toBe("identity-must-derived-from-or-self");
  });

  it("parses must on a leaf that constrains a sibling identityref via derived-from", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING);
    expect(module.name).toBe("identity-must-sibling");
  });

  it("validate must derived-from accepts mammal descendant", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { kind: "im:dog" } });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });

  it("validate must derived-from rejects base-only identity", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { kind: "im:animal" } });
    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("validate must derived-from-or-self accepts exact base", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { kind: "io:mammal" } });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });

  it("validate must on sibling when identityref satisfies derived-from", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { kind: "is:dog", label: "x" } });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });

  it("validate must on sibling fails when identityref not mammal lineage", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING);
    const validator = new YangValidator(module);
    const result = validator.validate({ data: { kind: "is:animal", label: "x" } });
    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});
