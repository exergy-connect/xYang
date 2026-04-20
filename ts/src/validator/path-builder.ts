export function buildPath(parts: string[]): string {
  return `/${parts.filter(Boolean).join("/")}`;
}
