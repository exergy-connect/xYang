/** Stubs for the browser UMD build; file-backed parsing is unsupported in the browser. */

export function existsSync(): boolean {
  throw new Error("parseYangFile() and YANG import resolution require Node.js (filesystem). Use parseYangString() in the browser.");
}

export function readFileSync(): string {
  throw new Error("parseYangFile() requires Node.js (filesystem). Use parseYangString() in the browser.");
}

export function readdirSync(): string[] {
  throw new Error("parseYangFile() requires Node.js (filesystem). Use parseYangString() in the browser.");
}
