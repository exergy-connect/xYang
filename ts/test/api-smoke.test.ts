import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString, YangValidator } from "../src";
import { resolveQualifiedTopLevel } from "../src/encoding";
import { TypeConstraint, TypeSystem } from "../src/types";

const repoRoot = resolve(__dirname, "..", "..");

describe("typescript bridge api", () => {
  it("parses a basic module from string", () => {
    const module = parseYangString(`
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix t;
  container root { leaf x { type string; } }
}
`);
    expect(module.name).toBe("test");
    expect(module.findStatement("root")?.name).toBe("root");
  });

  it("validates example data", () => {
    const module = parseYangFile(resolve(repoRoot, "examples/meta-model.yang"));
    const validator = new YangValidator(module);
    const result = validator.validate({ "data-model": { name: "demo", entities: [] } });
    expect(result.isValid).toBeTypeOf("boolean");
  });

  it("resolves qualified top level via encoding helper", () => {
    const module = parseYangString(`
module mod-a { yang-version 1.1; namespace "urn:a"; prefix a; container root { leaf x { type string; } } }
`);
    const result = resolveQualifiedTopLevel("mod-a:root", { [module.name ?? "mod-a"]: module });
    expect(result.statementName).toBe("root");
  });

  it("validates primitive type through TypeSystem", () => {
    const [ok] = new TypeSystem().validate("abc", "string", new TypeConstraint({ length: "1..5" }));
    expect(ok).toBe(true);
  });
});
