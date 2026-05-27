export const YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
} as const;

/** Keys inside the ``x-yang`` extension object (emit + parse). */
export const XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs",
  /** Built-in YANG type on a leaf when JSON Schema ``type`` is coarser (e.g. ``uint16``). */
  builtinType: "builtin-type"
} as const;

/** YANG integer built-in names preserved via {@link XYANG_KEYS.builtinType}. */
export const YANG_INTEGER_BUILTINS = new Set([
  "int8",
  "int16",
  "int32",
  "int64",
  "uint8",
  "uint16",
  "uint32",
  "uint64"
]);
