import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEST_ROOT = __dirname;

function collectTestFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...collectTestFiles(full));
      continue;
    }
    if (entry.endsWith(".test.ts") && entry !== "strictness.test.ts") {
      out.push(full);
    }
  }
  return out;
}

describe("strictness policy", () => {
  it("has no skipped/todo/focused tests", () => {
    const files = collectTestFiles(TEST_ROOT);
    const violations: string[] = [];

    for (const filePath of files) {
      const src = readFileSync(filePath, "utf-8");
      const checks: Array<[RegExp, string]> = [
        [/\b(?:it|test|describe)\s*\.\s*skip\s*\(/g, "skip"],
        [/\b(?:it|test)\s*\.\s*todo\s*\(/g, "todo"],
        [/\b(?:it|test|describe)\s*\.\s*only\s*\(/g, "only"]
      ];

      for (const [pattern, label] of checks) {
        if (pattern.test(src)) {
          violations.push(`${label}: ${filePath}`);
        }
      }
    }

    expect(violations, violations.join("\n")).toEqual([]);
  });
});
