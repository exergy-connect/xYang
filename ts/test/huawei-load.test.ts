// Opt-in load of every module in a Huawei YANG directory.
// Set XYANG_HUAWEI_DIR to the directory. Prints the TypeScript load rate.
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile } from "../src";

const root = process.env.XYANG_HUAWEI_DIR;

function kind(err: unknown): string {
  const line = String(err instanceof Error ? err.message : err).trim().split("\n")[0] ?? "";
  return line.replace(/^.*?:\s*\d+:\s*/, "");
}

describe.skipIf(!root)("huawei modules (slow)", () => {
  it("loads every module and prints the load rate", () => {
    const files = readdirSync(root!).filter((name) => name.endsWith(".yang")).sort();
    expect(files.length).toBeGreaterThan(0);
    let ok = 0;
    const errors = new Map<string, number>();
    for (const name of files) {
      try {
        parseYangFile(join(root!, name), { includePath: [root!] });
        ok += 1;
      } catch (err) {
        const message = kind(err);
        errors.set(message, (errors.get(message) ?? 0) + 1);
      }
    }
    console.log(`TypeScript load rate: ${ok}/${files.length}`);
    for (const [message, count] of [...errors.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)) {
      console.log(`${count}\t${message}`);
    }
    expect(ok).toBeLessThanOrEqual(files.length);
  });
});
