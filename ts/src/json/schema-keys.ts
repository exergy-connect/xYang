export const YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
} as const;

/** Keys inside the ``x-yang`` extension object (emit + parse). */
export const XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs",
  /** `{prefix: module}` for the prefixed steps of a leafref `path`, `must` or `when` (RFC 7950 §6.4.1). */
  xpathPrefixes: "xpath-prefixes"
} as const;
