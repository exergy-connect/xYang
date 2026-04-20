import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangFile } from "../../src";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MINIMAL_YANG = join(__dirname, "../../../examples/identity_roundtrip.yang");

describe("python parity: json/test_identity_json", () => {
  it("generateJsonSchema includes identity defs and identityref metadata", () => {
    const module = parseYangFile(MINIMAL_YANG);
    const schema = generateJsonSchema(module);
    const defs = (schema.$defs ?? {}) as Record<string, unknown>;

    expect(defs.animal).toBeDefined();
    expect((defs.animal as Record<string, unknown>).enum).toBeDefined();
    expect(((defs.animal as Record<string, unknown>)["x-yang"] as Record<string, unknown>).type).toBe("identity");
    expect(defs.dog).toBeDefined();

    const data = ((schema.properties as Record<string, unknown>).data as Record<string, unknown>);
    const kind = ((data.properties as Record<string, unknown>).kind as Record<string, unknown>);
    expect(kind).toBeDefined();
    expect(((kind["x-yang"] as Record<string, unknown>).type)).toBe("identityref");
    expect(((kind["x-yang"] as Record<string, unknown>).bases)).toEqual(["animal"]);
  });

  it("parseJsonSchema round-trip restores identities and identityref leaf type", () => {
    const module = parseYangFile(MINIMAL_YANG);
    const schema = generateJsonSchema(module);
    const round = parseJsonSchema(schema);

    expect(round.identities.animal).toBeDefined();
    expect(round.identities.dog).toBeDefined();
    expect(round.identities.mammal.bases).toEqual(["animal"]);

    const data = round.findStatement("data");
    const kind = data?.findStatement("kind");
    const type = (kind?.data.type as Record<string, unknown> | undefined) ?? {};
    expect(type.name).toBe("identityref");
    expect(type.identityref_bases).toEqual(["animal"]);
  });
});
