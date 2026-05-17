import { describe, expect, it, vi } from "vitest";
import { resolve } from "node:path";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { YangSyntaxError } from "../src/core/errors";
import type { XPathBinaryNode, XPathPathNode } from "../src/xpath/ast";
import { parseXPathPath } from "../src/xpath/parser";
import { parseYangFile, parseYangString } from "../src/parser";
import { mkdirSync } from "node:fs";

describe("parser parity with Python", () => {
  it("typedef default is stored on AST", () => {
    const mod = parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  typedef t { type string; default "x"; }
}`);
    const td = mod.typedefs["t"] as { default?: string };
    expect(td?.default).toBe("x");
  });

  it("pattern string concatenation merges quoted parts", () => {
    const mod = parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  typedef t {
    type string {
      pattern "a" + "b" + "c";
    }
  }
}`);
    const td = mod.typedefs["t"] as { type?: { patterns?: Array<{ pattern: string }> } };
    const patterns = td?.type?.patterns ?? [];
    expect(patterns[0]?.pattern).toBe("abc");
  });

  it("choice inline leaf creates implicit case", () => {
    const mod = parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container c {
    choice ch {
      leaf x { type string; }
    }
  }
}`);
    const c = mod.findStatement("c");
    expect(c).toBeDefined();
  });

  it("config false parses with warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const mod = parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container state-tree {
    config false;
    leaf x { type string; }
  }
}`);
    expect(mod.findStatement("state-tree")).toBeDefined();
    expect(warn.mock.calls.some((c) => String(c[0]).includes("config"))).toBe(true);
    warn.mockRestore();
  });

  it("YangSyntaxError toString includes line and message", () => {
    try {
      parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  typedef t {
    type string;
    bogus-stmt "x";
  }
}`);
      expect.fail("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(YangSyntaxError);
      const err = e as YangSyntaxError;
      expect(err.line_num).toBeDefined();
      const text = String(err);
      expect(text).toContain(`${err.line_num}:`);
      expect(text).toContain("bogus-stmt");
    }
  });

  it("parseXPathPath merges multiple predicates with and", () => {
    const path =
      "/alarms/alarm-list/alarm[resource=current()/../resource]" +
      "[alarm-type-id=current()/../alarm-type-id]/alarm-type-qualifier";
    const ast = parseXPathPath(path);
    expect(ast.kind).toBe("path");
    const p = ast as XPathPathNode;
    const alarm = p.segments.find((s) => s.step === "alarm");
    expect(alarm?.predicate).toBeDefined();
    expect(alarm?.predicate?.kind).toBe("binary");
    const bin = alarm?.predicate as XPathBinaryNode;
    expect(bin.operator).toBe("and");
  });

  it("include-path resolves import from extra directory", () => {
    const base = mkdtempSync(resolve(tmpdir(), "xyang-ts-inc-"));
    const inc = resolve(base, "include");
    mkdirSync(inc);
    writeFileSync(
      resolve(inc, "dep.yang"),
      `module dep {
  yang-version 1.1;
  namespace "urn:example:dep";
  prefix d;
}
`
    );
    const main = resolve(base, "main.yang");
    writeFileSync(
      main,
      `module main {
  yang-version 1.1;
  namespace "urn:example:main";
  prefix m;
  import dep { prefix d; }
}
`
    );
    const mod = parseYangFile(main, { includePath: [inc] });
    expect(mod.name).toBe("main");
  });

  it("leaf reference substatement is stored", () => {
    const mod = parseYangString(`module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container root {
    leaf x {
      type string;
      reference "RFC 7950";
    }
  }
}`);
    const root = mod.findStatement("root");
    const leaf = root?.findStatement("x");
    expect(leaf).toBeDefined();
    expect((leaf?.data as { reference?: string }).reference).toBe("RFC 7950");
  });
});
