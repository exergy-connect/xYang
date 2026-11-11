export const YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
} as const;

/** Keys inside the ``x-yang`` extension object (emit + parse). */
export const XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs",
  /** Actions of a container or list (RFC 7950 §7.15), keyed by action name; same shape as `rpcs`. */
  actions: "actions",
  /** `{prefix: module}` for the prefixed steps of a leafref `path`, `must` or `when` (RFC 7950 §6.4.1). */
  xpathPrefixes: "xpath-prefixes",
  /** `{key: module stub}` of the imported modules the identities of this module derive from (RFC 7950 §7.18.2). */
  imports: "imports",
  /** Identities of an `imports` stub, keyed by name. */
  identities: "identities",
  /** Extension definitions (RFC 7950 §7.19) of this module, keyed by name. */
  extension: "extension",
  /** Invocations on this node, in source order: `{name, argument?, ...}`. `name` is `prefix:ext`. */
  extensions: "extensions",
  argument: "argument",
  yinElement: "yin-element",
  reference: "reference",
  /** Nested statements of an invocation: `{extension}` or `{node, schema}`. */
  body: "body",
  /** Declared feature names. A value is `{}` or `{ "if-features": [...] }`. */
  features: "features",
  /** Absolute path of the `sx:augment-structure` that added this node. */
  augmentStructure: "augment-structure"
} as const;
