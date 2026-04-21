/**
 * Helpers for per-validator type-validation tracing (see `YangValidator` /
 * `DocumentValidator.setTypeValidationDebug`).
 */

export function summarizeValue(value: unknown): string {
  if (value === null) {
    return "null";
  }
  const t = typeof value;
  if (t === "undefined") {
    return "undefined";
  }
  if (t === "string") {
    const s = value;
    if (s.length > 100) {
      return `string(len=${s.length}):${JSON.stringify(s.slice(0, 80))}…`;
    }
    return JSON.stringify(s);
  }
  if (t === "number" || t === "boolean" || t === "bigint") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `Array(${value.length})`;
  }
  if (t === "object") {
    try {
      const j = JSON.stringify(value);
      return j.length > 160 ? `${j.slice(0, 160)}…` : j;
    } catch {
      return "[object]";
    }
  }
  return String(value);
}

export function traceTypeValidation(
  enabled: boolean,
  message: string,
  fields: Record<string, unknown>
): void {
  if (!enabled) {
    return;
  }
  console.debug(`[xYang:type-validation] ${message}`, fields);
}
