import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseYangFile } from "../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_MODEL_YANG = join(__dirname, "../../examples/meta-model.yang");

describe("python parity: test_enum_validation", () => {
  it("parses examples/meta-model.yang with grouping uses expansion", () => {
    const module = parseYangFile(META_MODEL_YANG);
    expect(module.name).toBe("meta-model");
    expect(module.findStatement("data-model")).toBeDefined();
  });
});
