import { YangTokenType } from "./parser/parser-context";

export type TypeConstraintInput = {
  pattern?: string;
  pattern_error_message?: string;
  pattern_error_app_tag?: string;
  length?: string;
  range?: string;
  fraction_digits?: number;
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: Array<Record<string, unknown>>;
};

export class TypeConstraint {
  pattern?: string;
  pattern_error_message?: string;
  pattern_error_app_tag?: string;
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

function patternConstraintViolationMessage(c: TypeConstraint, defaultMsg: string): string {
  const msg =
    typeof c.pattern_error_message === "string" && c.pattern_error_message.trim().length > 0
      ? c.pattern_error_message
      : defaultMsg;
  const tag = typeof c.pattern_error_app_tag === "string" ? c.pattern_error_app_tag.trim() : "";
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

/** @internal Parse JSON integer scalars for built-in numeric type checks. */
export function integerLike(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+$/.test(value)) {
    return Number.parseInt(value, 10);
  }
  return null;
}

function decimalLike(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return null;
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
      if (c.pattern && !new RegExp(`^(?:${c.pattern})$`).test(value)) {
        return [
          false,
          patternConstraintViolationMessage(c, `String does not match pattern ${c.pattern}`)
        ];
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

    if (normalizedType === YangTokenType.INT32) {
      const n = integerLike(value);
      if (n === null || n < -2147483648 || n > 2147483647) {
        return [false, "Expected int32"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.UINT8) {
      const n = integerLike(value);
      if (n === null || n < 0 || n > 255) {
        return [false, "Expected uint8"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.UINT64) {
      const n = integerLike(value);
      if (n === null || n < 0) {
        return [false, "Expected uint64"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }

    if (normalizedType === YangTokenType.BINARY) {
      return validateBinary(value, c.length);
    }

    if (normalizedType === YangTokenType.BITS) {
      return validateBits(value, c.bits ?? []);
    }

    if (normalizedType === YangTokenType.DECIMAL64 || normalizedType === "number") {
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
      const n = integerLike(value);
      if (n === null) {
        return [false, "Expected integer"]; 
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }

    // Treat unknown/custom type names as string-compatible in this baseline implementation.
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return [true, null];
    }
    return [false, `Unsupported type '${normalizedType}'`];
  }
}
