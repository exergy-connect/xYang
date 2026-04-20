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

export function leafTypeToSchema(typeShape: Record<string, unknown>): Record<string, unknown> {
  const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;

  if (typeName === YangTokenType.STRING_KW) {
    const out: Record<string, unknown> = { type: JSON_TYPE_STRING };
    if (typeof typeShape.pattern === "string") {
      out.pattern = typeShape.pattern;
    }
    return out;
  }

  if (
    [
      YangTokenType.INT32,
      YangTokenType.INT64,
      JSON_TYPE_INTEGER,
      YangTokenType.UINT8,
      YangTokenType.UINT64
    ].includes(typeName)
  ) {
    return { type: JSON_TYPE_INTEGER };
  }

  if ([YangTokenType.DECIMAL64, JSON_TYPE_NUMBER].includes(typeName)) {
    return { type: JSON_TYPE_NUMBER };
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
      anyOf: members.map((member) => leafTypeToSchema(member as Record<string, unknown>))
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
