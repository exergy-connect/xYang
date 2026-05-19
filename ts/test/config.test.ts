import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseYangString } from "../src";
import { XYANG_KEYS } from "../src/json/schema-keys";

describe("config (RFC 7950 §7.21.1)", () => {
  it("stores config false on container", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container state-tree {
    config false;
    leaf x { type string; }
  }
}
`);
    const c = mod.findStatement("state-tree");
    expect((c?.data as { config?: boolean }).config).toBe(false);
  });

  it("emits config in JSON Schema x-yang", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  leaf ro { type string; config false; }
}
`);
    const schema = generateJsonSchema(mod);
    const ro = (schema.properties as Record<string, unknown>).ro as Record<string, unknown>;
    expect((ro["x-yang"] as Record<string, unknown>)[XYANG_KEYS.config]).toBe(false);
  });
});
