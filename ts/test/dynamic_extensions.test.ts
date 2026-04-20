import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseYangFile, parseYangString, YangValidator } from "../src";

describe("python parity: test_dynamic_extensions", () => {
  it("extension definition and prefixed invocation are parsed with resolution metadata", () => {
    const mod = parseYangString(`
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;

  extension custom {
    argument name;
    description "custom extension";
  }

  ex:custom "payload" {
    leaf foo { type string; }
  }
}
`);

    const ext = mod.statements.find((stmt) => stmt.keyword === "extension" && stmt.name === "custom");
    expect(ext).toBeDefined();
    expect(ext?.data.argument_name).toBe("name");

    const invocations = mod.statements.filter((stmt) => stmt.data.prefix === "ex");
    expect(invocations).toHaveLength(1);
    const invocation = invocations[0];
    expect(invocation.keyword).toBe("ex:custom");
    expect(invocation.argument).toBe("payload");
    expect(invocation.data.resolved_module_name).toBe("ex");
    expect(invocation.data.resolved_extension_name).toBe("custom");
    expect(invocation.findStatement("foo")?.keyword).toBe("leaf");
  });

  it("unknown extension name in invocation is a parse error", () => {
    expect(() =>
      parseYangString(`
module ex-bad {
  yang-version 1.1;
  namespace "urn:ex:bad";
  prefix ex;

  ex:missing "x";
}
`)
    ).toThrow(/Unknown extension/);
  });

  it("unknown extension prefix in invocation is a parse error", () => {
    expect(() =>
      parseYangString(`
module ex-bad-prefix {
  yang-version 1.1;
  namespace "urn:ex:bad:prefix";
  prefix ex;

  zz:custom "x";
}
`)
    ).toThrow(/Unknown extension prefix/);
  });

  it("rfc8791 merges augment-structure into structure and removes augment invocation", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-rfc8791-"));
    try {
      writeFileSync(
        join(dir, "ietf-yang-structure-ext.yang"),
        `
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;
  extension structure { argument name; }
  extension augment-structure { argument target; }
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "demo.yang"),
        `
module demo {
  yang-version 1.1;
  namespace "urn:demo";
  prefix d;
  import ietf-yang-structure-ext { prefix sx; }

  sx:structure msg {
    leaf a { type string; }
  }

  sx:augment-structure "/d:msg" {
    leaf b { type string; }
  }
}
`,
        "utf-8"
      );

      const mod = parseYangFile(join(dir, "demo.yang"));
      const structure = mod.statements.find((stmt) => stmt.keyword === "sx:structure");
      expect(structure).toBeDefined();
      expect(structure?.name).toBe("msg");
      expect(structure?.findStatement("a")?.keyword).toBe("leaf");
      expect(structure?.findStatement("b")?.keyword).toBe("leaf");
      expect(mod.statements.some((stmt) => stmt.keyword === "sx:augment-structure")).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("rfc8791 resolver works with non-default extension prefix", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-rfc8791-prefix-"));
    try {
      writeFileSync(
        join(dir, "ietf-yang-structure-ext.yang"),
        `
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;
  extension structure { argument name; }
  extension augment-structure { argument target; }
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "demo-prefix.yang"),
        `
module demo-prefix {
  yang-version 1.1;
  namespace "urn:demo:prefix";
  prefix d;
  import ietf-yang-structure-ext { prefix extx; }

  extx:structure msg {
    leaf a { type string; }
  }

  extx:augment-structure "/d:msg" {
    leaf b { type string; }
  }
}
`,
        "utf-8"
      );

      const mod = parseYangFile(join(dir, "demo-prefix.yang"));
      const structure = mod.statements.find((stmt) => stmt.keyword === "extx:structure");
      expect(structure?.findStatement("a")?.keyword).toBe("leaf");
      expect(structure?.findStatement("b")?.keyword).toBe("leaf");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("rfc8791 augment-structure merges when and if-feature semantics onto roots", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-rfc8791-sem-"));
    try {
      writeFileSync(
        join(dir, "ietf-yang-structure-ext.yang"),
        `
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;
  extension structure { argument name; }
  extension augment-structure { argument target; }
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "demo-sem.yang"),
        `
module demo-sem {
  yang-version 1.1;
  namespace "urn:demo:sem";
  prefix d;

  import ietf-yang-structure-ext { prefix sx; }
  feature f;

  sx:structure msg {
    leaf enabled { type string; }
    leaf mode { type string; }
  }

  sx:augment-structure "/d:msg" {
    if-feature "f";
    when "enabled = 'true'";
    leaf b {
      type string;
      when "mode = 'x'";
    }
  }
}
`,
        "utf-8"
      );

      const mod = parseYangFile(join(dir, "demo-sem.yang"));
      const structure = mod.statements.find((stmt) => stmt.keyword === "sx:structure");
      const leafB = structure?.findStatement("b");
      expect(leafB).toBeDefined();
      expect(leafB?.data.if_features).toEqual(["f"]);
      const whenShape = leafB?.data.when as Record<string, unknown> | undefined;
      expect(whenShape?.expression).toBe("(enabled = 'true') and (mode = 'x')");
      expect(whenShape?.evaluate_with_parent_context).toBe(true);

      const validator = new YangValidator(mod);
      const ok = validator.validate({ msg: { enabled: "true", mode: "x", b: "ok" } });
      expect(ok.isValid).toBe(true);

      const bad = validator.validate({ msg: { enabled: "true", mode: "y", b: "bad" } });
      expect(bad.isValid).toBe(false);
      expect(bad.errors.some((error) => error.toLowerCase().includes("when"))).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
