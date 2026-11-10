import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";

describe("python parity: test_bits", () => {
  const BITS_TYPEDEF_MODULE = `
module bits-test {
  yang-version 1.1;
  namespace "urn:test:bits";
  prefix "t";

  typedef flags {
    type bits {
      bit execute { position 0; description "run"; }
      bit read { position 2; }
      bit write;
    }
  }

  container top {
    leaf mode {
      type flags;
    }
  }
}
`;

  it("parses bits typedef metadata", () => {
    const module = parseYangString(BITS_TYPEDEF_MODULE);
    const typedef = module.typedefs.flags as { type?: { name?: string; bits?: Array<{ name: string }> } } | undefined;

    expect(typedef?.type?.name).toBe("bits");
    expect((typedef?.type?.bits ?? []).map((bit) => bit.name)).toEqual(["execute", "read", "write"]);
  });

});
