/**
 * YANG identifier-ref: an identifier with an optional module prefix
 * (RFC 7950 prefix:identifier). Built once at parse time — transformers
 * must not re-split qname strings.
 */
export type YangIdentifierRef = {
  /** Import / module prefix when present; undefined for an unprefixed name. */
  prefix?: string;
  /** Local identifier. */
  name: string;
};

export function formatIdentifierRef(ref: YangIdentifierRef): string {
  return ref.prefix ? `${ref.prefix}:${ref.name}` : ref.name;
}

export function identifierRef(name: string, prefix?: string | undefined): YangIdentifierRef {
  return prefix ? { prefix, name } : { name };
}

/**
 * Convert a single opaque atom (if-feature token, JSON Schema base string,
 * RFC 7951 identityref instance value) into an identifier-ref.
 * Not for YANG token streams — those use ``consume_identifier_ref``.
 */
export function parseIdentifierRefAtom(atom: string): YangIdentifierRef {
  const idx = atom.indexOf(":");
  if (idx <= 0 || idx >= atom.length - 1) {
    return { name: atom };
  }
  return { prefix: atom.slice(0, idx), name: atom.slice(idx + 1) };
}

/**
 * Parse an absolute schema-node path (``/prefix:a/prefix:b``) into segment refs.
 * Used when a path arrives as a YANG string argument (augment, rfc8791).
 */
export function parseAbsoluteSchemaPath(path: string): YangIdentifierRef[] {
  const raw = path.replace(/^["']|["']$/g, "");
  if (!raw.startsWith("/")) {
    throw new Error(`Schema path must be absolute, got '${path}'`);
  }
  const parts = raw
    .slice(1)
    .split("/")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
  if (parts.length === 0) {
    throw new Error(`Empty schema path: '${path}'`);
  }
  return parts.map((seg) => {
    const ref = parseIdentifierRefAtom(seg);
    if (!ref.prefix) {
      throw new Error(`Invalid schema path segment '${seg}': expected 'prefix:identifier'`);
    }
    return ref;
  });
}

/** Normalize JSON/legacy string-or-object bases into identifier-refs. */
export function coerceIdentifierRef(value: unknown): YangIdentifierRef | undefined {
  if (typeof value === "string" && value.length > 0) {
    return parseIdentifierRefAtom(value);
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const o = value as { name?: unknown; prefix?: unknown };
    if (typeof o.name === "string" && o.name.length > 0) {
      return typeof o.prefix === "string" && o.prefix.length > 0
        ? { prefix: o.prefix, name: o.name }
        : { name: o.name };
    }
  }
  return undefined;
}
