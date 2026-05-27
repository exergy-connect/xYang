export const YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
} as const;

/** Keys inside the ``x-yang`` extension object (emit + parse). */
export const XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs"
} as const;
