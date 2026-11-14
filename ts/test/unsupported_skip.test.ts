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

  it("parses rpc notification and leaf a without warnings", () => {
    const yang = `
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  extension ext { argument name; }
  rpc reset {
    input { leaf in-arg { type string; } }
    output { leaf out-arg { type string; } }
  }
  notification done { leaf msg { type string; } }
  leaf a { type string; }
}
`;
    const mod = parseYangString(yang);
    const joined = warnSpy.mock.calls.map((c: unknown[]) => String(c[0])).join(" ").toLowerCase();
    expect(joined).not.toContain("rpc");
    expect(joined).not.toContain("input");
    expect(joined).not.toContain("output");
    expect(joined).not.toContain("notification");
    const reset = mod.findStatement("reset");
    expect(reset?.keyword).toBe("rpc");
    expect(reset?.name).toBe("reset");
    const done = mod.findStatement("done");
    expect(done?.name).toBe("done");
    const leaf = mod.findStatement("a");
    expect(leaf?.name).toBe("a");
  });

  it("parses action under a container and rejects it at module level", () => {
    const mod = parseYangString(
      'module ex { yang-version 1.1; namespace "urn:ex"; prefix ex; container c { action go { input { leaf x { type empty; } } } } }'
    );
    const action = mod.findStatement("c")?.statements.find((s) => s.keyword === "action");
    expect(action?.name).toBe("go");
    expect(() => parseYangString('module ex { yang-version 1.1; namespace "urn:ex"; prefix ex; action go { } }')).toThrow(
      "unknown statement in module body: 'action'"
    );
  });
});
