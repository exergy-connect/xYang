/** Scope restrictions on the global typedef table (RFC 7950 §§5.4–5.5). */
import { YangSemanticError } from "./core/errors";
import { REGISTRY } from "./types/registry";

export type ScopedTypedef = { name?: string; scope?: string; type?: Record<string, unknown>; units?: string };
export function inScope(scope: string | undefined, context: string): boolean {
  return scope === undefined || context === scope || context.startsWith(scope + "/");
}
export function scopePath(context: string, parent: unknown): string {
  const stmt = parent as { keyword?: string; name?: string } | undefined;
  if (!stmt || !["container", "list", "grouping", "rpc", "action", "input", "output", "notification"].includes(stmt.keyword ?? "")) return context;
  const name = stmt.keyword === "grouping" ? `@grouping:${stmt.name}` : ["input", "output"].includes(stmt.keyword ?? "") ? stmt.keyword! : stmt.name ?? "";
  return context + "/" + name.replace(/~/g, "~0").replace(/\//g, "~1");
}
export function registerTypedef(typedefs: Record<string, ScopedTypedef>, td: ScopedTypedef): void {
  for (const previous of Object.values(typedefs)) {
    if (previous.name === td.name && (inScope(previous.scope, td.scope ?? "") || inScope(td.scope, previous.scope ?? ""))) {
      throw new YangSemanticError(`Duplicate typedef '${td.name}' in lexical scope`);
    }
  }
  if (Object.prototype.hasOwnProperty.call(REGISTRY, td.name ?? "")) throw new YangSemanticError(`Duplicate typedef '${td.name}': built-in type`);
  typedefs[(td.scope ? td.scope + "/" : "") + td.name] = td;
}
export function validateScope(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || !value.startsWith("/") || value.endsWith("/") || value.includes("//") || /~(?:[^01]|$)/.test(value)) throw new Error("typedef scope must be a non-empty absolute context path");
  return value;
}
