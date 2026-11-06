import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const model = parseYangString(`
module strict {
  namespace "urn:strict";
  prefix s;
  container topology {
    presence "Configured topology";
    leaf device { type string; }
    container empty {}
    choice mode {
      case routed { container routing { leaf enabled { type boolean; } } }
      case bridged { leaf bridge { type string; } }
    }
    list nodes { key "name"; leaf name { type string; } }
    anydata metadata;
    anyxml payload;
  }
}`);
const validator = new YangValidator(model);

describe("unknown fields", () => {
  it.each([
    [{ typo: true }, "Unknown field 'typo'"],
    [{ topology: { deviceX: "frr" } }, "topology: Unknown field 'deviceX'"],
    [{ topology: { empty: { extra: 1 } } }, "topology.empty: Unknown field 'extra'"],
    [{ topology: { routing: { enable: true } } }, "topology.mode.routing: Unknown field 'enable'"],
    [{ topology: { nodes: [{ name: "a", extra: 1 }] } }, "topology.nodes[0]: Unknown field 'extra'"]
  ])("rejects unknown members in %j", (data, error) => {
    const result = validator.validate(data);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain(error);
  });

  it("accepts modeled choice children and opaque payload contents", () => {
    expect(validator.validate({ topology: {
      device: "frr", empty: {}, routing: { enabled: true },
      nodes: [{ name: "a" }], metadata: { arbitrary: { nested: true } },
      payload: { arbitrary: true }
    } }).errors).toEqual([]);
  });

  it("does not treat a choice or case name as an instance member", () => {
    expect(validator.validate({ topology: { mode: {}, routed: {} } }).errors)
      .toEqual(["topology: Unknown field 'mode'", "topology: Unknown field 'routed'"]);
  });
});
