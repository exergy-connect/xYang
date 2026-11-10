import { isQuotedInteger, REGISTRY, YANG_INTEGER_BOUNDS } from "./types/registry";
import { YangTokenType } from "./parser/parser-context";
import { translateXsdRegex } from "./xsd-regex";

export type TypeConstraintInput = {
  patterns?: Array<{
    pattern: string;
    invert_match?: boolean;
    error_message?: string;
    error_app_tag?: string;
  }>;
  length?: string;
  range?: string;
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
  fraction_digits?: number;
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: Array<Record<string, unknown>>;

  constructor(input: TypeConstraintInput = {}) {
    Object.assign(this, input);
  }
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
  range?: string
): [boolean, string | null] {
  const bounds = YANG_INTEGER_BOUNDS[typeName];
  if (!bounds) {
    return [false, `Unsupported integer type '${typeName}'`];
  }
  if (typeof value === "string") {
    // Quoted 64-bit integers are decoded to bigint by the instance iterator.
    // A string that reaches this check is not a JSON integer.
    return [false, REGISTRY[typeName].checkValue(value, null) ?? "Expected integer, got string"];
  }
  if (typeof value === "bigint" && isQuotedInteger(typeName)) {
    const unsigned = YANG_INTEGER_BOUNDS[typeName]?.[0] === 0;
    const lo = unsigned ? BigInt(0) : INT64_MIN;
    const hi = unsigned ? UINT64_MAX : INT64_MAX;
    if (value < lo || value > hi) {
      return [false, `Value ${value} is outside ${typeName}`];
    }
    if (range) {
      const asNumber = Number(value);
      if (!Number.isSafeInteger(asNumber) || !matchesRange(asNumber, range)) {
        if (!Number.isSafeInteger(asNumber)) {
          return [true, null];
        }
        return [false, `Integer ${value} does not match ${range}`];
      }
    }
    return [true, null];
  }
  const n = integerLike(value);
  if (n === null) {
    return [false, `Expected ${typeName}`];
  }
  if (range) {
    if (!matchesRange(n, range)) {
      return [false, `Integer ${n} does not match ${range}`];
    }
    return [true, null];
  }
  const [lo, hi] = bounds;
  if (n < lo) {
    return [false, `Value ${n} is less than minimum ${lo}`];
  }
  if (n > hi) {
    return [false, `Value ${n} exceeds maximum ${hi}`];
  }
  return [true, null];
}

function validateBinary(value: unknown, length?: string): [boolean, string | null] {
  if (typeof value !== "string") {
    return [false, "Expected base64 string"]; 
  }

  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) {
    return [false, "Expected valid base64 string"]; 
  }

  try {
    const bytes = Buffer.from(value, "base64");
    if (length && !matchesRange(bytes.length, length)) {
      return [false, `Binary length ${bytes.length} does not match ${length}`];
    }
  } catch {
    return [false, "Expected valid base64 string"];
  }

  return [true, null];
}

function validateBits(value: unknown, bits: Array<{ name: string; position: number }>): [boolean, string | null] {
  if (typeof value !== "string") {
    return [false, "Bits values must be string tokens"]; 
  }
  const allowed = new Set(bits.map((bit) => bit.name));
  if (value.trim() === "") {
    return [true, null];
  }
  const seen = new Set<string>();
  for (const token of value.trim().split(/\s+/)) {
    if (!allowed.has(token)) {
      return [false, `Unknown bit token '${token}'`];
    }
    if (seen.has(token)) {
      return [false, `Duplicate bit token '${token}'`];
    }
    seen.add(token);
  }
  return [true, null];
}

export class TypeSystem {
  validate(value: unknown, typeName: string, constraint?: TypeConstraint): [boolean, string | null] {
    const c = constraint ?? new TypeConstraint();
    const normalizedType = typeName.trim();

    if (normalizedType === YangTokenType.UNION) {
      for (const member of c.types ?? []) {
        const memberName = typeof member.name === "string" ? member.name : YangTokenType.STRING_KW;
        const [ok] = this.validate(value, memberName, new TypeConstraint(member as TypeConstraintInput));
        if (ok) {
          return [true, null];
        }
      }
      return [false, "Value does not match any union member type"];
    }

    if (normalizedType === YangTokenType.ENUMERATION) {
      if (typeof value !== "string") {
        return [false, "Expected enumeration value (string)"];
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [false, `Value '${value}' is not in enum`];
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.STRING_KW) {
      if (typeof value !== "string") {
        return [false, "Expected string"]; 
      }
      if (c.length && !matchesRange(value.length, c.length)) {
        return [false, `String length ${value.length} does not match ${c.length}`];
      }
      const patterns = Array.isArray(c.patterns) ? c.patterns : [];
      if (patterns.length > 0) {
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
            return [false, patternEntryViolationMessage(p, defaultMsg)];
          }
        }
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [false, `Value '${value}' is not in enum`];
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.BOOLEAN) {
      if (typeof value === "boolean") {
        return [true, null];
      }
      if (value === YangTokenType.TRUE || value === YangTokenType.FALSE) {
        return [true, null];
      }
      return [false, "Expected boolean"]; 
    }

    if (normalizedType === YangTokenType.EMPTY) {
      if (value === null) {
        return [true, null];
      }
      return [false, "Expected empty (null)"];
    }

    if (normalizedType in YANG_INTEGER_BOUNDS) {
      return validateIntegerBuiltin(normalizedType, value, c.range);
    }

    if (normalizedType === YangTokenType.BINARY) {
      return validateBinary(value, c.length);
    }

    if (normalizedType === YangTokenType.BITS) {
      return validateBits(value, c.bits ?? []);
    }

    if (normalizedType === YangTokenType.DECIMAL64 || normalizedType === "number") {
      if (typeof value === "string") {
        return [false, "Expected number"];
      }
      if (value instanceof ExactDecimal) {
        const text = value.text.trim();
        const n = Number(text);
        if (!Number.isFinite(n)) {
          return [false, "Expected number"];
        }
        if (c.range && !matchesRange(n, c.range)) {
          return [false, `Number ${n} does not match ${c.range}`];
        }
        if (typeof c.fraction_digits === "number" && text.includes(".")) {
          const decimals = text.split(".")[1]?.length ?? 0;
          if (decimals > c.fraction_digits) {
            return [false, `Too many fraction digits (${decimals} > ${c.fraction_digits})`];
          }
        }
        return [true, null];
      }
      const n = decimalLike(value);
      if (n === null) {
        return [false, "Expected number"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Number ${n} does not match ${c.range}`];
      }
      if (typeof c.fraction_digits === "number") {
        const decimals = `${n}`.split(".")[1]?.length ?? 0;
        if (decimals > c.fraction_digits) {
          return [false, `Too many fraction digits (${decimals} > ${c.fraction_digits})`];
        }
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.INT64 || normalizedType === "integer") {
      if (typeof value === "string") {
        return [false, "Expected integer, got string"];
      }
      const n = integerLike(value);
      if (n === null) {
        return [false, "Expected integer"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }

    // Unknown typedef names without a resolver: accept strings only (baseline).
    if (typeof value === "string") {
      return [true, null];
    }
    return [false, `Unsupported type '${normalizedType}'`];
  }
}
