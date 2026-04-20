import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import {
  buildEnabledFeaturesMap,
  evaluateIfFeatureExpression,
  parseYangFile,
  parseYangString,
  reachableModuleData,
  stmtIfFeaturesSatisfied,
  YangParser,
  YangValidator
} from "../src";

describe("python parity: test_if_feature", () => {
  it("stores if-feature expression on leaf (including braced forms)", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature f;
  feature baz;

  leaf a {
    if-feature "f";
    type string;
  }

  leaf b {
    if-feature "baz" {
      description "d";
      reference "RFC 7950";
    }
    type string;
  }
}
`);

    expect(module.findStatement("a")?.data.if_features).toEqual(["f"]);
    expect(module.findStatement("b")?.data.if_features).toEqual(["baz"]);
  });

  it("stores multiple if-feature substatements in order", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature p;
  feature q;

  leaf z {
    if-feature "p";
    if-feature "q";
    type uint8;
  }
}
`);

    expect(module.findStatement("z")?.data.if_features).toEqual(["p", "q"]);
  });

  it("stores if-feature on container, leaf-list, and list", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature c;
  feature fl;
  feature lst;

  container root {
    if-feature "c";
    leaf-list tags {
      if-feature "fl";
      type string;
    }
    list items {
      if-feature "lst";
      key "id";
      leaf id { type string; }
    }
  }
}
`);

    const root = module.findStatement("root");
    const tags = root?.findStatement("tags");
    const items = root?.findStatement("items");
    expect(root?.data.if_features).toEqual(["c"]);
    expect(tags?.data.if_features).toEqual(["fl"]);
    expect(items?.data.if_features).toEqual(["lst"]);
  });

  it("stores if-feature on choice and case", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;
  feature cf;
  feature bf;

  container root {
    choice ch {
      if-feature "cf";
      case ca {
        if-feature "bf";
        leaf L { type string; }
      }
    }
  }
}
`);

    const root = module.findStatement("root");
    const choice = root?.findStatement("ch");
    const caseStmt = choice?.findStatement("ca");
    expect(choice?.data.if_features).toEqual(["cf"]);
    expect(caseStmt?.data.if_features).toEqual(["bf"]);
  });

  it("parses prefixed feature reference from imported module", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-if-feature-"));
    try {
      writeFileSync(
        join(dir, "lib.yang"),
        `
module lib {
  yang-version 1.1;
  namespace "urn:test:if-feature-lib";
  prefix l;
  feature remote;
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "main.yang"),
        `
module main {
  yang-version 1.1;
  namespace "urn:test:if-feature-main";
  prefix m;
  import lib { prefix imp; }
  leaf x {
    if-feature "imp:remote";
    type string;
  }
}
`,
        "utf-8"
      );

      const module = parseYangFile(join(dir, "main.yang"));
      const leaf = module.findStatement("x");

      expect((module.data.import_prefixes as Record<string, { name?: string }>).imp?.name).toBe("lib");
      expect(leaf?.data.if_features).toEqual(["imp:remote"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("keeps uses-level if-feature when uses expansion is disabled", () => {
    const parser = new YangParser({ expand_uses: false });
    const module = parser.parseString(`
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;
  feature u;

  grouping g {
    leaf L { type string; }
  }

  container root {
    uses g {
      if-feature "u";
    }
  }
}
`);

    const root = module.findStatement("root");
    const uses = root?.statements.find((stmt) => stmt.keyword === "uses");
    expect(uses?.data.if_features).toEqual(["u"]);
  });

  it("evaluates if-feature boolean expressions and enabled-feature maps", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature a;
  feature b;
  feature c;
}
`);
    const data = module.data as Record<string, unknown>;
    const enAll = buildEnabledFeaturesMap(data, null);
    const enNone = buildEnabledFeaturesMap(data, { m: new Set<string>() });
    const enA = buildEnabledFeaturesMap(data, { m: new Set(["a"]) });
    const enAb = buildEnabledFeaturesMap(data, { m: new Set(["a", "b"]) });

    expect(evaluateIfFeatureExpression("a", data, enAll)).toBe(true);
    expect(evaluateIfFeatureExpression("a", data, enNone)).toBe(false);
    expect(evaluateIfFeatureExpression("not a", data, enAll)).toBe(false);
    expect(evaluateIfFeatureExpression("not a", data, enNone)).toBe(true);
    expect(evaluateIfFeatureExpression("a or b", data, enA)).toBe(true);
    expect(evaluateIfFeatureExpression("a and b", data, enA)).toBe(false);
    expect(evaluateIfFeatureExpression("a and b", data, enAb)).toBe(true);
    expect(evaluateIfFeatureExpression("a or b and c", data, enA)).toBe(true);
    expect(evaluateIfFeatureExpression("(a or b) and c", data, enA)).toBe(false);
  });

  it("accepts parentheses and whitespace in if-feature expressions", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature p;
  feature q;
}
`);
    const data = module.data as Record<string, unknown>;
    const enP = buildEnabledFeaturesMap(data, { m: new Set(["p"]) });
    expect(evaluateIfFeatureExpression("  ( p or q ) ", data, enP)).toBe(true);
  });

  it("resolves own-module prefix in if-feature expressions", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix mx;
  feature f;
}
`);
    const data = module.data as Record<string, unknown>;
    const en = buildEnabledFeaturesMap(data, null);
    expect(evaluateIfFeatureExpression("f", data, en)).toBe(true);
    expect(evaluateIfFeatureExpression("mx:f", data, en)).toBe(true);
  });

  it("treats unknown prefix or missing feature as unsupported", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
}
`);
    const data = module.data as Record<string, unknown>;
    const en = buildEnabledFeaturesMap(data, null);
    expect(evaluateIfFeatureExpression("nope:f", data, en)).toBe(false);
    expect(evaluateIfFeatureExpression("x:missing", data, en)).toBe(false);
  });

  it("treats malformed if-feature expressions as false", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
}
`);
    const data = module.data as Record<string, unknown>;
    const en = buildEnabledFeaturesMap(data, null);
    expect(evaluateIfFeatureExpression("", data, en)).toBe(false);
    expect(evaluateIfFeatureExpression("f f", data, en)).toBe(false);
    expect(evaluateIfFeatureExpression("not", data, en)).toBe(false);
  });

  it("combines multiple if-feature substatements with AND", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature p;
  feature q;
}
`);
    const data = module.data as Record<string, unknown>;
    const enBoth = buildEnabledFeaturesMap(data, { m: new Set(["p", "q"]) });
    const enP = buildEnabledFeaturesMap(data, { m: new Set(["p"]) });
    expect(stmtIfFeaturesSatisfied([], data, enBoth)).toBe(true);
    expect(stmtIfFeaturesSatisfied(["p", "q"], data, enBoth)).toBe(true);
    expect(stmtIfFeaturesSatisfied(["p", "q"], data, enP)).toBe(false);
  });

  it("evaluates prefixed OR across imported modules", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-if-feature-or-"));
    try {
      writeFileSync(
        join(dir, "lib.yang"),
        `
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  feature fea1;
  feature fea2;
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
  import lib { prefix ex; }
  leaf x {
    if-feature "ex:fea1 or ex:fea2";
    type string;
  }
}
`,
        "utf-8"
      );
      const parser = new YangParser({ expand_uses: false });
      const mod = parser.parseFile(join(dir, "main.yang"));
      const leaf = mod.findStatement("x");
      expect(leaf?.data.if_features).toEqual(["ex:fea1 or ex:fea2"]);
      const data = mod.data as Record<string, unknown>;
      const ifs = leaf?.data.if_features as string[] | undefined;
      const expr = ifs?.[0] ?? "";
      const en1 = buildEnabledFeaturesMap(data, { lib: new Set(["fea1"]), main: new Set() });
      expect(evaluateIfFeatureExpression(expr, data, en1)).toBe(true);
      const en2 = buildEnabledFeaturesMap(data, { lib: new Set(["fea2"]), main: new Set() });
      expect(evaluateIfFeatureExpression(expr, data, en2)).toBe(true);
      const enNone = buildEnabledFeaturesMap(data, { lib: new Set(), main: new Set() });
      expect(evaluateIfFeatureExpression(expr, data, enNone)).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("lists reachable modules including transitive imports", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-if-feature-reach-"));
    try {
      writeFileSync(
        join(dir, "a.yang"),
        `
module a {
  yang-version 1.1;
  namespace "urn:a";
  prefix a;
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "b.yang"),
        `
module b {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  import a { prefix pa; }
}
`,
        "utf-8"
      );
      writeFileSync(
        join(dir, "c.yang"),
        `
module c {
  yang-version 1.1;
  namespace "urn:c";
  prefix c;
  import b { prefix pb; }
}
`,
        "utf-8"
      );
      const parser = new YangParser({ expand_uses: false });
      const mod = parser.parseFile(join(dir, "c.yang"));
      const names = new Set(reachableModuleData(mod.data as Record<string, unknown>).map((m) => String(m.name)));
      expect(names).toEqual(new Set(["c", "b", "a"]));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("enables all features for unlisted imported modules when override constrains importer only", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-if-feature-unlisted-"));
    try {
      writeFileSync(
        join(dir, "lib.yang"),
        `
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  feature x;
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
  prefix m;
  import lib { prefix imp; }
}
`,
        "utf-8"
      );
      const parser = new YangParser({ expand_uses: false });
      const mod = parser.parseFile(join(dir, "main.yang"));
      const data = mod.data as Record<string, unknown>;
      const m = buildEnabledFeaturesMap(data, { main: new Set() });
      expect(m.lib?.has("x")).toBe(true);
      expect(m.main?.size).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("prunes features whose own if-feature substatements fail when all features are nominally on", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature a;
  feature b { if-feature "not a"; }
}
`);
    const data = module.data as Record<string, unknown>;
    const m = buildEnabledFeaturesMap(data, null);
    expect(m.m?.has("a")).toBe(true);
    expect(m.m?.has("b")).toBe(false);
  });

  it("rejects instance data for nodes whose if-feature is false", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
  container root {
    leaf a {
      if-feature "f";
      type string;
    }
  }
}
`);
    const v = new YangValidator(module, { enabledFeaturesByModule: { m: new Set() } });
    const bad = v.validate({ root: { a: "hi" } });
    expect(bad.isValid).toBe(false);
    expect(bad.errors.some((e) => e.toLowerCase().includes("if-feature"))).toBe(true);

    const okAbsent = v.validate({ root: {} });
    expect(okAbsent.isValid).toBe(true);

    const vOn = new YangValidator(module, { enabledFeaturesByModule: { m: new Set(["f"]) } });
    expect(vOn.validate({ root: { a: "ok" } }).isValid).toBe(true);
  });

  it("rejects list data when list if-feature is inactive", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature lst;
  container root {
    list items {
      if-feature "lst";
      key "id";
      leaf id { type string; }
    }
  }
}
`);
    const v = new YangValidator(module, { enabledFeaturesByModule: { m: new Set() } });
    const r = v.validate({ root: { items: [{ id: "1" }] } });
    expect(r.isValid).toBe(false);
    expect(r.errors.some((e) => e.toLowerCase().includes("if-feature"))).toBe(true);
  });

  it("merges if-feature from uses into expanded grouping nodes", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature u;
  grouping g {
    leaf L { type string; }
  }
  container root {
    uses g {
      if-feature "u";
    }
  }
}
`);
    const root = module.findStatement("root");
    const leafL = root?.findStatement("L");
    expect(leafL?.data.if_features).toEqual(["u"]);
  });

  it("merges if-feature from refine into expanded target leaf", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature rf;
  grouping g {
    leaf x { type string; }
  }
  container c {
    uses g {
      refine "x" {
        if-feature "rf";
      }
    }
  }
}
`);
    const c = module.findStatement("c");
    const leafX = c?.findStatement("x");
    expect(leafX?.data.if_features).toEqual(["rf"]);
  });

  it("records if-feature substatements on feature definitions in module data", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature core;
  feature layered {
    if-feature "core";
    description "needs core";
  }
}
`);
    const fif = module.data.feature_if_features as Record<string, string[]> | undefined;
    expect(fif).toEqual({ layered: ["core"] });
  });
});
