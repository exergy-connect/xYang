import { YangTokenType } from "../parser/parser-context";

export const JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

export const JSON_TYPE_STRING = "string";
export const JSON_TYPE_INTEGER = "integer";
export const JSON_TYPE_NUMBER = "number";
export const JSON_TYPE_BOOLEAN = "boolean";
export const JSON_TYPE_OBJECT = "object";
export const JSON_TYPE_ARRAY = "array";
export const JSON_TYPE_NULL = "null";

export const JSON_TYPE_FREE_FORM = [
  JSON_TYPE_STRING,
  JSON_TYPE_NUMBER,
  JSON_TYPE_BOOLEAN,
  JSON_TYPE_OBJECT,
  JSON_TYPE_ARRAY,
  JSON_TYPE_NULL
] as const;

function fractionDigitsFromMultipleOf(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value >= 1) {
    return undefined;
  }
  let n = 0;
  let t = value;
  while (t < 1 && n < 18) {
    t *= 10;
    n += 1;
  }
  return t === 1 ? n : undefined;
}

export function leafTypeToSchema(typeShape: Record<string, unknown>): Record<string, unknown> {
  const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;

  if (typeName === YangTokenType.STRING_KW) {
    const out: Record<string, unknown> = { type: JSON_TYPE_STRING };
    const rawPatterns = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
    const specs = rawPatterns
      .filter((x): x is Record<string, unknown> => Boolean(x) && typeof x === "object" && !Array.isArray(x))
      .map((x) => ({
        pattern: typeof x.pattern === "string" ? x.pattern : "",
        invert_match: x.invert_match === true,
        error_message: typeof x.error_message === "string" ? x.error_message : undefined,
        error_app_tag: typeof x.error_app_tag === "string" ? x.error_app_tag : undefined
      }))
      .filter((x) => x.pattern.length > 0);
    const anchored = (p: string): string => (p.startsWith("^") && p.endsWith("$") ? p : `^${p}$`);
    if (specs.length === 1 && !specs[0].invert_match) {
      out.pattern = anchored(specs[0].pattern);
    } else if (specs.length > 0) {
      out.allOf = specs.map((spec) =>
        spec.invert_match
          ? { not: { type: JSON_TYPE_STRING, pattern: anchored(spec.pattern) } }
          : { pattern: anchored(spec.pattern) }
      );
    }
    if (specs.length > 0) {
      const entries = specs.map((spec) => ({
        pattern: spec.pattern,
        "invert-match": spec.invert_match,
        ...(spec.error_message ? { "pattern-error-message": spec.error_message } : {}),
        ...(spec.error_app_tag ? { "pattern-error-app-tag": spec.error_app_tag } : {})
      }));
      const xYang: Record<string, unknown> = { "string-patterns": entries };
      const last = entries[entries.length - 1];
      if (typeof last["pattern-error-message"] === "string") {
        xYang["pattern-error-message"] = last["pattern-error-message"];
      }
      if (typeof last["pattern-error-app-tag"] === "string") {
        xYang["pattern-error-app-tag"] = last["pattern-error-app-tag"];
      }
      out["x-yang"] = xYang;
    }
    if (typeof typeShape.length === "string") {
      const [rawMin, rawMax] = typeShape.length.split("..");
      const min = Number.parseInt((rawMin ?? "").trim(), 10);
      const maxRaw = (rawMax ?? "").trim().toLowerCase();
      const max = Number.parseInt((rawMax ?? "").trim(), 10);
      if (!Number.isNaN(min)) {
        out.minLength = min;
      }
      if (!Number.isNaN(max) && maxRaw !== "max") {
        out.maxLength = max;
      }
    }
    return out;
  }

  if (
    [
      YangTokenType.INT8,
      YangTokenType.INT16,
      YangTokenType.INT32,
      YangTokenType.INT64,
      JSON_TYPE_INTEGER,
      YangTokenType.UINT8,
      YangTokenType.UINT16,
      YangTokenType.UINT32,
      YangTokenType.UINT64
    ].includes(typeName)
  ) {
    const out: Record<string, unknown> = { type: JSON_TYPE_INTEGER };
    if (typeName === YangTokenType.UINT8) {
      out.minimum = 0;
      out.maximum = 255;
      return out;
    }
    if (typeof typeShape.range === "string") {
      const [rawMin, rawMax] = typeShape.range.split("..");
      const min = Number.parseInt((rawMin ?? "").trim(), 10);
      const maxRaw = (rawMax ?? "").trim().toLowerCase();
      const max = Number.parseInt((rawMax ?? "").trim(), 10);
      if (!Number.isNaN(min) && (rawMin ?? "").trim().toLowerCase() !== "min") {
        out.minimum = min;
      }
      if (!Number.isNaN(max) && maxRaw !== "max") {
        out.maximum = max;
      }
    }
    return out;
  }

  if ([YangTokenType.DECIMAL64, JSON_TYPE_NUMBER].includes(typeName)) {
    const out: Record<string, unknown> = { type: JSON_TYPE_NUMBER };
    if (typeof typeShape.fraction_digits === "number" && typeShape.fraction_digits > 0) {
      out.multipleOf = 10 ** -typeShape.fraction_digits;
    }
    if (typeof typeShape.range === "string") {
      const [rawMin, rawMax] = typeShape.range.split("..");
      const minRaw = (rawMin ?? "").trim();
      const maxRaw = (rawMax ?? "").trim();
      const min = Number.parseFloat(minRaw);
      const max = Number.parseFloat(maxRaw);
      if (!Number.isNaN(min) && minRaw.toLowerCase() !== "min") {
        out.minimum = min;
      }
      if (!Number.isNaN(max) && maxRaw.toLowerCase() !== "max") {
        out.maximum = max;
      }
    }
    return out;
  }

  if (typeName === YangTokenType.BOOLEAN) {
    return { type: JSON_TYPE_BOOLEAN };
  }

  if (typeName === YangTokenType.BINARY) {
    return { type: JSON_TYPE_STRING, contentEncoding: "base64" };
  }

  if (typeName === YangTokenType.EMPTY) {
    return { type: JSON_TYPE_OBJECT, maxProperties: 0 };
  }

  if (typeName === YangTokenType.ENUMERATION) {
    const enums = Array.isArray(typeShape.enums)
      ? typeShape.enums.filter((value): value is string => typeof value === "string")
      : [];
    return enums.length > 0 ? { type: JSON_TYPE_STRING, enum: enums } : { type: JSON_TYPE_STRING };
  }

  if (
    typeName === YangTokenType.LEAFREF ||
    typeName === YangTokenType.IDENTITYREF ||
    typeName === YangTokenType.INSTANCE_IDENTIFIER
  ) {
    return { type: JSON_TYPE_STRING };
  }

  if (typeName === YangTokenType.UNION) {
    const members = Array.isArray(typeShape.types) ? typeShape.types : [];
    return {
      oneOf: members.map((member) => leafTypeToSchema(member as Record<string, unknown>))
    };
  }

  return { type: JSON_TYPE_FREE_FORM };
}

export function schemaTypeToYangType(schema: Record<string, unknown>): string {
  const type = schema.type;
  if (type === JSON_TYPE_STRING) {
    return YangTokenType.STRING_KW;
  }
  if (type === JSON_TYPE_INTEGER) {
    const min = typeof schema.minimum === "number" ? schema.minimum : undefined;
    const max = typeof schema.maximum === "number" ? schema.maximum : undefined;
    if (
      min !== undefined &&
      max !== undefined &&
      Number.isInteger(min) &&
      Number.isInteger(max) &&
      min >= 0 &&
      max <= 255
    ) {
      return YangTokenType.UINT8;
    }
    return YangTokenType.INT32;
  }
  if (type === JSON_TYPE_NUMBER) {
    return YangTokenType.DECIMAL64;
  }
  if (type === JSON_TYPE_BOOLEAN) {
    return YangTokenType.BOOLEAN;
  }
  return YangTokenType.STRING_KW;
}

export function decimal64FractionDigitsFromSchema(schema: Record<string, unknown>): number | undefined {
  return fractionDigitsFromMultipleOf(schema.multipleOf);
}
