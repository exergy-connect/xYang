const warned = new Set<string>();

/** Loud, once-per-process warning for a snake_case public alias. */
export function warnDeprecatedOnce(name: string, replacement: string): void {
  if (warned.has(name)) {
    return;
  }
  warned.add(name);
  console.warn(
    `xyang: \`${name}\` is deprecated and will be removed in the next release. Use \`${replacement}\`.`
  );
}
