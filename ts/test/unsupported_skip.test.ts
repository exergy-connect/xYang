import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseYangString } from "../src";

describe("python parity: test_unsupported_skip", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("skips deviation, rpc, action, notification, input, output and still parses leaf a", () => {
    const yang = `
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  deviation /ex:foo { deviate not-supported; }
  extension ext { argument name; }
  rpc reset {
    input { leaf in-arg { type string; } }
    output { leaf out-arg { type string; } }
  }
  action "entity" {
    input { leaf x { type empty; } }
  }
  notification done { leaf msg { type string; } }
  input { leaf in-top { type empty; } }
  output { leaf out-top { type empty; } }
  leaf a { type string; }
}
`;
    const mod = parseYangString(yang);
    const joined = warnSpy.mock.calls.map((c) => String(c[0])).join(" ").toLowerCase();
    for (const kw of ["deviation", "rpc", "action", "notification", "input", "output"]) {
      expect(joined).toContain(kw);
    }
    const leaf = mod.findStatement("a");
    expect(leaf?.name).toBe("a");
  });

  it("skips rpc inside container and still parses sibling leaf x", () => {
    const yang = `
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  container c {
    rpc inner { }
    leaf x { type int8; }
  }
}
`;
    const mod = parseYangString(yang);
    expect(warnSpy.mock.calls.some((c) => String(c[0]).toLowerCase().includes("rpc"))).toBe(true);
    const c = mod.findStatement("c");
    expect(c).toBeDefined();
    const names = new Set(c?.statements.map((s) => s.name).filter(Boolean));
    expect(names.has("x")).toBe(true);
  });
});
