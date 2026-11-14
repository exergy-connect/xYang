import type { YangStatement } from "../core/model";

export function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

type WhenRecord = Record<string, unknown>;

/**
 * RFC 7950: a `when` on `uses` or `augment` applies to every child it contributes, evaluated
 * against the parent context. A child without its own `when` gets a copy; otherwise the two
 * expressions are AND-ed and `extra` adds fields such as merged XPath prefixes.
 */
export function mergeParentWhen(
  owner: YangStatement,
  child: YangStatement,
  extra?: (existing: WhenRecord, ownerWhen: WhenRecord) => WhenRecord
): void {
  const ownerWhen = owner.when as WhenRecord | undefined;
  if (!ownerWhen || typeof ownerWhen.expression !== "string" || ownerWhen.expression.trim() === "") {
    return;
  }
  const existing = child.when as WhenRecord | undefined;
  if (!existing?.expression) {
    child.when = { ...deepClone(ownerWhen), evaluate_with_parent_context: true } as YangStatement["when"];
    return;
  }
  child.when = {
    ...existing,
    expression: `(${String(existing.expression)}) and (${ownerWhen.expression})`,
    ...(extra ? extra(existing, ownerWhen) : {}),
    description: String(existing.description ?? ""),
    evaluate_with_parent_context: true
  } as YangStatement["when"];
}
