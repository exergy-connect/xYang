import type { YangIdentifierRef } from "./core/identifier-ref";
import { parseIdentifierRefAtom } from "./core/identifier-ref";
import type { YangModule } from "./core/model";

/** (defining module, local identity name) */
export type IdentityPair = { mod: YangModule; local: string };

function ownPrefixStripped(mod: YangModule): string {
  return String(mod.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

type IdentityInfo = { bases: Array<string | YangIdentifierRef> };

function getIdentities(mod: YangModule): Record<string, IdentityInfo> {
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

export function resolvePrefixedModuleData(importer: YangModule, prefix: string): YangModule | undefined {
  const own = ownPrefixStripped(importer);
  if (prefix === own) {
    return importer;
  }
  const m = importer.import_prefixes[prefix];
  return m && typeof m === "object" ? m : undefined;
}

/** Resolve an RFC 7951 identityref instance value (``prefix:name`` string). */
export function resolveIdentityQnamePair(importer: YangModule, qname: string): IdentityPair | null {
  const ref = parseIdentifierRefAtom(qname);
  if (!ref.prefix) {
    return null;
  }
  return resolveIdentityBaseRef(importer, ref);
}

/**
 * Resolve an RFC 7951 identityref instance value (§6.8). `name` resolves in the module.
 * `modname:name` resolves where `modname` is the *module name* (not the prefix) of the
 * module itself or of a module it imports.
 */
export function resolveIdentityValue(moduleData: YangModule, value: unknown): IdentityPair | null {
  if (typeof value !== "string" || value.length === 0) {
    return null;
  }
  const colon = value.indexOf(":");
  let target: YangModule | undefined = moduleData;
  let local = value;
  if (colon >= 0) {
    const modName = value.slice(0, colon);
    local = value.slice(colon + 1);
    if (modName !== moduleData.name) {
      const imports = moduleData.import_prefixes;
      target = Object.values(imports).find((m) => m && typeof m === "object" && m.name === modName);
    }
  }
  if (!target || !(local in getIdentities(target))) {
    return null;
  }
  return { mod: target, local };
}

/** RFC 7950: the value must be derived from (or equal to) **every** identityref base. */
export function identityrefValueValid(
  moduleData: YangModule,
  value: unknown,
  bases: Array<string | YangIdentifierRef>
): boolean {
  if (bases.length === 0) {
    return false;
  }
  const v = resolveIdentityValue(moduleData, value);
  if (!v) {
    return false;
  }
  const closure = identityAncestorClosure(v.mod, v.local);
  return bases.every((b) => {
    const br = resolveIdentityBaseRef(moduleData, b);
    return br !== null && pairInPairs(br, closure);
  });
}

export function resolveIdentityBaseRef(
  fromMod: YangModule,
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
  startMod: YangModule,
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

/** `vQ` is an instance value (RFC 7951 module name); `tQ` is a schema literal (prefix). */
export function isDerivedFromStrictQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const v = resolveIdentityValue(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  const ancestors = identityAncestorClosure(v.mod, v.local).filter((p) => !pairEquals(p, v));
  return pairInPairs(t, ancestors);
}

export function isDerivedFromOrSelfQNames(importer: YangModule, vQ: string, tQ: string): boolean {
  const v = resolveIdentityValue(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  if (pairEquals(v, t)) {
    return true;
  }
  return pairInPairs(t, identityAncestorClosure(v.mod, v.local));
}
