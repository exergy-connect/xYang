import type { YangModule } from "./core/model";

/** (defining module data, local identity name) */
export type IdentityPair = { mod: Record<string, unknown>; local: string };

function ownPrefixStripped(mod: Record<string, unknown>): string {
  return String(mod.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

function getIdentities(mod: Record<string, unknown>): Record<string, { bases: string[] }> {
  const raw = mod.identities;
  if (!raw || typeof raw !== "object") {
    return {};
  }
  return raw as Record<string, { bases: string[] }>;
}

export function resolvePrefixedModuleData(
  importerData: Record<string, unknown>,
  prefix: string
): Record<string, unknown> | undefined {
  const own = ownPrefixStripped(importerData);
  if (prefix === own) {
    return importerData;
  }
  const imports = (importerData.import_prefixes as Record<string, Record<string, unknown>> | undefined) ?? {};
  const m = imports[prefix];
  return m && typeof m === "object" ? m : undefined;
}

export function resolveIdentityQnamePair(importer: YangModule, qname: string): IdentityPair | null {
  if (!qname.includes(":")) {
    return null;
  }
  const [pref, local] = qname.split(":", 2);
  const m = resolvePrefixedModuleData(importer.data, pref);
  if (!m || !(local in getIdentities(m))) {
    return null;
  }
  return { mod: m, local };
}

export function resolveIdentityBaseRef(fromMod: Record<string, unknown>, base: string): IdentityPair | null {
  if (base.includes(":")) {
    const [pref, local] = base.split(":", 2);
    const m = resolvePrefixedModuleData(fromMod, pref);
    if (!m || !(local in getIdentities(m))) {
      return null;
    }
    return { mod: m, local };
  }
  if (base in getIdentities(fromMod)) {
    return { mod: fromMod, local: base };
  }
  return null;
}

function pairEquals(a: IdentityPair, b: IdentityPair): boolean {
  return a.mod === b.mod && a.local === b.local;
}

function pairInPairs(p: IdentityPair, pairs: IdentityPair[]): boolean {
  return pairs.some((x) => pairEquals(x, p));
}

const moduleSlot = new WeakMap<object, number>();
let nextModuleSlot = 1;

function moduleId(mod: object): number {
  let id = moduleSlot.get(mod);
  if (id === undefined) {
    id = nextModuleSlot;
    nextModuleSlot += 1;
    moduleSlot.set(mod, id);
  }
  return id;
}

function pairKey(p: IdentityPair): string {
  return `${moduleId(p.mod)}:${p.local}`;
}

/** Reflexive transitive closure of identity bases from (startMod, startName). */
export function identityAncestorClosure(startMod: Record<string, unknown>, startName: string): IdentityPair[] {
  const out: IdentityPair[] = [];
  const seen = new Set<string>();
  const stack: IdentityPair[] = [{ mod: startMod, local: startName }];

  while (stack.length > 0) {
    const pair = stack.pop()!;
    const k = pairKey(pair);
    if (seen.has(k)) {
      continue;
    }
    seen.add(k);
    out.push(pair);

    const stmt = getIdentities(pair.mod)[pair.local];
    if (!stmt?.bases) {
      continue;
    }
    for (const b of stmt.bases) {
      const nxt = resolveIdentityBaseRef(pair.mod, b);
      if (nxt) {
        stack.push(nxt);
      }
    }
  }

  return out;
}

export function isDerivedFromStrictQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const pv = resolveIdentityQnamePair(importer, vQ);
  const pt = resolveIdentityQnamePair(importer, tQ);
  if (!pv || !pt) {
    return false;
  }
  const closure = identityAncestorClosure(pv.mod, pv.local);
  return pairInPairs(pt, closure) && !pairEquals(pt, pv);
}

export function isDerivedFromOrSelfQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const pv = resolveIdentityQnamePair(importer, vQ);
  const pt = resolveIdentityQnamePair(importer, tQ);
  if (!pv || !pt) {
    return false;
  }
  const closure = identityAncestorClosure(pv.mod, pv.local);
  return pairInPairs(pt, closure);
}
