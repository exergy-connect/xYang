// #161: extension definitions and invocations survive the native JSON form.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { YangExportError } from "../src/core/errors";
import type { YangStatement } from "../src/core/model";
import { generateJsonSchema, parseJsonSchema, YangParser } from "../src";

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

  it("refuses to record RFC 8791 sx:structure", () => {
    const dir = resolve(CASES, "json-form-rfc8791-extension-161");
    const yang = new YangParser({ expandUses: false, includePath: [dir] }).parseFile(resolve(dir, "m.yang"));
    expect(() => generateJsonSchema(yang)).toThrow(YangExportError);
    expect(() => generateJsonSchema(yang)).toThrow(/RFC 8791 sx:structure/);
  });
});
