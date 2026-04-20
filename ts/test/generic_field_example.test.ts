import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangParser } from "../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const GENERIC_FIELD_YANG = join(__dirname, "../../examples/generic-field.yang");

describe("python parity: test_generic_field_example", () => {
  it("parses generic-field.yang with uses expansion disabled", () => {
    const parser = new YangParser({ expand_uses: false });
    const module = parser.parseFile(GENERIC_FIELD_YANG);
    expect(module.name).toBe("generic-field");
    expect(module.namespace).toBe("urn:xyang:example:generic-field");
  });

  it("parses generic-field.yang with default expand uses", () => {
    const module = parseYangFile(GENERIC_FIELD_YANG);
    expect(module.name).toBe("generic-field");
    expect(module.namespace).toBe("urn:xyang:example:generic-field");
  });
});
