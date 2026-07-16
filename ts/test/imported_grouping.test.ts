import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { YangParser, YangValidator } from "../src";

describe("imported grouping uses expansion", () => {
  it("parses uses prefix:grouping into structured prefix+name (no joined qname)", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-grouping-parse-"));
    writeFileSync(
      join(dir, "types.yang"),
      `module types {
  yang-version 1.1;
  namespace "urn:ex:types";
  prefix t;
  grouping af-flags {
    container af {
      leaf ipv4 { type boolean; }
    }
  }
}
`
    );
    writeFileSync(
      join(dir, "topo.yang"),
      `module topo {
  yang-version 1.1;
  namespace "urn:ex:topo";
  prefix nt;
  import types { prefix ntype; }
  container topology {
    uses ntype:af-flags;
  }
}
`
    );

    const mod = new YangParser({ include_path: [dir], expand_uses: false }).parseFile(
      join(dir, "topo.yang")
    );
    const topology = (mod.data.statements as { name?: string; statements?: unknown[] }[]).find(
      (s) => s.name === "topology"
    );
    const uses = (topology?.statements as { keyword?: string; grouping_name?: string; grouping_prefix?: string; argument?: string }[] | undefined)?.find(
      (s) => s.keyword === "uses"
    );
    expect(uses?.grouping_prefix).toBe("ntype");
    expect(uses?.grouping_name).toBe("af-flags");
    expect(uses?.argument).toBe("ntype:af-flags");
    expect(uses?.grouping_name?.includes(":")).toBe(false);
  });

  it("expands uses prefix:grouping from an imported module", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-grouping-"));
    writeFileSync(
      join(dir, "types.yang"),
      `module types {
  yang-version 1.1;
  namespace "urn:ex:types";
  prefix t;
  grouping af-flags {
    container af {
      leaf ipv4 { type boolean; }
      leaf ipv6 { type boolean; }
    }
  }
}
`
    );
    writeFileSync(
      join(dir, "topo.yang"),
      `module topo {
  yang-version 1.1;
  namespace "urn:ex:topo";
  prefix nt;
  import types { prefix ntype; }
  container topology {
    uses ntype:af-flags;
  }
}
`
    );

    const parser = new YangParser({ include_path: [dir], expand_uses: true });
    const mod = parser.parseFile(join(dir, "topo.yang"));
    const topology = (mod.data.statements as { name?: string; statements?: unknown[] }[]).find(
      (s) => s.name === "topology"
    );
    expect(topology?.statements?.some((s) => (s as { name?: string }).name === "af")).toBe(true);

    const v = new YangValidator(mod);
    expect(v.validate({ topology: { af: { ipv4: true, ipv6: false } } }).isValid).toBe(true);
    expect(v.validate({ topology: { af: { ipv4: "nope" } } }).isValid).toBe(false);
  });

  it("expands imported grouping when the consumer has no local groupings", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-grouping-only-"));
    writeFileSync(
      join(dir, "lib.yang"),
      `module lib {
  yang-version 1.1;
  namespace "urn:ex:lib";
  prefix l;
  grouping g {
    leaf x { type string; mandatory true; }
  }
}
`
    );
    writeFileSync(
      join(dir, "app.yang"),
      `module app {
  yang-version 1.1;
  namespace "urn:ex:app";
  prefix a;
  import lib { prefix l; }
  container root { uses l:g; }
}
`
    );

    const mod = new YangParser({ include_path: [dir], expand_uses: true }).parseFile(join(dir, "app.yang"));
    // Imported module must retain groupings for cross-module uses.
    const lib = (mod.data.import_prefixes as Record<string, { groupings?: Record<string, unknown> }>).l;
    expect(lib?.groupings?.g).toBeDefined();

    const v = new YangValidator(mod);
    expect(v.validate({ root: { x: "ok" } }).isValid).toBe(true);
    expect(v.validate({ root: {} }).isValid).toBe(false);
  });

  it("resolves nested local uses inside an imported grouping", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-grouping-nested-"));
    writeFileSync(
      join(dir, "lib.yang"),
      `module lib {
  yang-version 1.1;
  namespace "urn:ex:lib";
  prefix l;
  grouping inner {
    leaf y { type int32; }
  }
  grouping outer {
    leaf x { type string; }
    uses inner;
  }
}
`
    );
    writeFileSync(
      join(dir, "app.yang"),
      `module app {
  yang-version 1.1;
  namespace "urn:ex:app";
  prefix a;
  import lib { prefix l; }
  container root { uses l:outer; }
}
`
    );

    const mod = new YangParser({ include_path: [dir], expand_uses: true }).parseFile(join(dir, "app.yang"));
    const v = new YangValidator(mod);
    expect(v.validate({ root: { x: "a", y: 1 } }).isValid).toBe(true);
  });

  it("registers typedefs from an imported grouping onto the consumer", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-grouping-typedef-"));
    writeFileSync(
      join(dir, "provider.yang"),
      `module provider {
  yang-version 1.1;
  namespace "urn:example:provider";
  prefix p;
  grouping g {
    typedef code {
      type enumeration {
        enum a;
        enum b;
      }
    }
    leaf value { type code; }
  }
}
`
    );
    writeFileSync(
      join(dir, "consumer.yang"),
      `module consumer {
  yang-version 1.1;
  namespace "urn:example:consumer";
  prefix c;
  import provider { prefix p; }
  container data { uses p:g; }
}
`
    );

    const mod = new YangParser({ include_path: [dir], expand_uses: true }).parseFile(
      join(dir, "consumer.yang")
    );
    expect((mod.data.typedefs as Record<string, unknown>).code).toBeDefined();
    const v = new YangValidator(mod);
    expect(v.validate({ data: { value: "a" } }).isValid).toBe(true);
    expect(v.validate({ data: { value: "nope" } }).isValid).toBe(false);
  });
});
