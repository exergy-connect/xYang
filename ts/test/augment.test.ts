import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { parseYangString, YangModule, YangParser, YangSyntaxError, YangValidator } from "../src";

const tempDirs: string[] = [];

afterEach(() => {
  while (tempDirs.length > 0) {
    const dir = tempDirs.pop();
    if (dir) {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

function tempYangDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "xyang-augment-"));
  tempDirs.push(dir);
  return dir;
}

describe("python parity: test_augment (parse shape, expandUses=false)", () => {
  it("parses augment path and body statements without merging", () => {
    const module = new YangParser({ expand_uses: false }).parseString(`
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
    expect(module.findStatement("a")?.findStatement("y")).toBeUndefined();
  });

  it("parses concatenated string form for augment path", () => {
    const module = new YangParser({ expand_uses: false }).parseString(`
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
    const module = new YangParser({ expand_uses: false }).parseString(`
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

describe("python parity: test_augment (schema merge, expandUses=true)", () => {
  it("merges same-module augment into container and validates", () => {
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

    expect(module.statements.some((s) => s.keyword === "augment")).toBe(false);
    const a = module.findStatement("a");
    expect(a?.findStatement("x")?.keyword).toBe("leaf");
    expect(a?.findStatement("y")?.keyword).toBe("leaf");
    const { isValid, errors } = new YangValidator(module).validate({ a: { x: "hi", y: 42 } });
    expect(isValid, errors.join("; ")).toBe(true);
  });

  it("merges cross-file import augment into imported container", () => {
    const dir = tempYangDir();
    writeFileSync(
      join(dir, "lib.yang"),
      `
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  container root {
    leaf existing { type string; }
  }
}
`,
      "utf-8"
    );
    writeFileSync(
      join(dir, "main.yang"),
      `
module main {
  yang-version 1.1;
  namespace "urn:main";
  prefix mn;
  import lib { prefix imp; }
  augment "/imp:root" {
    leaf extra { type string; }
  }
}
`,
      "utf-8"
    );

    const parser = new YangParser({ expand_uses: true, include_path: [dir] });
    const mod = parser.parseFile(join(dir, "main.yang"));
    expect(mod.statements.some((s) => s.keyword === "augment")).toBe(false);

    const libData = (mod.data.import_prefixes as Record<string, Record<string, unknown>>).imp;
    expect(libData).toBeDefined();
    const libMod = new YangModule(libData, { kind: "file", value: join(dir, "lib.yang") });

    const root = libMod.findStatement("root");
    expect(root?.findStatement("existing")?.keyword).toBe("leaf");
    expect(root?.findStatement("extra")?.keyword).toBe("leaf");

    const { isValid, errors } = new YangValidator(libMod).validate({
      root: { existing: "a", extra: "b" }
    });
    expect(isValid, errors.join("; ")).toBe(true);
  });

  it("prepends augment if-feature onto merged leaves", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature f;
  container a { leaf x { type string; } }
  augment "/m:a" {
    if-feature "f";
    leaf z { type string; }
  }
}
`);

    const z = module.findStatement("a")?.findStatement("z");
    expect(z?.data.if_features).toEqual(["f"]);
    const { isValid, errors } = new YangValidator(module, {
      enabledFeaturesByModule: { m: new Set() }
    }).validate({ a: { x: "ok", z: "bad" } });
    expect(isValid).toBe(false);
    expect(errors.some((e) => e.toLowerCase().includes("if-feature"))).toBe(true);
  });

  it("merges case into choice", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container root {
    choice target {
      case a { leaf x { type string; } }
    }
  }
  augment "/m:root/m:target" {
    case b {
      leaf y { type int32; }
    }
  }
}
`);

    const ch = module.findStatement("root")?.findStatement("target");
    expect(ch?.keyword).toBe("choice");
    const caseNames = (ch?.statements ?? [])
      .filter((s) => s.keyword === "case")
      .map((s) => s.name);
    expect(new Set(caseNames)).toEqual(new Set(["a", "b"]));
    const caseB = ch?.statements.find((s) => s.keyword === "case" && s.name === "b");
    expect(caseB?.findStatement("y")?.keyword).toBe("leaf");
  });

  it("merges augment into list (netlab-style /topology/nodes)", () => {
    const module = parseYangString(`
module nt {
  yang-version 1.1;
  namespace "urn:nt";
  prefix nt;
  container topology {
    list nodes {
      key "name";
      leaf name { type string; }
    }
  }
  augment "/nt:topology/nt:nodes" {
    container vxlan {
      leaf vni { type uint32; }
    }
  }
}
`);

    expect(module.statements.some((s) => s.keyword === "augment")).toBe(false);
    const nodes = module.findStatement("topology")?.findStatement("nodes");
    expect(nodes?.keyword).toBe("list");
    expect(nodes?.findStatement("vxlan")?.keyword).toBe("container");
    expect(nodes?.findStatement("vxlan")?.findStatement("vni")?.keyword).toBe("leaf");

    const { isValid, errors } = new YangValidator(module).validate({
      topology: {
        nodes: [{ name: "r1", vxlan: { vni: 100 } }]
      }
    });
    expect(isValid, errors.join("; ")).toBe(true);
  });

  it("errors when augment path is not absolute", () => {
    expect(() =>
      parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container a { }
  augment "m:a" { leaf y { type string; } }
}
`)
    ).toThrow(YangSyntaxError);
    expect(() =>
      parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container a { }
  augment "m:a" { leaf y { type string; } }
}
`)
    ).toThrow(/absolute/);
  });

  it("errors on unknown prefix in augment path", () => {
    expect(() =>
      parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  augment "/xx:noop" { leaf y { type string; } }
}
`)
    ).toThrow(/unknown prefix/);
  });
});
