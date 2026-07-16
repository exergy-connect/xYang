import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { YangParser, YangValidator } from "../src";

describe("imported typedef resolution", () => {
  it("validates prefix:typedef leaves including union+boolean", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-imported-typedef-"));
    writeFileSync(
      join(dir, "types-mod.yang"),
      `module types-mod {
  yang-version 1.1;
  namespace "urn:ex:types";
  prefix t;
  typedef ipv4-prefix {
    type union {
      type string {
        pattern '1\\.2\\.3\\.0/24|true|false';
      }
      type boolean;
    }
  }
}
`
    );
    writeFileSync(
      join(dir, "host.yang"),
      `module host {
  yang-version 1.1;
  namespace "urn:ex:host";
  prefix h;
  import types-mod { prefix t; }
  container root {
    leaf addr {
      type t:ipv4-prefix;
    }
  }
}
`
    );

    const parser = new YangParser({ include_path: [dir], expand_uses: true });
    const mod = parser.parseFile(join(dir, "host.yang"));
    const v = new YangValidator(mod);

    expect(v.validate({ root: { addr: "1.2.3.0/24" } }).isValid).toBe(true);
    expect(v.validate({ root: { addr: true } }).isValid).toBe(true);
    expect(v.validate({ root: { addr: false } }).isValid).toBe(true);
    expect(v.validate({ root: { addr: "true" } }).isValid).toBe(true);
    expect(v.validate({ root: { addr: 42 } }).isValid).toBe(false);
    const bad = v.validate({ root: { addr: 42 } });
    expect(bad.errors.some((e) => e.includes("Unsupported type"))).toBe(false);
  });
});
