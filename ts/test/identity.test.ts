import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";

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

describe("python parity: test_identity", () => {
  // Validation coverage: tests/cases/references/identityref,
  // tests/cases/references/identityref-must-derived-from

  it("parses a module with identity statements and an identityref leaf", () => {
    const module = parseYangString(MINIMAL_IDENTITY_YANG);
    expect(module.name).toBe("identity-test");
    expect("animal" in module.identities).toBe(true);
    expect(module.identities.dog?.bases).toEqual([{ name: "mammal" }]);
  });

  it("parses must using derived-from(identityref, identity) (RFC 7950)", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM);
    expect(module.name).toBe("identity-must-derived-from");
  });

  it("parses must using derived-from-or-self(identityref, identity) (RFC 7950)", () => {
    const module = parseYangString(IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF);
    expect(module.name).toBe("identity-must-derived-from-or-self");
  });
});
