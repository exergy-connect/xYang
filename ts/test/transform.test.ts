import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { iterInstance, projectInstance } from "../src/encoding";
import {
  ExpressionError,
  generateJsonSchema,
  parseJsonSchema,
  parseYangFile,
  YangValidator
} from "../src";

const CASE = join(import.meta.dirname, "../../tests/cases/normalization/conditional/m.yang");

function writeModel(text: string): string {
  const dir = mkdtempSync(join(tmpdir(), "xyang-transform-"));
  const path = join(dir, "m.yang");
  writeFileSync(path, text);
  return path;
}

describe("instance normalization", () => {
  const module = parseYangFile(CASE);

  it("does not mutate input", () => {
    const data = { nodes: [{ name: "a" }, { name: "b" }], links: ["a-b"] };
    const original = structuredClone(data);
    expect(new YangValidator(module).validateDetailed(data).valid).toBe(true);
    expect(data).toEqual(original);
  });

  it("survives native JSON round trip", () => {
    const restored = parseJsonSchema(generateJsonSchema(module));
    const data = { nodes: [{ name: "a" }, { name: "b" }], links: ["a-b"] };
    expect(new YangValidator(restored).validateDetailed(data).valid).toBe(true);
  });

  it("applies transform in the instance iterator", () => {
    const data = { nodes: [{ name: "a" }, { name: "b" }], links: ["a-b"] };
    const { data: projected } = projectInstance([...iterInstance(data, module)], module.name ?? "");
    expect(projected.links).toEqual([{ left: "a", right: "b" }]);
    expect(data.links).toEqual(["a-b"]);
  });

  it("ignores an unrelated extension with the same name", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      extension normalize;
      list links { key "left"; m:normalize; leaf left { type string; } }
    }`);
    const result = new YangValidator(parseYangFile(path)).validateDetailed({ links: ["a-b"] });
    expect(result.errors.map((e) => [e.path, e.code])).toEqual([["/links/0", "type"]]);
  });

  it("cannot discard the document at the root", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      xt:normalize { xt:if 'true'; xt:apply '"not an object"'; }
      leaf label { type string; }
    }`);
    const result = new YangValidator(parseYangFile(path)).validateDetailed({ label: "a" });
    expect(result.errors.map((e) => [e.path, e.code])).toEqual([["", "normalize"]]);
  });

  it("fails unsupported expressions even when the node is absent", () => {
    const restored = parseJsonSchema(generateJsonSchema(module));
    const links = restored.findStatement("links")!;
    const rule = links.statements.find(
      (s) => s.resolved_module_name === "xyang-transform" && s.resolved_extension_name === "normalize"
    )!;
    rule.statements[1].argument = "unsupported(.)";
    expect(() => new YangValidator(restored).validateDetailed({})).toThrow(/unsupported function/);
  });

  it("normalizes rpc input", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      rpc run { input {
        list links { key "left right";
          xt:normalize {
            xt:if 'type == "string" and contains("-")';
            xt:apply 'split("-") | {left: .[0], right: .[1]}';
          }
          leaf left { type string; } leaf right { type string; }
        }
      } }
    }`);
    const result = new YangValidator(parseYangFile(path)).validateDetailed(
      { "m:input": { links: ["a-b"] } },
      { rpc: "run" }
    );
    expect(result.valid).toBe(true);
  });

  it("applies an apply-only rule unconditionally", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      list links { key "left right";
        xt:normalize {
          xt:apply 'split("-") | {left: .[0], right: .[1]}';
        }
        leaf left { type string; } leaf right { type string; }
      }
    }`);
    const result = new YangValidator(parseYangFile(path)).validateDetailed({ links: ["a-b"] });
    expect(result.valid).toBe(true);
  });

  it.each([
    ["", /xt:apply/],
    ["xt:if 'true';", /xt:apply/],
    ["xt:apply 'true'; xt:if 'true';", /xt:apply/],
    ["xt:if 'true'; xt:if 'true'; xt:apply 'true';", /xt:apply/]
  ])("rejects invalid normalize bodies: %s", (body, match) => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      leaf label { type string; xt:normalize { ${body} } }
    }`);
    expect(() => new YangValidator(parseYangFile(path)).validateDetailed({})).toThrow(match);
  });

  it("keeps dotted-key expansion after native JSON reload without mutating input", () => {
    const schema = join(import.meta.dirname, "../../tests/cases/normalization/dotted/m.yang");
    const restored = parseJsonSchema(generateJsonSchema(parseYangFile(schema)));
    const data = { nodes: { a: { "bgp.as": 65000 } } };
    const original = structuredClone(data);
    expect(new YangValidator(restored).validateDetailed(data, { nativeJson: true }).valid).toBe(true);
    expect(data).toEqual(original);
  });

  it.each(["TRUE", "yes", "1"])("rejects invalid expand-dotted-keys %s", (value) => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      xt:expand-dotted-keys ${value};
    }`);
    expect(() => new YangValidator(parseYangFile(path)).validateDetailed({})).toThrow(/requires true or false/);
  });

  it("allows expand-dotted-keys only at module level", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      container c { xt:expand-dotted-keys true; }
    }`);
    expect(() => new YangValidator(parseYangFile(path)).validateDetailed({})).toThrow(/only at module level/);
  });

  it("leaves keys unchanged when expand-dotted-keys is false", () => {
    const path = writeModel(`module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      xt:expand-dotted-keys false;
      container c { leaf v { type string; } }
    }`);
    const result = new YangValidator(parseYangFile(path)).validateDetailed({ "c.v": "x" });
    expect(result.errors.map((e) => [e.path, e.code])).toEqual([["/c.v", "unknown-field"]]);
  });

  it("exports ExpressionError", () => {
    expect(new ExpressionError("x")).toBeInstanceOf(Error);
  });
});
