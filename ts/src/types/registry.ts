/**
 * One frozen table for how a YANG built-in maps to JSON.
 * Mirrors `src/xyang/types/registry.py`.
 */
import {
  JSON_TYPE_BOOLEAN,
  JSON_TYPE_FREE_FORM,
  JSON_TYPE_INTEGER,
  JSON_TYPE_NUMBER,
  JSON_TYPE_OBJECT,
  JSON_TYPE_STRING
} from "../json/type-constants";

export const INT8 = "int8";
export const INT16 = "int16";
export const INT32 = "int32";
export const INT64 = "int64";
export const UINT8 = "uint8";
export const UINT16 = "uint16";
export const UINT32 = "uint32";
export const UINT64 = "uint64";
export const DECIMAL64 = "decimal64";
export const STRING = "string";
export const BOOLEAN = "boolean";
export const EMPTY = "empty";
export const ENUMERATION = "enumeration";
export const BITS = "bits";
export const BINARY = "binary";
export const UNION = "union";
export const LEAFREF = "leafref";
export const IDENTITYREF = "identityref";
export const INSTANCE_IDENTIFIER = "instance-identifier";

const INT64_PATTERN = "^-?[0-9]+$";
const UINT64_PATTERN = "^[0-9]+$";
const DECIMAL_PATTERN = "^-?[0-9]+(\\.[0-9]+)?$";

const INT64_MIN_TEXT = "-9223372036854775808";
const INT64_MAX_TEXT = "9223372036854775807";
const UINT64_MAX_TEXT = "18446744073709551615";

export type JsonEncoding = "number" | "string-number" | "string" | "boolean" | "empty";

export type Builtin = {
  readonly name: string;
  readonly jsonEncoding: JsonEncoding;
  readonly bounds: readonly [number, number] | null;
  readonly boundsText: readonly [string, string] | null;
  readonly pattern: string | null;
  toSchema(typeShape: Record<string, unknown>): Record<string, unknown>;
  fromSchema(fragment: Record<string, unknown>): Record<string, unknown> | null;
  checkValue(value: unknown, typeShape: Record<string, unknown> | null): string | null;
};

const table = new Map<string, Builtin>();

function define(spec: Omit<Builtin, "toSchema" | "fromSchema" | "checkValue"> & Partial<Pick<Builtin, "toSchema" | "fromSchema" | "checkValue">>): Builtin {
  const builtin: Builtin = {
    ...spec,
    toSchema(typeShape) {
      return emitSchema(builtin, typeShape);
    },
    fromSchema(fragment) {
      return readSchema(builtin, fragment);
    },
    checkValue(value, typeShape) {
      return checkBuiltin(builtin, value, typeShape);
    }
  };
  table.set(builtin.name, builtin);
  return builtin;
}

function integer(
  name: string,
  bounds: readonly [number, number],
  boundsText: readonly [string, string],
  jsonEncoding: JsonEncoding,
  pattern: string | null
): Builtin {
  return define({ name, jsonEncoding, bounds, boundsText, pattern });
}

integer(INT8, [-128, 127], ["-128", "127"], "number", null);
integer(INT16, [-32768, 32767], ["-32768", "32767"], "number", null);
integer(INT32, [-2147483648, 2147483647], ["-2147483648", "2147483647"], "number", null);
integer(
  INT64,
  [-9223372036854775808, 9223372036854775807],
  [INT64_MIN_TEXT, INT64_MAX_TEXT],
  "string-number",
  INT64_PATTERN
);
integer(UINT8, [0, 255], ["0", "255"], "number", null);
integer(UINT16, [0, 65535], ["0", "65535"], "number", null);
integer(UINT32, [0, 4294967295], ["0", "4294967295"], "number", null);
integer(UINT64, [0, 18446744073709551615], ["0", UINT64_MAX_TEXT], "string-number", UINT64_PATTERN);
define({ name: DECIMAL64, jsonEncoding: "string-number", bounds: null, boundsText: null, pattern: DECIMAL_PATTERN });
define({ name: STRING, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BOOLEAN, jsonEncoding: "boolean", bounds: null, boundsText: null, pattern: null });
define({ name: EMPTY, jsonEncoding: "empty", bounds: null, boundsText: null, pattern: null });
define({ name: ENUMERATION, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BITS, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BINARY, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: UNION, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: LEAFREF, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: IDENTITYREF, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: INSTANCE_IDENTIFIER, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });

export const REGISTRY: Readonly<Record<string, Builtin>> = Object.fromEntries(table);

export const YANG_INTEGER_BOUNDS: Readonly<Record<string, readonly [number, number]>> = Object.fromEntries(
  [...table.values()].filter((spec) => spec.bounds).map((spec) => [spec.name, spec.bounds!])
);

export const YANG_INTEGER_BUILTIN_NAMES = new Set(Object.keys(YANG_INTEGER_BOUNDS));

export const QUOTED_INTEGER_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "string-number" && spec.bounds).map((spec) => spec.name)
);

export const NUMBER_INTEGER_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "number").map((spec) => spec.name)
);

export const DECIMAL_TYPE_NAMES = new Set([DECIMAL64, JSON_TYPE_NUMBER]);

export const STRINGISH_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "string" && spec.name !== UNION).map((spec) => spec.name)
);

export function isStringNumberBuiltin(name: string): boolean {
  return REGISTRY[name]?.jsonEncoding === "string-number";
}

export function isQuotedInteger(name: string): boolean {
  const spec = REGISTRY[name];
  return spec?.jsonEncoding === "string-number" && spec.bounds != null;
}

function signedNames(): string[] {
  return [...table.values()].filter((spec) => spec.bounds != null && spec.bounds[0] < 0).map((spec) => spec.name);
}

function unsignedThenSigned(): string[] {
  const unsigned = [...table.values()]
    .filter((spec) => spec.bounds != null && spec.bounds[0] >= 0)
    .map((spec) => spec.name);
  return [...unsigned, ...signedNames()];
}

function parseRange(rangeStr: string): { lo?: number; hi?: number } {
  const parts = rangeStr.split("..");
  const out: { lo?: number; hi?: number } = {};
  const rawLo = (parts[0] ?? "").trim();
  const rawHi = (parts[1] ?? "").trim();
  if (rawLo && rawLo.toLowerCase() !== "min") {
    const lo = Number.parseInt(rawLo, 10);
    if (!Number.isNaN(lo)) {
      out.lo = lo;
    }
  }
  if (rawHi && rawHi.toLowerCase() !== "max") {
    const hi = Number.parseInt(rawHi, 10);
    if (!Number.isNaN(hi)) {
      out.hi = hi;
    }
  }
  return out;
}

export function jsonIntegerBoundsForBuiltin(
  yangType: string,
  rangeStr?: string
): { minimum?: number; maximum?: number } {
  const bounds = YANG_INTEGER_BOUNDS[yangType];
  if (!bounds) {
    return {};
  }
  if (!rangeStr) {
    return { minimum: bounds[0], maximum: bounds[1] };
  }
  const { lo, hi } = parseRange(rangeStr);
  const parts = rangeStr.split("..");
  const loS = (parts[0] ?? "").trim();
  const hiS = (parts[1] ?? "").trim();
  const out: { minimum?: number; maximum?: number } = {};
  if (loS.toLowerCase() === "min") {
    out.minimum = bounds[0];
  } else if (lo !== undefined) {
    out.minimum = lo;
  }
  if (rangeStr.includes("..") && hiS.toLowerCase() === "max") {
    out.maximum = bounds[1];
  } else if (hi !== undefined) {
    out.maximum = hi;
  }
  return out;
}

function coerceInt(value: unknown): number | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  return undefined;
}

function narrowestIntegerBuiltin(lo: number | undefined, hi: number | undefined): string {
  const order = lo !== undefined && lo < 0 ? signedNames() : unsignedThenSigned();
  const effectiveLo = lo ?? YANG_INTEGER_BOUNDS[order[0]][0];
  const effectiveHi = hi ?? YANG_INTEGER_BOUNDS[order[order.length - 1]][1];
  for (const name of order) {
    const [blo, bhi] = YANG_INTEGER_BOUNDS[name];
    if (effectiveLo >= blo && effectiveHi <= bhi) {
      return name;
    }
  }
  return INT64;
}

/** Infer YANG integer built-in and optional range from JSON Schema bounds. */
export function yangIntegerFromJsonBounds(
  minVal: unknown,
  maxVal: unknown
): { name: string; range?: string } {
  const lo = coerceInt(minVal);
  const hi = coerceInt(maxVal);

  if (lo === undefined && hi === undefined) {
    return { name: "integer" };
  }

  if (lo === 0 && hi !== undefined) {
    for (const name of signedNames()) {
      if (hi === YANG_INTEGER_BOUNDS[name][1]) {
        return { name, range: "0..max" };
      }
    }
  }

  if (lo !== undefined && hi !== undefined) {
    for (const [name, [blo, bhi]] of Object.entries(YANG_INTEGER_BOUNDS)) {
      if (lo === blo && hi === bhi) {
        return { name };
      }
    }
  }

  let range: string | undefined;
  if (lo !== undefined || hi !== undefined) {
    const minPart = lo !== undefined ? String(lo) : "min";
    const maxPart = hi !== undefined ? String(hi) : "max";
    range = `${minPart}..${maxPart}`;
  }

  const name = narrowestIntegerBuiltin(lo, hi);
  const canonical = YANG_INTEGER_BOUNDS[name];
  if (range && canonical && lo === canonical[0] && hi === canonical[1]) {
    return { name };
  }
  return range ? { name, range } : { name };
}

function stringSchema(typeShape: Record<string, unknown>): Record<string, unknown> {
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

function emitSchema(spec: Builtin, typeShape: Record<string, unknown>): Record<string, unknown> {
  if (spec.bounds && spec.jsonEncoding === "string-number") {
    const xYang: Record<string, unknown> = { type: spec.name };
    if (typeof typeShape.range === "string" && typeShape.range) {
      xYang.range = typeShape.range;
    }
    return { type: JSON_TYPE_STRING, pattern: spec.pattern, "x-yang": xYang };
  }
  if (spec.jsonEncoding === "number") {
    const out: Record<string, unknown> = { type: JSON_TYPE_INTEGER };
    const rangeStr = typeof typeShape.range === "string" ? typeShape.range : undefined;
    const { minimum, maximum } = jsonIntegerBoundsForBuiltin(spec.name, rangeStr);
    if (minimum !== undefined) {
      out.minimum = minimum;
    }
    if (maximum !== undefined) {
      out.maximum = maximum;
    }
    return out;
  }
  if (spec.name === DECIMAL64) {
    const xYang: Record<string, unknown> = { type: DECIMAL64 };
    if (typeof typeShape.fraction_digits === "number") {
      xYang["fraction-digits"] = typeShape.fraction_digits;
    }
    if (typeof typeShape.range === "string" && typeShape.range) {
      xYang.range = typeShape.range;
    }
    return { type: JSON_TYPE_STRING, pattern: spec.pattern, "x-yang": xYang };
  }
  if (spec.name === STRING) {
    return stringSchema(typeShape);
  }
  if (spec.name === BOOLEAN) {
    return { type: JSON_TYPE_BOOLEAN };
  }
  if (spec.name === BINARY) {
    return { type: JSON_TYPE_STRING, contentEncoding: "base64" };
  }
  if (spec.name === EMPTY) {
    return { type: JSON_TYPE_OBJECT, maxProperties: 0 };
  }
  if (spec.name === ENUMERATION) {
    const enums = Array.isArray(typeShape.enums)
      ? typeShape.enums.filter((value): value is string => typeof value === "string")
      : [];
    return enums.length > 0 ? { type: JSON_TYPE_STRING, enum: enums } : { type: JSON_TYPE_STRING };
  }
  if (spec.name === LEAFREF || spec.name === IDENTITYREF || spec.name === INSTANCE_IDENTIFIER) {
    return { type: JSON_TYPE_STRING };
  }
  if (spec.name === UNION) {
    const members = Array.isArray(typeShape.types) ? typeShape.types : [];
    return { oneOf: members.map((member) => leafTypeToSchema(member as Record<string, unknown>)) };
  }
  return { type: JSON_TYPE_FREE_FORM };
}

export function leafTypeToSchema(typeShape: Record<string, unknown>): Record<string, unknown> {
  const typeName = typeof typeShape.name === "string" ? typeShape.name : STRING;
  if (typeName === JSON_TYPE_NUMBER) {
    return REGISTRY[DECIMAL64].toSchema(typeShape);
  }
  const spec = REGISTRY[typeName];
  if (!spec) {
    return { type: JSON_TYPE_FREE_FORM };
  }
  return spec.toSchema(typeShape);
}

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

export function decimal64FractionDigitsFromSchema(schema: Record<string, unknown>): number | undefined {
  return fractionDigitsFromMultipleOf(schema.multipleOf);
}

export function schemaTypeToYangType(schema: Record<string, unknown>): string {
  const type = schema.type;
  if (type === JSON_TYPE_STRING) {
    return STRING;
  }
  if (type === JSON_TYPE_INTEGER) {
    return yangIntegerFromJsonBounds(schema.minimum, schema.maximum).name;
  }
  if (type === JSON_TYPE_NUMBER) {
    return DECIMAL64;
  }
  if (type === JSON_TYPE_BOOLEAN) {
    return BOOLEAN;
  }
  return STRING;
}

export function quotedNumericTypeShape(xy: Record<string, unknown>): Record<string, unknown> | null {
  const name = typeof xy.type === "string" ? xy.type : "";
  if (!isStringNumberBuiltin(name)) {
    return null;
  }
  const shape: Record<string, unknown> = { name };
  if (typeof xy.range === "string" && xy.range) {
    shape.range = xy.range;
  }
  if (name === DECIMAL64 && typeof xy["fraction-digits"] === "number") {
    shape.fraction_digits = xy["fraction-digits"];
  }
  return shape;
}

function readSchema(spec: Builtin, fragment: Record<string, unknown>): Record<string, unknown> | null {
  const xy = (fragment["x-yang"] as Record<string, unknown> | undefined) ?? fragment;
  if (spec.jsonEncoding === "string-number") {
    const named = quotedNumericTypeShape(xy);
    return named && named.name === spec.name ? named : null;
  }
  if (spec.jsonEncoding === "number" && fragment.type === JSON_TYPE_INTEGER) {
    const inferred = yangIntegerFromJsonBounds(fragment.minimum, fragment.maximum);
    if (inferred.name !== spec.name) {
      return null;
    }
    const shape: Record<string, unknown> = { name: inferred.name };
    if (inferred.range) {
      shape.range = inferred.range;
    }
    return shape;
  }
  if (spec.name === BOOLEAN && fragment.type === JSON_TYPE_BOOLEAN) {
    return { name: BOOLEAN };
  }
  if (spec.name === EMPTY && fragment.type === JSON_TYPE_OBJECT && fragment.maxProperties === 0) {
    return { name: EMPTY };
  }
  if (spec.name === DECIMAL64 && fragment.type === JSON_TYPE_NUMBER) {
    const shape: Record<string, unknown> = { name: DECIMAL64 };
    const fd = decimal64FractionDigitsFromSchema(fragment);
    if (typeof fd === "number") {
      shape.fraction_digits = fd;
    }
    return shape;
  }
  return null;
}

function checkBuiltin(spec: Builtin, value: unknown, _typeShape: Record<string, unknown> | null): string | null {
  if (spec.bounds) {
    if (typeof value === "string") {
      if (spec.jsonEncoding === "string-number") {
        return `Expected ${spec.name}`;
      }
      return "Expected integer, got string";
    }
    return null;
  }
  if (spec.name === DECIMAL64) {
    if (typeof value === "string") {
      return "Expected number";
    }
    return null;
  }
  if (spec.name === BOOLEAN) {
    if (typeof value === "boolean" || value === "true" || value === "false") {
      return null;
    }
    return "Expected boolean";
  }
  if (spec.name === EMPTY) {
    return value === null ? null : "Expected empty (null)";
  }
  if (spec.jsonEncoding === "string" && spec.name !== UNION && spec.name !== BITS) {
    return typeof value === "string" ? null : "Expected string";
  }
  return null;
}

export function registryParitySnapshot(): Record<
  string,
  { json_encoding: string; bounds: [string, string] | null; pattern: string | null }
> {
  const out: Record<string, { json_encoding: string; bounds: [string, string] | null; pattern: string | null }> = {};
  for (const spec of table.values()) {
    out[spec.name] = {
      json_encoding: spec.jsonEncoding,
      bounds: spec.boundsText ? [spec.boundsText[0], spec.boundsText[1]] : null,
      pattern: spec.pattern
    };
  }
  return out;
}
