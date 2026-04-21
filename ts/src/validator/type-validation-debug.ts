/**
 * Opt-in tracing for leaf / typedef / union type checks.
 *
 * Enable any of:
 * - `globalThis.__XYANG_DEBUG_TYPE_VALIDATION__ = true` (browser or Node)
 * - `process.env.XYANG_DEBUG_TYPE_VALIDATION=1` (Node / Vitest)
 * - `setTypeValidationDebug(true)` from the public API
 */

const GLOBAL_KEY = "__XYANG_DEBUG_TYPE_VALIDATION__";

let forcedOverride: boolean | undefined;

export function setTypeValidationDebug(on: boolean): void {
  forcedOverride = on;
  try {
    (globalThis as Record<string, unknown>)[GLOBAL_KEY] = on;
  } catch {
    /* ignore */
  }
}

export function isTypeValidationDebugEnabled(): boolean {
  if (forcedOverride !== undefined) {
    return forcedOverride;
  }
  try {
    if ((globalThis as Record<string, unknown>)[GLOBAL_KEY] === true) {
      return true;
    }
  } catch {
    /* ignore */
  }
  try {
    const proc = typeof process !== "undefined" ? process : undefined;
    if (proc?.env?.XYANG_DEBUG_TYPE_VALIDATION === "1") {
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

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

export function traceTypeValidation(message: string, fields: Record<string, unknown>): void {
  if (!isTypeValidationDebugEnabled()) {
    return;
  }
  console.debug(`[xYang:type-validation] ${message}`, fields);
}
