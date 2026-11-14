import { resolveTypedef } from "./type-checker";
import { REGISTRY } from "../types/registry";
import { YangSemanticError } from "../core/errors";
import { YangStatement, YangModule } from "../core/model";

function iterStatements(statements: YangStatement[] | undefined): YangStatement[] {
  const out: YangStatement[] = [];
  for (const stmt of statements ?? []) {
    out.push(stmt);
    out.push(...iterStatements(stmt.statements));
  }
  return out;
}

function validateListKeyConstraints(module: YangModule): void {
  for (const stmt of iterStatements(module.statements)) {
    if (stmt.keyword !== "list" || typeof stmt.key !== "string" || stmt.key.trim() === "") {
      continue;
    }
    const keyLeaves = new Map(
      (stmt.statements ?? [])
        .filter((child) => child.keyword === "leaf" && typeof child.name === "string")
        .map((child) => [child.name as string, child])
    );
    for (const keyName of stmt.key.split(/\s+/).filter(Boolean)) {
      const child = keyLeaves.get(keyName);
      if (child === undefined) {
        throw new YangSemanticError(
          `List '${stmt.name ?? ""}': key leaf '${keyName}' does not exist ` +
            "(RFC 7950: each list key name must refer to a child leaf)."
        );
      }
      let illegal: string | undefined;
      if (child.when !== undefined) {
        illegal = "when";
      } else if (Array.isArray(child.if_features) && child.if_features.length > 0) {
        illegal = "if-feature";
      }
      if (illegal === undefined) {
        continue;
      }
      throw new YangSemanticError(
        `List '${stmt.name ?? ""}': key leaf '${child.name}' must not have '${illegal}' ` +
          "(RFC 7950: 'when' and 'if-feature' are illegal on list keys)."
      );
    }
  }
}

export function validateSemantics(module: YangModule): void {
  validateListKeyConstraints(module);
  const checkType = (type: Record<string, unknown> | undefined, stack = new Set<object>()): void => {
    if (!type) return;
    if (type.prefix || !Object.prototype.hasOwnProperty.call(REGISTRY, String(type.name))) {
      const td = resolveTypedef(module, type);
      if (!td) throw new YangSemanticError(`Unknown typedef '${type.name}' in lexical scope`);
      if (stack.has(td)) throw new YangSemanticError(`Circular typedef '${type.name}'`);
      checkType(td.type, new Set([...stack, td]));
    }
    for (const member of (type.types ?? []) as Record<string, unknown>[]) checkType(member, stack);
  };
  for (const td of Object.values(module.typedefs) as Array<{ type?: Record<string, unknown> }>) checkType(td.type);
  for (const stmt of iterStatements(module.statements)) checkType(stmt.type);
}
