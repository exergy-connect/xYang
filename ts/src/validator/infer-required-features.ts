import { YangModule, YangStatement } from "../core/model";
import { declaredFeatures, ModuleData, reachableModuleData, resolvePrefixedModule } from "./if-feature-eval";

/** Infer sorted module:feature requirements for present data; does not validate values. */
export function inferRequiredFeatures(module: YangModule, instance: unknown): string[] {
  const modules = reachableModuleData(module.data);
  const required = new Set<string>();
  const active = new Set<string>();
  const addConditions = (conditions: unknown, ctx: ModuleData): void => {
    for (const expression of (conditions ?? []) as string[]) {
      // Only positive conjunctions are supported; reject ambiguity rather than guess.
      const atoms = expression.trim().split(/\s+and\s+/);
      if (atoms.some(a => !/^[A-Za-z_][\w.-]*(?::[A-Za-z_][\w.-]*)?$/.test(a) || ["and", "or", "not"].includes(a))) {
        throw new Error(`Unsupported if-feature expression: ${expression}`);
      }
      for (const atom of atoms) {
        const parts = atom.split(":");
        const name = parts.at(-1)!;
        const owner = parts.length === 2 ? resolvePrefixedModule(ctx, parts[0]!) : ctx;
        if (!owner || !declaredFeatures(owner).has(name)) throw new Error(`Unknown feature: ${atom}`);
        const key = `${String(owner.name)}:${name}`;
        if (active.has(key)) throw new Error(`Cyclic feature prerequisite: ${key}`);
        if (required.has(key)) continue;
        active.add(key);
        addConditions((owner.feature_if_features as Record<string, string[]> | undefined)?.[name], owner);
        active.delete(key);
        required.add(key);
      }
    }
  };
  type Gate = { stmt: YangStatement; ctx: ModuleData };
  type Entry = { stmt: YangStatement; gates: Gate[]; ctx: ModuleData };
  const entries = (statements: YangStatement[], ctx: ModuleData, gates: Gate[] = []): Entry[] =>
    statements.flatMap(stmt => {
      const owner = stmt.data.defining_module;
      const local = owner ? modules.find(m => m.name === owner) : ctx;
      if (!local) throw new Error(`Unknown defining module: ${String(owner)}`);
      if (["choice", "case"].includes(stmt.keyword ?? "")) return entries(stmt.statements, local, [...gates, { stmt, ctx: local }]);
      return ["container", "list", "leaf", "leaf-list", "anydata", "anyxml"].includes(stmt.keyword ?? "")
        ? [{ stmt, gates, ctx: local }] : [];
    });
  const walk = (statements: YangStatement[], value: unknown, ctx: ModuleData): void => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Instance object expected");
    const candidates = entries(statements, ctx);
    for (const [key, child] of Object.entries(value)) {
      const matches = candidates.filter(e => key === `${String(e.ctx.name)}:${e.stmt.name}` ||
        (key === e.stmt.name && e.ctx === ctx));
      if (matches.length !== 1) throw new Error(`Unknown or ambiguous instance element: ${key}`);
      const { stmt, gates, ctx: local } = matches[0]!;
      for (const gate of gates) addConditions(gate.stmt.data.if_features, gate.ctx);
      addConditions(stmt.data.if_features, local);
      if (stmt.keyword === "container") walk(stmt.statements, child, local);
      if (stmt.keyword === "list") {
        if (!Array.isArray(child)) throw new Error(`List array expected: ${key}`);
        for (const row of child) walk(stmt.statements, row, local);
      }
    }
  };
  walk(module.statements, instance, module.data);
  return [...required].sort();
}
