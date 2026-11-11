import { YangExportError } from "../core/errors";
import { coerceIdentifierRef, formatIdentifierRef } from "../core/identifier-ref";
import type { IdentityBases, YangModule } from "../core/model";
import {
  identityAncestorClosure,
  resolveIdentityBaseRef,
  type IdentityPair
} from "../identity-graph";
import { XYANG_KEYS, YANG_SCHEMA_KEYS } from "./schema-keys";

type Export = { root: YangModule; used: IdentityPair[] };

let active: Export | undefined;

/** Run *fn* with *root* as the module being exported; identity bases resolved outside it are recorded. */
export function withIdentityExport<T>(root: YangModule, fn: (used: IdentityPair[]) => T): T {
  const previous = active;
  const current: Export = { root, used: [] };
  active = current;
  try {
    return fn(current.used);
  } finally {
    active = previous;
  }
}

function ownPrefix(module: YangModule): string {
  return String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

/** Key of *module* in the root `x-yang.imports`: the prefix that imports it, else its name. */
function importKey(root: YangModule, module: YangModule): string {
  for (const [prefix, imported] of Object.entries(root.import_prefixes)) {
    if (imported === module || imported.name === module.name) {
      return prefix;
    }
  }
  const name = module.name ?? "";
  if (name in root.import_prefixes || name === ownPrefix(root)) {
    throw new YangExportError(
      `cannot export identities of module '${name}': the name is also a prefix of module '${root.name}'`
    );
  }
  return name;
}

function scopeModule(root: YangModule, scopeName: unknown): YangModule {
  if (typeof scopeName !== "string" || scopeName === "" || scopeName === root.name) {
    return root;
  }
  const loaded = root.module_registry?.[scopeName];
  if (!loaded) {
    throw new YangExportError(`type is written in module '${scopeName}', which is not loaded`);
  }
  return loaded;
}

/** `{base, ref}` of one identity `base` written in `scope`, re-expressed in the exported module's scope. */
function identityBaseForJson(base: unknown, scope: YangModule, root: YangModule): { base: string; ref: string } {
  const parsed = coerceIdentifierRef(base);
  const label = parsed ? formatIdentifierRef(parsed) : String(base);
  const pair = parsed ? resolveIdentityBaseRef(scope, parsed) : null;
  if (!pair) {
    throw new YangExportError(`cannot export identity base '${label}': it does not resolve in module '${scope.name}'`);
  }
  if (pair.mod.name === root.name) {
    return { base: pair.local, ref: `#/$defs/${pair.local}` };
  }
  active?.used.push(pair);
  const key = importKey(root, pair.mod);
  return {
    base: `${key}:${pair.local}`,
    ref: `#/${YANG_SCHEMA_KEYS.xYang}/${XYANG_KEYS.imports}/${key}/${XYANG_KEYS.identities}/${pair.local}`
  };
}

/** JSON Schema of an `identityref` type: `$ref` (or `allOf` of them) to each base, plus `x-yang`. */
export function identityrefSchema(typeShape: Record<string, unknown>): Record<string, unknown> {
  const rawBases = Array.isArray(typeShape.identityref_bases) ? typeShape.identityref_bases : [];
  if (rawBases.length === 0) {
    return { type: "string" };
  }
  if (!active) {
    throw new YangExportError("cannot export an identityref outside generateJsonSchema");
  }
  const scope = scopeModule(active.root, typeShape.scope_module);
  const exported = rawBases.map((b) => identityBaseForJson(b, scope, active!.root));
  const xYang = { type: "identityref", bases: exported.map((e) => e.base) };
  if (exported.length === 1) {
    return { $ref: exported[0]!.ref, [YANG_SCHEMA_KEYS.xYang]: xYang };
  }
  return { allOf: exported.map((e) => ({ $ref: e.ref })), [YANG_SCHEMA_KEYS.xYang]: xYang };
}

function basesText(bases: unknown): string[] {
  return (Array.isArray(bases) ? bases : [])
    .map((b) => coerceIdentifierRef(b))
    .filter((b): b is NonNullable<typeof b> => Boolean(b))
    .map((b) => formatIdentifierRef(b));
}

/** `$defs`-shaped identity entry; the enum holds the descendants in `only` (default: every identity of the module). */
export function identityDef(module: YangModule, name: string, only?: Set<string>): Record<string, unknown> {
  const identities = module.identities as Record<string, IdentityBases>;
  const children: Record<string, string[]> = {};
  for (const [id, info] of Object.entries(identities)) {
    for (const base of basesText(info?.bases)) {
      (children[base] ??= []).push(id);
    }
  }
  const out = new Set<string>([name]);
  const stack = [...(children[name] ?? [])];
  while (stack.length > 0) {
    const next = stack.pop() as string;
    if (!out.has(next)) {
      out.add(next);
      stack.push(...(children[next] ?? []));
    }
  }
  const prefix = ownPrefix(module);
  const names = [...out].filter((n) => !only || only.has(n)).sort();
  const bases = basesText(identities[name]?.bases);
  const description = identities[name]?.description;
  const ifFeatures = identities[name]?.if_features ?? [];
  return {
    type: "string",
    enum: names.map((n) => `${prefix}:${n}`),
    ...(typeof description === "string" && description.length > 0 ? { description } : {}),
    [YANG_SCHEMA_KEYS.xYang]: {
      type: "identity",
      bases,
      ...(ifFeatures.length > 0 ? { "if-features": [...ifFeatures] } : {})
    }
  };
}

function stub(module: YangModule, names: Map<string, Set<string>>): Record<string, unknown> {
  const mine = names.get(module.name ?? "") as Set<string>;
  const identities: Record<string, unknown> = {};
  const imports: Record<string, unknown> = {};
  const raw = module.identities as Record<string, { bases?: unknown }>;
  for (const name of [...mine].sort()) {
    identities[name] = identityDef(module, name, mine);
    for (const base of Array.isArray(raw[name]?.bases) ? (raw[name]!.bases as unknown[]) : []) {
      const ref = coerceIdentifierRef(base);
      const pair = ref ? resolveIdentityBaseRef(module, ref) : null;
      if (!ref || !pair) {
        throw new YangExportError(
          `cannot export identity '${name}' of module '${module.name}': base '${String(base)}' does not resolve there`
        );
      }
      if (pair.mod.name !== module.name) {
        imports[ref.prefix as string] = stub(pair.mod, names);
      }
    }
  }
  const sortedImports = Object.fromEntries(Object.entries(imports).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
  return {
    module: module.name,
    namespace: module.namespace ?? "",
    prefix: module.prefix ?? "",
    ...(Object.keys(sortedImports).length > 0 ? { [XYANG_KEYS.imports]: sortedImports } : {}),
    [XYANG_KEYS.identities]: identities
  };
}

/**
 * Imported identities the exported module needs, so the JSON form resolves them without `import`: every
 * identity an `identityref` base names, the bases of the module's own identities, and the identities of a
 * directly imported module that derive from one of those, each with its bases.
 */
export function importsForJson(root: YangModule, used: IdentityPair[]): Record<string, unknown> {
  const usedKeys = new Set(used.map((p) => `${p.mod.name}\u0000${p.local}`));
  const own = root.identities as Record<string, { bases?: unknown }>;
  for (const [name, info] of Object.entries(own)) {
    for (const base of Array.isArray(info?.bases) ? (info!.bases as unknown[]) : []) {
      const ref = coerceIdentifierRef(base);
      if (!ref || !resolveIdentityBaseRef(root, ref)) {
        throw new YangExportError(
          `cannot export identity '${name}': base '${ref ? formatIdentifierRef(ref) : String(base)}' does not resolve in module '${root.name}'`
        );
      }
    }
  }
  const names = new Map<string, Set<string>>();
  const need = (pairs: IdentityPair[]): void => {
    for (const p of pairs) {
      const key = p.mod.name ?? "";
      if (!names.has(key)) names.set(key, new Set());
      names.get(key)!.add(p.local);
    }
  };
  const candidates: IdentityPair[] = Object.keys(own).map((local) => ({ mod: root, local }));
  for (const imported of Object.values(root.import_prefixes)) {
    for (const local of Object.keys(imported.identities)) {
      candidates.push({ mod: imported, local });
    }
  }
  for (const c of candidates) {
    const closure = identityAncestorClosure(c.mod, c.local);
    if (c.mod === root || closure.some((p) => usedKeys.has(`${p.mod.name}\u0000${p.local}`))) {
      need(closure);
    }
  }
  need(used);
  names.delete(root.name ?? "");
  const out: Record<string, unknown> = {};
  for (const module of [...Object.values(root.import_prefixes), ...used.map((p) => p.mod)]) {
    if (names.has(module.name ?? "")) {
      out[importKey(root, module)] = stub(module, names);
    }
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}
