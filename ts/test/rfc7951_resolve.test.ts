import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";
import { resolveQualifiedTopLevel } from "../src/encoding";

describe("python parity: test_rfc7951_resolve", () => {
  it("resolveQualifiedTopLevel finds statement in qualified module", () => {
    const a = parseYangString(`
module mod-a {
  yang-version 1.1;
  namespace "urn:a";
  prefix a;
  container root { leaf x { type string; } }
}
`);
    const b = parseYangString(`
module mod-b {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  leaf y { type int8; }
}
`);

    const modules = {
      [a.name ?? "mod-a"]: a,
      [b.name ?? "mod-b"]: b
    };

    const first = resolveQualifiedTopLevel("mod-a:root", modules);
    expect(first.moduleName).toBe("mod-a");
    expect(first.statementName).toBe("root");

    const second = resolveQualifiedTopLevel("mod-b:y", modules);
    expect(second.moduleName).toBe("mod-b");
    expect(second.statementName).toBe("y");
  });

  it("returns nulls for unknown module", () => {
    const lone = parseYangString(`
module lone {
  yang-version 1.1;
  namespace "urn:l";
  prefix l;
  leaf z { type string; }
}
`);

    const result = resolveQualifiedTopLevel("unknown:z", {
      [lone.name ?? "lone"]: lone
    });

    expect(result).toEqual({ statementName: null, moduleName: null });
  });

  it("returns nulls for unqualified key", () => {
    const lone = parseYangString(
      'module lone { yang-version 1.1; namespace "urn:l"; prefix l; leaf z { type string; } }'
    );

    const result = resolveQualifiedTopLevel("z", {
      [lone.name ?? "lone"]: lone
    });

    expect(result).toEqual({ statementName: null, moduleName: null });
  });
});
