// #161: extension definitions and invocations survive the native JSON form.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { YangStatement } from "../src/core/model";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangParser, YangValidator } from "../src";
import { YangExportError } from "../src/core/errors";
import { registerExtensionApplyCallback } from "../src/ext/capabilities";
import { applyBuiltinExtensionInvocations } from "../src/ext/rfc8791";

const CASES = resolve(dirname(fileURLToPath(import.meta.url)), "../../tests/cases/modules");

function isInvocation(stmt: YangStatement): boolean {
  return typeof stmt.prefix === "string" && typeof stmt.resolved_extension_name === "string" && stmt.resolved_extension_name.length > 0;
}

function byOwner(statements: YangStatement[], path = ""): Record<string, Array<[string, string | undefined]>> {
  const out: Record<string, Array<[string, string | undefined]>> = {};
  const here: Array<[string, string | undefined]> = [];
  for (const stmt of statements) {
    if (isInvocation(stmt)) {
      here.push([`${stmt.prefix}:${stmt.resolved_extension_name}`, stmt.argument]);
    }
  }
  if (here.length > 0) {
    out[path] = here;
  }
  for (const stmt of statements) {
    if (!isInvocation(stmt) && stmt.keyword !== "typedef") {
      Object.assign(out, byOwner(stmt.statements ?? [], `${path}/${stmt.name ?? ""}`));
    }
  }
  return out;
}

describe("native JSON form of extensions", () => {
  it("reloads the same invocations and reproduces the JSON", () => {
    const dir = resolve(CASES, "json-form-extensions-161");
    const yang = new YangParser({ expandUses: false, includePath: [dir] }).parseFile(resolve(dir, "m.yang"));
    const form = generateJsonSchema(yang);
    expect(form).toEqual(JSON.parse(readFileSync(resolve(dir, "expected.yang.json"), "utf8")));
    const loaded = parseJsonSchema(form);
    expect(byOwner(loaded.statements)).toEqual(byOwner(yang.statements));
    const yangKind = (yang.identities.kind as { statements?: YangStatement[] } | undefined)?.statements ?? [];
    const loadedKind = (loaded.identities.kind as { statements?: YangStatement[] } | undefined)?.statements ?? [];
    expect(byOwner(loadedKind, "$identity/kind")).toEqual(byOwner(yangKind, "$identity/kind"));
    const yangTypedef = ((yang.typedefs.name as { statements?: YangStatement[] }).statements) ?? [];
    const loadedTypedef = ((loaded.typedefs.name as { statements?: YangStatement[] }).statements) ?? [];
    expect(byOwner(loadedTypedef, "$typedef/name")).toEqual(byOwner(yangTypedef, "$typedef/name"));
    expect(loaded.extensions).toMatchObject({
      "http-header": { argument_name: "name", description: "Mirror into an HTTP header.", reference: "RFC 7950" },
      note: { argument_name: "text", argument_yin_element: true, description: "A note." }
    });
    expect(loaded.import_prefixes.e?.extensions).toMatchObject({
      tag: { argument_name: "value", description: "Imported tag.", reference: "ext" }
    });
    expect(JSON.parse(JSON.stringify(generateJsonSchema(loaded)))).toEqual(form);
  });

  it("round-trips RFC 8791 sx:structure (#164 removed the #162 refusal)", () => {
    const dir = resolve(CASES, "json-form-rfc8791-extension-161");
    const yang = new YangParser({ expandUses: false, includePath: [dir] }).parseFile(resolve(dir, "m.yang"));
    const form = JSON.parse(JSON.stringify(generateJsonSchema(yang)));
    expect(form).toEqual(JSON.parse(readFileSync(resolve(dir, "expected.yang.json"), "utf8")));
    const loaded = parseJsonSchema(form);
    expect(JSON.parse(JSON.stringify(generateJsonSchema(loaded)))).toEqual(form);
    const index = loaded.extension_runtime?.["ietf-yang-structure-ext:structure-index"] as Record<string, unknown>;
    expect(Object.keys(index ?? {})).toEqual(["msg"]);
  });

  it("applies a cross-module augment-structure once on reload (#164)", () => {
    const dir = resolve(CASES, "json-form-augment-structure-cross-164");
    const yang = new YangParser({ expandUses: false, includePath: [dir] }).parseFile(resolve(dir, "m.yang"));
    const form = JSON.parse(JSON.stringify(generateJsonSchema(yang)));
    const loaded = parseJsonSchema(form);
    expect(JSON.parse(JSON.stringify(generateJsonSchema(loaded)))).toEqual(form);
    const extras = () => {
      const stub = loaded.import_prefixes.b;
      const index = stub?.extension_runtime?.["ietf-yang-structure-ext:structure-index"] as
        | Record<string, { statements?: Array<{ name?: string; statements?: Array<{ name?: string }> }> }>
        | undefined;
      const box = index?.msg?.statements?.find((stmt) => stmt.name === "box");
      return box?.statements?.filter((stmt) => stmt.name === "extra") ?? [];
    };
    expect(extras()).toHaveLength(1);
    applyBuiltinExtensionInvocations(loaded);
    expect(extras()).toHaveLength(1);
  });

  it("enforces if-feature merged by augment-structure after reload (#164)", () => {
    const dir = resolve(CASES, "json-form-augment-structure-164");
    const yang = new YangParser({ includePath: [dir] }).parseFile(resolve(dir, "m.yang"));
    const loaded = parseJsonSchema(
      generateJsonSchema(new YangParser({ expandUses: false, includePath: [dir] }).parseFile(resolve(dir, "m.yang")))
    );
    const data = { "m:msg": { enabled: "on", "extra-leaf": "z", box: { note: "hi" } } };
    for (const module of [yang, loaded]) {
      const result = new YangValidator(module, { enabledFeaturesByModule: { m: new Set() } }).validateDetailed(data);
      expect(result.errors.map((error) => `${error.code} ${error.path}`)).toEqual(["if-feature /m:msg/extra-leaf"]);
    }
  });

  it("still rejects an extension that has an apply callback and no JSON form (#164)", () => {
    registerExtensionApplyCallback("marked", "mark", () => undefined);
    const yang = parseYangString(`module marked {
  yang-version 1.1;
  namespace "urn:marked";
  prefix m;
  extension mark { argument value; }
  m:mark "x";
}
`);
    expect(() => generateJsonSchema(yang)).toThrow(YangExportError);
    expect(() => generateJsonSchema(yang)).toThrow(/marked:mark/);
  });
});
