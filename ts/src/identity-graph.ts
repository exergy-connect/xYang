import type { YangIdentifierRef } from "./core/identifier-ref";
import { parseIdentifierRefAtom } from "./core/identifier-ref";
import type { YangModule } from "./core/model";

/** (defining module data, local identity name) */
export type IdentityPair = { mod: Record<string, unknown>; local: string };

function ownPrefixStripped(mod: Record<string, unknown>): string {
  return String(mod.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

type IdentityInfo = { bases: Array<string | YangIdentifierRef> };

function getIdentities(mod: Record<string, unknown>): Record<string, IdentityInfo> {
  const raw = mod.identities;
  if (!raw || typeof raw !== "object") {
    return {};
  }
  return raw as Record<string, IdentityInfo>;
}

function asBaseRef(base: string | YangIdentifierRef): YangIdentifierRef {
  if (typeof base === "string") {
    return parseIdentifierRefAtom(base);
  }
  return base.prefix ? { prefix: base.prefix, name: base.name } : { name: base.name };
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

/** Resolve an RFC 7951 identityref instance value (``prefix:name`` string). */
export function resolveIdentityQnamePair(importer: YangModule, qname: string): IdentityPair | null {
  const ref = parseIdentifierRefAtom(qname);
  if (!ref.prefix) {
    return null;
  }
  return resolveIdentityBaseRef(importer.data, ref);
}

export function resolveIdentityBaseRef(
  fromMod: Record<string, unknown>,
  base: string | YangIdentifierRef
): IdentityPair | null {
  const ref = asBaseRef(base);
  if (ref.prefix) {
    const m = resolvePrefixedModuleData(fromMod, ref.prefix);
    if (!m || !(ref.name in getIdentities(m))) {
      return null;
    }
    return { mod: m, local: ref.name };
  }
  if (ref.name in getIdentities(fromMod)) {
    return { mod: fromMod, local: ref.name };
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
export function identityAncestorClosure(
  startMod: Record<string, unknown>,
  startName: string
): IdentityPair[] {
  const start: IdentityPair = { mod: startMod, local: startName };
  const out: IdentityPair[] = [];
  const seen = new Set<string>();
  const stack: IdentityPair[] = [start];
  while (stack.length > 0) {
    const cur = stack.pop()!;
    const key = pairKey(cur);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(cur);
    const stmt = getIdentities(cur.mod)[cur.local];
    if (!stmt?.bases) {
      continue;
    }
    for (const b of stmt.bases) {
      const parent = resolveIdentityBaseRef(cur.mod, b);
      if (parent) {
        stack.push(parent);
      }
    }
  }
  return out;
}

export function isDerivedFromStrictQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const v = resolveIdentityQnamePair(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  const ancestors = identityAncestorClosure(v.mod, v.local).filter((p) => !pairEquals(p, v));
  return pairInPairs(t, ancestors);
}

export function isDerivedFromOrSelfQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const v = resolveIdentityQnamePair(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  if (pairEquals(v, t)) {
    return true;
  }
  return pairInPairs(t, identityAncestorClosure(v.mod, v.local));
}
