/**
 * YANG 1.1 if-feature boolean expressions (RFC 7950 §7.20.2, §14).
 * Multiple if-feature substatements on one node are combined with logical AND.
 */

export type ModuleData = Record<string, unknown>;

function stripQuotes(prefix: unknown): string {
  return String(prefix ?? "").replace(/^['"]|['"]$/g, "");
}

function moduleName(m: ModuleData): string {
  return String(m.name ?? "");
}

export function declaredFeatures(m: ModuleData): Set<string> {
  const f = m.features;
  if (f instanceof Set) {
    return new Set(f as Set<string>);
  }
  if (Array.isArray(f)) {
    return new Set(f as string[]);
  }
  return new Set();
}

export function resolvePrefixedModule(ctx: ModuleData, prefix: string): ModuleData | undefined {
  const own = stripQuotes(ctx.prefix);
  if (prefix === own) {
    return ctx;
  }
  const imports = ctx.import_prefixes as Record<string, ModuleData> | undefined;
  const hit = imports?.[prefix];
  if (hit && typeof hit === "object") {
    return hit;
  }
  return undefined;
}

export function reachableModuleData(root: ModuleData): ModuleData[] {
  const out: ModuleData[] = [];
  const seen = new Set<ModuleData>();
  const walk = (m: ModuleData): void => {
    if (seen.has(m)) {
      return;
    }
    seen.add(m);
    out.push(m);
    const im = m.import_prefixes as Record<string, ModuleData> | undefined;
    if (!im) {
      return;
    }
    for (const v of Object.values(im)) {
      if (v && typeof v === "object") {
        walk(v);
      }
    }
  };
  walk(root);
  return out;
}

export function featureIsSupported(
  ctxModule: ModuleData,
  enabledByModule: Readonly<Record<string, ReadonlySet<string>>>,
  ref: string
): boolean {
  let mod: ModuleData;
  let fname: string;
  const idx = ref.indexOf(":");
  if (idx !== -1) {
    const pref = ref.slice(0, idx);
    fname = ref.slice(idx + 1);
    const resolved = resolvePrefixedModule(ctxModule, pref);
    if (!resolved) {
      return false;
    }
    mod = resolved;
  } else {
    mod = ctxModule;
    fname = ref;
  }
  if (!declaredFeatures(mod).has(fname)) {
    return false;
  }
  const enabled = enabledByModule[moduleName(mod)];
  if (!enabled) {
    return false;
  }
  return enabled.has(fname);
}

function tokenize(expr: string): string[] {
  const tokens: string[] = [];
  let i = 0;
  const n = expr.length;
  while (i < n) {
    const c = expr[i]!;
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if (c === "(" || c === ")") {
      tokens.push(c);
      i += 1;
      continue;
    }
    let j = i;
    while (j < n && !/\s/.test(expr[j]!) && expr[j] !== "(" && expr[j] !== ")") {
      j += 1;
    }
    tokens.push(expr.slice(i, j));
    i = j;
  }
  return tokens;
}

class IfFeatureParser {
  private i = 0;

  constructor(
    private readonly toks: string[],
    private readonly ctx: ModuleData,
    private readonly enabled: Readonly<Record<string, ReadonlySet<string>>>
  ) {}

  private peek(): string | undefined {
    return this.toks[this.i];
  }

  private eat(expected?: string): string {
    const t = this.peek();
    if (t === undefined) {
      throw new Error("unexpected end of expression");
    }
    if (expected !== undefined && t !== expected) {
      throw new Error(`expected ${expected}, got ${t}`);
    }
    this.i += 1;
    return t;
  }

  parseExpr(): boolean {
    let left = this.parseTerm();
    while (this.peek() === "or") {
      this.eat("or");
      const right = this.parseExpr();
      left = left || right;
    }
    return left;
  }

  parseTerm(): boolean {
    let left = this.parseFactor();
    while (this.peek() === "and") {
      this.eat("and");
      const right = this.parseTerm();
      left = left && right;
    }
    return left;
  }

  parseFactor(): boolean {
    const t = this.peek();
    if (t === "not") {
      this.eat("not");
      return !this.parseFactor();
    }
    if (t === "(") {
      this.eat("(");
      const v = this.parseExpr();
      this.eat(")");
      return v;
    }
    if (t === undefined) {
      throw new Error("unexpected end of expression");
    }
    this.eat();
    return featureIsSupported(this.ctx, this.enabled, t);
  }

  atEnd(): boolean {
    return this.i >= this.toks.length;
  }
}

export function evaluateIfFeatureExpression(
  expr: string,
  ctxModule: ModuleData,
  enabledByModule: Readonly<Record<string, ReadonlySet<string>>>
): boolean {
  const trimmed = expr.trim();
  if (!trimmed) {
    return false;
  }
  try {
    const p = new IfFeatureParser(tokenize(trimmed), ctxModule, enabledByModule);
    const out = p.parseExpr();
    if (!p.atEnd()) {
      return false;
    }
    return out;
  } catch {
    return false;
  }
}

export function stmtIfFeaturesSatisfied(
  ifFeatures: string[] | undefined,
  ctxModule: ModuleData,
  enabledByModule: Readonly<Record<string, ReadonlySet<string>>>
): boolean {
  if (!ifFeatures || ifFeatures.length === 0) {
    return true;
  }
  return ifFeatures.every((e) => evaluateIfFeatureExpression(e, ctxModule, enabledByModule));
}

function normalizeOverride(
  override: ReadonlyMap<string, ReadonlySet<string>> | Record<string, ReadonlySet<string>> | null | undefined
): Map<string, ReadonlySet<string>> | null {
  if (override == null) {
    return null;
  }
  if (override instanceof Map) {
    return new Map(override);
  }
  return new Map(Object.entries(override));
}

function prunePerFeatureIfFeatures(
  modules: ModuleData[],
  enabled: Record<string, Set<string>>
): Record<string, ReadonlySet<string>> {
  let changed = true;
  while (changed) {
    changed = false;
    const frozen: Record<string, ReadonlySet<string>> = {};
    for (const [mn, s] of Object.entries(enabled)) {
      frozen[mn] = new Set(s);
    }
    for (const m of modules) {
      const mn = moduleName(m);
      const mutable = enabled[mn];
      if (!mutable) {
        continue;
      }
      const fif = m.feature_if_features as Record<string, string[]> | undefined;
      for (const fname of [...mutable]) {
        const reqs = fif?.[fname];
        if (!reqs?.length) {
          continue;
        }
        if (!stmtIfFeaturesSatisfied(reqs, m, frozen)) {
          mutable.delete(fname);
          changed = true;
        }
      }
    }
  }
  const out: Record<string, ReadonlySet<string>> = {};
  for (const [k, v] of Object.entries(enabled)) {
    out[k] = new Set(v);
  }
  return out;
}

/**
 * For each reachable module, the set of feature names that are enabled.
 * - override is null/undefined: every declared feature is enabled.
 * - override[moduleName] present: only those names are enabled for that module.
 * - Module not listed: all declared features enabled for that module.
 */
export function buildEnabledFeaturesMap(
  root: ModuleData,
  override: ReadonlyMap<string, ReadonlySet<string>> | Record<string, ReadonlySet<string>> | null | undefined
): Record<string, ReadonlySet<string>> {
  const modules = reachableModuleData(root);
  const ov = normalizeOverride(override);
  const enabled: Record<string, Set<string>> = {};
  for (const m of modules) {
    const mn = moduleName(m);
    const declared = declaredFeatures(m);
    if (ov === null || !ov.has(mn)) {
      enabled[mn] = new Set(declared);
    } else {
      enabled[mn] = new Set(ov.get(mn) ?? []);
    }
  }
  return prunePerFeatureIfFeatures(modules, enabled);
}
