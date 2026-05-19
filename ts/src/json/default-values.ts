const YANG_INT_TYPES = new Set([
  "int8",
  "int16",
  "int32",
  "int64",
  "uint8",
  "uint16",
  "uint32",
  "uint64"
]);

function tryIntLiteral(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^-?\d+$/.test(trimmed)) {
      return Number.parseInt(trimmed, 10);
    }
  }
  return null;
}

function coerceDefaultValue(value: unknown, typeName: string | undefined): unknown {
  if (value === undefined || value === null || typeName === undefined) {
    return value;
  }
  if (typeName === "boolean") {
    if (value === true || value === "true") {
      return true;
    }
    if (value === false || value === "false") {
      return false;
    }
  }
  if (YANG_INT_TYPES.has(typeName)) {
    if (typeof value === "number" && Number.isInteger(value)) {
      return value;
    }
    const parsed = tryIntLiteral(value);
    if (parsed !== null) {
      return parsed;
    }
  }
  if (typeName === "decimal64" || typeName === "number") {
    if (typeof value === "number") {
      return value;
    }
    const n = Number(value);
    if (!Number.isNaN(n)) {
      return n;
    }
  }
  return value;
}

/** Map YANG AST default values to JSON Schema literal types (Python parity). */
export function jsonSchemaDefaultValue(
  defaultValue: unknown,
  options: { yangTypeName?: string | null; jsonSchemaType?: string | null } = {}
): unknown {
  if (defaultValue === undefined || defaultValue === null) {
    return defaultValue;
  }
  const { yangTypeName = null, jsonSchemaType = null } = options;
  const typeName = yangTypeName ?? jsonSchemaType;
  if (typeName === "boolean" || jsonSchemaType === "boolean") {
    if (defaultValue === true || (typeof defaultValue === "string" && defaultValue.toLowerCase() === "true")) {
      return true;
    }
    if (defaultValue === false || (typeof defaultValue === "string" && defaultValue.toLowerCase() === "false")) {
      return false;
    }
  }
  if (yangTypeName === "union") {
    const numeric = tryIntLiteral(defaultValue);
    if (numeric !== null) {
      return numeric;
    }
    return defaultValue;
  }
  let coerceType = yangTypeName ?? undefined;
  if (jsonSchemaType === "integer" && (coerceType === undefined || coerceType === "integer")) {
    coerceType = "int32";
  }
  if (jsonSchemaType === "number" && coerceType === undefined) {
    coerceType = "decimal64";
  }
  const coerced = coerceDefaultValue(defaultValue, coerceType ?? undefined);
  if (coerced !== defaultValue) {
    return coerced;
  }
  if (jsonSchemaType === "integer") {
    const numeric = tryIntLiteral(defaultValue);
    if (numeric !== null) {
      return numeric;
    }
  }
  return defaultValue;
}

/** Map JSON Schema default back to YANG AST string form (Python parity). */
export function yangDefaultFromJsonSchema(
  defaultValue: unknown,
  schemaType: string | undefined,
  yangTypeFromXyang?: string
): unknown {
  if (defaultValue === undefined) {
    return undefined;
  }
  const xyType = yangTypeFromXyang ?? schemaType;
  if (xyType === "boolean" || schemaType === "boolean") {
    if (typeof defaultValue === "boolean") {
      return defaultValue ? "true" : "false";
    }
    if (typeof defaultValue === "string") {
      return defaultValue.toLowerCase();
    }
  }
  if (schemaType === "integer" && typeof defaultValue === "number") {
    return String(Math.trunc(defaultValue));
  }
  if (typeof defaultValue === "boolean") {
    return defaultValue ? "true" : "false";
  }
  return defaultValue;
}
