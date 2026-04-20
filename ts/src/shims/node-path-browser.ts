/** Minimal path helpers for the browser UMD build (parseYangString-only; no real filesystem). */

export function resolve(...parts: string[]): string {
  const joined = parts.filter((p) => p && p.length > 0).join("/");
  return joined.replace(/\/+/g, "/").replace(/^\.\//, "") || ".";
}

export function dirname(p: string): string {
  const s = p.replace(/\/+$/, "");
  if (s.length === 0) {
    return ".";
  }
  const i = s.lastIndexOf("/");
  if (i <= 0) {
    return ".";
  }
  return s.slice(0, i) || "/";
}
