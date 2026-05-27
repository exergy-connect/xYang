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

  it("skips deviation, action, and top-level input/output; parses notification and leaf a", () => {
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
    const joined = warnSpy.mock.calls.map((c: unknown[]) => String(c[0])).join(" ").toLowerCase();
    for (const kw of ["deviation", "action", "input", "output"]) {
      expect(joined).toContain(kw);
    }
    expect(joined).not.toContain("rpc");
    expect(joined).not.toContain("notification");
    const reset = mod.findStatement("reset");
    expect(reset?.keyword).toBe("rpc");
    expect(reset?.name).toBe("reset");
    const done = mod.findStatement("done");
    expect(done?.name).toBe("done");
    const leaf = mod.findStatement("a");
    expect(leaf?.name).toBe("a");
  });

  it("rejects rpc inside container", () => {
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
    expect(() => parseYangString(yang)).toThrow(/rpc/i);
  });
});
