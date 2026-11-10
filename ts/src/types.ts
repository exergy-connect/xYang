import { isQuotedInteger, REGISTRY, YANG_INTEGER_BOUNDS } from "./types/registry";
import { YangTokenType } from "./parser/parser-context";
import { translateXsdRegex } from "./xsd-regex";

/** `(code, message)`. The same pair Python's type checker returns. */
export type TypeIssue = [code: string, message: string];

export type TypeConstraintInput = {
  patterns?: Array<{
    pattern: string;
    invert_match?: boolean;
    error_message?: string;
    error_app_tag?: string;
  }>;
  length?: string;
  range?: string;
  length_error_message?: string;
  length_error_app_tag?: string;
  range_error_message?: string;
  range_error_app_tag?: string;
  fraction_digits?: number;
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: Array<Record<string, unknown>>;
};

export class TypeConstraint {
  patterns?: Array<{
    pattern: string;
    invert_match?: boolean;
    error_message?: string;
    error_app_tag?: string;
  }>;
  length?: string;
  range?: string;
  length_error_message?: string;
  length_error_app_tag?: string;
  range_error_message?: string;
  range_error_app_tag?: string;
  fraction_digits?: number;
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: Array<Record<string, unknown>>;

  constructor(input: TypeConstraintInput = {}) {
    Object.assign(this, input);
  }
}

function restrictionMessage(defaultMsg: string, message?: string, tag?: string): string {
  return patternEntryViolationMessage({ error_message: message, error_app_tag: tag }, defaultMsg);
}

function patternEntryViolationMessage(
  p: { error_message?: string; error_app_tag?: string },
  defaultMsg: string
): string {
  const msg =
    typeof p.error_message === "string" && p.error_message.trim().length > 0
      ? p.error_message
      : defaultMsg;
  const tag = typeof p.error_app_tag === "string" ? p.error_app_tag.trim() : "";
  return tag.length > 0 ? `${msg} (error-app-tag: ${tag})` : msg;
}

function parseRangeText(raw: string): Array<{ min: number; max: number }> {
  const parseBound = (text: string, kind: "min" | "max"): number => {
    const t = text.trim().toLowerCase();
    if (t === "min") {
      return Number.NEGATIVE_INFINITY;
    }
    if (t === "max") {
      return Number.POSITIVE_INFINITY;
    }
    const n = Number(t);
    if (Number.isNaN(n)) {
      return kind === "min" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
    }
    return n;
  };

  return raw
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [minRaw, maxRaw] = part.split("..").map((x) => x.trim());
      if (!maxRaw) {
        const n = parseBound(minRaw, "min");
        return { min: n, max: n };
      }
      return { min: parseBound(minRaw, "min"), max: parseBound(maxRaw, "max") };
    });
}

function matchesRange(value: number, raw: string): boolean {
  for (const band of parseRangeText(raw)) {
    if (value >= band.min && value <= band.max) {
      return true;
    }
  }
  return false;
}

/** @internal JSON number that is an integer. Strings are not integers (RFC 7951 §6.1). */
export function integerLike(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) {
    return value;
  }
  return null;
}

/** Exact decimal64 text. Distinct from a plain string so unions can tell them apart. */
export class ExactDecimal {
  constructor(readonly text: string) {}
}

const INT64_MIN = BigInt("-9223372036854775808");
const INT64_MAX = BigInt("9223372036854775807");
const UINT64_MAX = BigInt("18446744073709551615");

function decimalLike(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return null;
}

function validateIntegerBuiltin(
  typeName: string,
  value: unknown,
  range?: string,
  diag?: { error_message?: string; error_app_tag?: string }
): TypeIssue[] {
  const bounds = YANG_INTEGER_BOUNDS[typeName];
  if (!bounds) {
    return [["type", `Unsupported integer type '${typeName}'`]];
  }
  if (typeof value === "string") {
    // Quoted 64-bit integers are decoded to bigint by the instance iterator.
    // A string that reaches this check is not a JSON integer.
    return [["type", REGISTRY[typeName].checkValue(value, null) ?? "Expected integer, got string"]];
  }
  if (typeof value === "bigint" && isQuotedInteger(typeName)) {
    const unsigned = YANG_INTEGER_BOUNDS[typeName]?.[0] === 0;
    const lo = unsigned ? BigInt(0) : INT64_MIN;
    const hi = unsigned ? UINT64_MAX : INT64_MAX;
    if (value < lo || value > hi) {
      return [["type", `Value ${value} is outside ${typeName}`]];
    }
    if (range) {
      const asNumber = Number(value);
      if (!Number.isSafeInteger(asNumber) || !matchesRange(asNumber, range)) {
        if (!Number.isSafeInteger(asNumber)) {
          return [];
        }
        return [["range", restrictionMessage(`Integer ${value} does not match ${range}`, diag?.error_message, diag?.error_app_tag)]];
      }
    }
    return [];
  }
  const n = integerLike(value);
  if (n === null) {
    return [["type", `Expected ${typeName}`]];
  }
  if (range) {
    if (!matchesRange(n, range)) {
      return [["range", restrictionMessage(`Integer ${n} does not match ${range}`, diag?.error_message, diag?.error_app_tag)]];
    }
    return [];
  }
  const [lo, hi] = bounds;
  if (n < lo) {
    return [["range", `Value ${n} is less than minimum ${lo}`]];
  }
  if (n > hi) {
    return [["range", `Value ${n} exceeds maximum ${hi}`]];
  }
  return [];
}

function validateBinary(
  value: unknown,
  length?: string,
  diag?: { error_message?: string; error_app_tag?: string }
): TypeIssue[] {
  if (typeof value !== "string") {
    return [["type", "Expected base64 string"]];
  }

  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) {
    return [["type", "Expected valid base64 string"]];
  }

  try {
    const bytes = Buffer.from(value, "base64");
    if (length && !matchesRange(bytes.length, length)) {
      // A length miss stops here. Pattern is not also reported (same as Python).
      return [["length", restrictionMessage(`Binary length ${bytes.length} does not match ${length}`, diag?.error_message, diag?.error_app_tag)]];
    }
  } catch {
    return [["type", "Expected valid base64 string"]];
  }

  return [];
}

function validateBits(value: unknown, bits: Array<{ name: string; position: number }>): TypeIssue[] {
  if (typeof value !== "string") {
    return [["bits", "Bits values must be string tokens"]];
  }
  const allowed = new Set(bits.map((bit) => bit.name));
  if (value.trim() === "") {
    return [];
  }
  const seen = new Set<string>();
  for (const token of value.trim().split(/\s+/)) {
    if (!allowed.has(token)) {
      return [["bits", `Unknown bit token '${token}'`]];
    }
    if (seen.has(token)) {
      return [["bits", `Duplicate bit token '${token}'`]];
    }
    seen.add(token);
  }
  return [];
}

function stringIssues(value: unknown, c: TypeConstraint): TypeIssue[] {
  if (typeof value !== "string") {
    return [["type", "Expected string"]];
  }
  const errors: TypeIssue[] = [];
  if (c.length && !matchesRange(value.length, c.length)) {
    errors.push([
      "length",
      restrictionMessage(
        `String length ${value.length} does not match ${c.length}`,
        c.length_error_message,
        c.length_error_app_tag
      )
    ]);
  }
  const patterns = Array.isArray(c.patterns) ? c.patterns : [];
  for (const p of patterns) {
    if (typeof p?.pattern !== "string" || p.pattern.length === 0) {
      continue;
    }
    const matched = translateXsdRegex(p.pattern).test(value);
    const invert = p.invert_match === true;
    if ((!invert && !matched) || (invert && matched)) {
      const defaultMsg = invert
        ? `String matches forbidden pattern ${p.pattern} (invert-match)`
        : `String does not match pattern ${p.pattern}`;
      errors.push(["pattern", patternEntryViolationMessage(p, defaultMsg)]);
    }
  }
  if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
    errors.push(["enum", `Value '${value}' is not in enum`]);
  }
  return errors;
}

export class TypeSystem {
  /**
   * Every restriction violation for this value.
   * Strings report length, then each failing pattern, then enum.
   * Other types still return at most one issue (a range miss does not also
   * report fraction-digits; a binary length miss does not also report pattern).
   */
  issues(value: unknown, typeName: string, constraint?: TypeConstraint): TypeIssue[] {
    const c = constraint ?? new TypeConstraint();
    const normalizedType = typeName.trim();

    if (normalizedType === YangTokenType.UNION) {
      for (const member of c.types ?? []) {
        const memberName = typeof member.name === "string" ? member.name : YangTokenType.STRING_KW;
        if (this.issues(value, memberName, new TypeConstraint(member as TypeConstraintInput)).length === 0) {
          return [];
        }
      }
      return [["union", "Value does not match any union member type"]];
    }

    if (normalizedType === YangTokenType.ENUMERATION) {
      if (typeof value !== "string") {
        return [["enum", "Expected enumeration value (string)"]];
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [["enum", `Value '${value}' is not in enum`]];
      }
      return [];
    }

    if (normalizedType === YangTokenType.STRING_KW) {
      return stringIssues(value, c);
    }

    if (normalizedType === YangTokenType.BOOLEAN) {
      if (typeof value === "boolean") {
        return [];
      }
      if (value === YangTokenType.TRUE || value === YangTokenType.FALSE) {
        return [];
      }
      return [["type", "Expected boolean"]];
    }

    if (normalizedType === YangTokenType.EMPTY) {
      if (value === null) {
        return [];
      }
      return [["type", "Expected empty (null)"]];
    }

    if (normalizedType in YANG_INTEGER_BOUNDS) {
      return validateIntegerBuiltin(normalizedType, value, c.range, {
        error_message: c.range_error_message,
        error_app_tag: c.range_error_app_tag
      });
    }

    if (normalizedType === YangTokenType.BINARY) {
      return validateBinary(value, c.length, {
        error_message: c.length_error_message,
        error_app_tag: c.length_error_app_tag
      });
    }

    if (normalizedType === YangTokenType.BITS) {
      return validateBits(value, c.bits ?? []);
    }

    if (normalizedType === YangTokenType.DECIMAL64 || normalizedType === "number") {
      if (typeof value === "string") {
        return [["type", "Expected number"]];
      }
      if (value instanceof ExactDecimal) {
        const text = value.text.trim();
        const n = Number(text);
        if (!Number.isFinite(n)) {
          return [["type", "Expected number"]];
        }
        if (c.range && !matchesRange(n, c.range)) {
          return [["range", restrictionMessage(`Number ${n} does not match ${c.range}`, c.range_error_message, c.range_error_app_tag)]];
        }
        if (typeof c.fraction_digits === "number" && text.includes(".")) {
          const decimals = text.split(".")[1]?.length ?? 0;
          if (decimals > c.fraction_digits) {
            return [["fraction-digits", `Too many fraction digits (${decimals} > ${c.fraction_digits})`]];
          }
        }
        return [];
      }
      const n = decimalLike(value);
      if (n === null) {
        return [["type", "Expected number"]];
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [["range", restrictionMessage(`Number ${n} does not match ${c.range}`, c.range_error_message, c.range_error_app_tag)]];
      }
      if (typeof c.fraction_digits === "number") {
        const decimals = `${n}`.split(".")[1]?.length ?? 0;
        if (decimals > c.fraction_digits) {
          return [["fraction-digits", `Too many fraction digits (${decimals} > ${c.fraction_digits})`]];
        }
      }
      return [];
    }

    if (normalizedType === YangTokenType.INT64 || normalizedType === "integer") {
      if (typeof value === "string") {
        return [["type", "Expected integer, got string"]];
      }
      const n = integerLike(value);
      if (n === null) {
        return [["type", "Expected integer"]];
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [["range", restrictionMessage(`Integer ${n} does not match ${c.range}`, c.range_error_message, c.range_error_app_tag)]];
      }
      return [];
    }

    // Unknown typedef names without a resolver: accept strings only (baseline).
    if (typeof value === "string") {
      return [];
    }
    return [["type", `Unsupported type '${normalizedType}'`]];
  }

  /**
   * Public tuple kept for `@exergy-connect/xyang/types`.
   * Thin wrapper over {@link issues}: valid, or invalid with the first message.
   * Validation that must report every issue calls {@link issues}.
   */
  validate(value: unknown, typeName: string, constraint?: TypeConstraint): [boolean, string | null] {
    const found = this.issues(value, typeName, constraint);
    if (found.length === 0) {
      return [true, null];
    }
    return [false, found[0][1]];
  }
}
