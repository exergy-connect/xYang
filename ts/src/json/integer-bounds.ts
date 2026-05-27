import { YangTokenType } from "../parser/parser-context";

/** Canonical inclusive bounds for YANG integer built-ins (RFC 7950 §4.2.4). */
export const YANG_INTEGER_BOUNDS: Readonly<Record<string, readonly [number, number]>> = {
  int8: [-128, 127],
  int16: [-32768, 32767],
  int32: [-2147483648, 2147483647],
  int64: [-9223372036854775808, 9223372036854775807],
  uint8: [0, 255],
  uint16: [0, 65535],
  uint32: [0, 4294967295],
  // JSON numbers are IEEE doubles; uint64 max is representable exactly.
  uint64: [0, 18446744073709551615]
};

export const YANG_INTEGER_BUILTIN_NAMES = new Set(Object.keys(YANG_INTEGER_BOUNDS));

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
  if (rangeStr) {
    const { lo, hi } = parseRange(rangeStr);
    const out: { minimum?: number; maximum?: number } = {};
    if (lo !== undefined) {
      out.minimum = lo;
    }
    if (hi !== undefined) {
      out.maximum = hi;
    }
    return out;
  }
  return { minimum: bounds[0], maximum: bounds[1] };
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
  const order =
    lo !== undefined && lo < 0
      ? (["int8", "int16", "int32", "int64"] as const)
      : (["uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64"] as const);
  const effectiveLo = lo ?? YANG_INTEGER_BOUNDS[order[0]][0];
  const effectiveHi = hi ?? YANG_INTEGER_BOUNDS[order[order.length - 1]][1];
  for (const name of order) {
    const [blo, bhi] = YANG_INTEGER_BOUNDS[name];
    if (effectiveLo >= blo && effectiveHi <= bhi) {
      return name;
    }
  }
  return YangTokenType.INT64;
}

/** Infer YANG integer built-in and optional ``range`` from JSON Schema bounds. */
export function yangIntegerFromJsonBounds(
  minVal: unknown,
  maxVal: unknown
): { name: string; range?: string } {
  const lo = coerceInt(minVal);
  const hi = coerceInt(maxVal);

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
