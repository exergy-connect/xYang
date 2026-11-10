import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const validatorDir = join(dirname(fileURLToPath(import.meta.url)), "../src/validator");

describe("unused validator files (#76)", () => {
  it("does not keep path-builder.ts or validation-error.ts", () => {
    expect(existsSync(join(validatorDir, "path-builder.ts"))).toBe(false);
    expect(existsSync(join(validatorDir, "validation-error.ts"))).toBe(false);
  });
});
