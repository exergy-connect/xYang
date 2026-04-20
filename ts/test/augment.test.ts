import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";

describe("python parity: test_augment", () => {
  it("parses augment path and merges body statements into augment node shape", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  container a {
    leaf x { type string; }
  }

  augment "/m:a" {
    leaf y { type int32; }
  }
}
`);

    const augment = module.statements.find((stmt) => stmt.keyword === "augment");
    expect(augment).toBeDefined();
    expect(augment?.argument).toBe("/m:a");

    const y = augment?.findStatement("y");
    expect(y?.keyword).toBe("leaf");
    expect((y?.data.type as Record<string, unknown> | undefined)?.name).toBe("int32");
  });

  it("parses concatenated string form for augment path", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  augment "/m:" + "a" {
    leaf y { type string; }
  }
}
`);

    const augment = module.statements.find((stmt) => stmt.keyword === "augment");
    expect(augment?.argument).toBe("/m:a");
    expect(augment?.findStatement("y")?.keyword).toBe("leaf");
  });

  it("captures augment-level if-feature metadata", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature f;

  augment "/m:a" {
    if-feature "f";
    leaf z { type string; }
  }
}
`);

    const augment = module.statements.find((stmt) => stmt.keyword === "augment");
    expect(augment?.data.if_features).toEqual(["f"]);
  });
});
