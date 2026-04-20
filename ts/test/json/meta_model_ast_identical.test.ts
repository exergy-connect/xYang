import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseJsonSchema, parseYangFile } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_MODEL_JSON = join(__dirname, "../../../examples/meta-model.yang.json");
const META_MODEL_YANG = join(__dirname, "../../../examples/meta-model.yang");

function normalizePattern(pattern: unknown): string | null {
  if (typeof pattern !== "string" || pattern.trim().length === 0) {
    return null;
  }
  let s = pattern.trim();
  if (s.startsWith("^")) {
    s = s.slice(1);
  }
  if (s.endsWith("$")) {
    s = s.slice(0, -1);
  }
  return s || null;
}

function pathToText(path: unknown): string | null {
  if (typeof path === "string" && path.length > 0) {
    return path;
  }
  if (!path || typeof path !== "object" || Array.isArray(path)) {
    return null;
  }
  const shape = path as Record<string, unknown>;
  if (shape.kind !== "path") {
    return null;
  }
  const segments = Array.isArray(shape.segments)
    ? shape.segments
        .map((seg) => (seg && typeof seg === "object" ? (seg as Record<string, unknown>).step : undefined))
        .filter((step): step is string => typeof step === "string" && step.length > 0)
    : [];
  if (segments.length === 0) {
    return null;
  }
  const absolute = shape.isAbsolute === true;
  return `${absolute ? "/" : ""}${segments.join("/")}`;
}

function normalizeType(typeStmt: unknown): Record<string, unknown> | null {
  if (!typeStmt || typeof typeStmt !== "object" || Array.isArray(typeStmt)) {
    return null;
  }
  const t = typeStmt as Record<string, unknown>;
  return {
    name: typeof t.name === "string" ? t.name : "",
    pattern: normalizePattern(t.pattern),
    length: typeof t.length === "string" ? t.length : null,
    range: typeof t.range === "string" ? t.range : null,
    enums: Array.isArray(t.enums) ? [...(t.enums as string[])].sort() : [],
    require_instance: t.require_instance !== false,
    path: pathToText(t.path),
    types: Array.isArray(t.types) ? t.types.map((x) => normalizeType(x)) : [],
    bits: Array.isArray(t.bits)
      ? [...t.bits]
          .map((bit) => (bit && typeof bit === "object" ? bit : {}))
          .map((bit) => ({
            name: typeof (bit as Record<string, unknown>).name === "string" ? ((bit as Record<string, unknown>).name as string) : "",
            position: typeof (bit as Record<string, unknown>).position === "number" ? ((bit as Record<string, unknown>).position as number) : -1
          }))
          .sort((a, b) => (a.position - b.position) || a.name.localeCompare(b.name))
      : []
  };
}

function normalizeWhen(stmt: Record<string, unknown>): Record<string, unknown> | null {
  const w = stmt.when;
  if (!w || typeof w !== "object" || Array.isArray(w)) {
    return null;
  }
  const whenObj = w as Record<string, unknown>;
  const condition = typeof whenObj.expression === "string" ? whenObj.expression : "";
  if (!condition) {
    return null;
  }
  return {
    condition,
    description: typeof whenObj.description === "string" ? whenObj.description : ""
  };
}

function normalizeMust(stmt: Record<string, unknown>): string[] {
  const children = Array.isArray(stmt.statements) ? (stmt.statements as Array<Record<string, unknown>>) : [];
  return children
    .filter((child) => child.keyword === "must" && typeof child.argument === "string")
    .map((child) => child.argument as string);
}

function normalizeStatement(stmtLike: unknown): Record<string, unknown> | null {
  if (!stmtLike || typeof stmtLike !== "object" || Array.isArray(stmtLike)) {
    return null;
  }
  const stmt = stmtLike as Record<string, unknown>;
  const keyword = typeof stmt.keyword === "string" ? stmt.keyword : "";
  const name = typeof stmt.name === "string" ? stmt.name : "";
  const description = typeof stmt.description === "string" ? stmt.description : "";
  const out: Record<string, unknown> = { keyword, name, description };

  const childrenRaw = Array.isArray(stmt.statements) ? stmt.statements : [];

  if (keyword === "container") {
    out.when = normalizeWhen(stmt);
    out.presence = typeof stmt.presence === "string" ? stmt.presence : null;
    out.must = normalizeMust(stmt);
    out.children = childrenRaw.map((s) => normalizeStatement(s)).filter(Boolean).sort((a, b) => String((a as Record<string, unknown>).name).localeCompare(String((b as Record<string, unknown>).name)));
    return out;
  }

  if (keyword === "list") {
    out.when = normalizeWhen(stmt);
    out.key = typeof stmt.key === "string" ? stmt.key : null;
    out.min_elements = typeof stmt.min_elements === "number" ? stmt.min_elements : null;
    out.max_elements = typeof stmt.max_elements === "number" ? stmt.max_elements : null;
    out.must = normalizeMust(stmt);
    out.children = childrenRaw.map((s) => normalizeStatement(s)).filter(Boolean).sort((a, b) => String((a as Record<string, unknown>).name).localeCompare(String((b as Record<string, unknown>).name)));
    return out;
  }

  if (keyword === "leaf") {
    out.when = normalizeWhen(stmt);
    out.type = normalizeType(stmt.type);
    out.mandatory = stmt.mandatory === true;
    out.default = stmt.default ?? null;
    out.must = normalizeMust(stmt);
    return out;
  }

  if (keyword === "leaf-list") {
    out.when = normalizeWhen(stmt);
    out.type = normalizeType(stmt.type);
    out.min_elements = typeof stmt.min_elements === "number" ? stmt.min_elements : null;
    out.max_elements = typeof stmt.max_elements === "number" ? stmt.max_elements : null;
    out.must = normalizeMust(stmt);
    return out;
  }

  if (keyword === "choice") {
    out.mandatory = stmt.mandatory === true;
    out.cases = childrenRaw.map((s) => normalizeStatement(s)).filter(Boolean).sort((a, b) => String((a as Record<string, unknown>).name).localeCompare(String((b as Record<string, unknown>).name)));
    return out;
  }

  if (keyword === "case") {
    out.children = childrenRaw.map((s) => normalizeStatement(s)).filter(Boolean).sort((a, b) => String((a as Record<string, unknown>).name).localeCompare(String((b as Record<string, unknown>).name)));
    return out;
  }

  return null;
}

function normalizeModule(moduleData: Record<string, unknown>): Record<string, unknown> {
  const typedefs = (moduleData.typedefs as Record<string, unknown>) ?? {};
  const statements = Array.isArray(moduleData.statements) ? moduleData.statements : [];
  const normalizedTypedefs: Record<string, unknown> = {};
  for (const [name, entry] of Object.entries(typedefs)) {
    const rec = (entry && typeof entry === "object" && !Array.isArray(entry)) ? (entry as Record<string, unknown>) : {};
    normalizedTypedefs[name] = {
      name,
      type: normalizeType(rec.type)
    };
  }

  return {
    name: moduleData.name,
    namespace: moduleData.namespace,
    prefix: moduleData.prefix,
    yang_version: moduleData.yang_version ?? "1.1",
    typedefs: normalizedTypedefs,
    statements: statements.map((s) => normalizeStatement(s)).filter(Boolean).sort((a, b) => String((a as Record<string, unknown>).name).localeCompare(String((b as Record<string, unknown>).name)))
  };
}

function unionMemberNamesCompatible(jsonType: Record<string, unknown>, yangType: Record<string, unknown>): boolean {
  if (jsonType.name !== "union" || yangType.name !== "union") {
    return false;
  }
  const jtypes = Array.isArray(jsonType.types) ? jsonType.types : [];
  const ytypes = Array.isArray(yangType.types) ? yangType.types : [];
  if (jtypes.length !== ytypes.length) {
    return false;
  }
  for (let i = 0; i < jtypes.length; i += 1) {
    const jn = ((jtypes[i] as Record<string, unknown> | null)?.name as string | undefined) ?? "";
    const yn = ((ytypes[i] as Record<string, unknown> | null)?.name as string | undefined) ?? "";
    if (jn === yn) {
      continue;
    }
    if ((jn === "string" && yn === "primitive-type") || (jn === "primitive-type" && yn === "string")) {
      continue;
    }
    return false;
  }
  return true;
}

describe("python parity: json/test_meta_model_ast_identical", () => {
  it("meta-model JSON and YANG parse to identical normalized AST", () => {
    const jsonModule = parseJsonSchema(JSON.parse(readFileSync(META_MODEL_JSON, "utf-8")) as Record<string, unknown>);
    const yangModule = parseYangFile(META_MODEL_YANG);

    const normJson = normalizeModule(jsonModule.data as Record<string, unknown>);
    const normYang = normalizeModule(yangModule.data as Record<string, unknown>);

    expect(normJson.name).toBe(normYang.name);
    expect(normJson.namespace).toBe(normYang.namespace);
    expect(normJson.prefix).toBe(normYang.prefix);
    expect(normJson.yang_version).toBe(normYang.yang_version);

    const jsonTypedefs = normJson.typedefs as Record<string, Record<string, unknown>>;
    const yangTypedefs = normYang.typedefs as Record<string, Record<string, unknown>>;
    const common = Object.keys(jsonTypedefs).filter((k) => k in yangTypedefs);
    const mismatchedTypedefs: string[] = [];
    for (const name of common) {
      const jt = (jsonTypedefs[name].type as Record<string, unknown> | null) ?? null;
      const yt = (yangTypedefs[name].type as Record<string, unknown> | null) ?? null;
      if (jt && yt) {
        const compatible = jt.name === yt.name || unionMemberNamesCompatible(jt, yt);
        if (!compatible) {
          mismatchedTypedefs.push(`${name}: json=${String(jt.name)} yang=${String(yt.name)}`);
        }
      }
    }
    expect(mismatchedTypedefs, mismatchedTypedefs.join("; ")).toEqual([]);

    const jsonStatements = normJson.statements as Array<Record<string, unknown>>;
    const yangStatements = normYang.statements as Array<Record<string, unknown>>;
    expect(jsonStatements.length).toBe(yangStatements.length);
    for (let i = 0; i < jsonStatements.length; i += 1) {
      expect(jsonStatements[i]).toEqual(yangStatements[i]);
    }
  });
});
