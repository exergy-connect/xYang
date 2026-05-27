import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";
import { YANG_INTEGER_BOUNDS } from "../../src/json/integer-bounds";

describe("integer built-in JSON bounds round-trip", () => {
  it("uint16 uses minimum/maximum and no builtin-type", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  leaf x { type uint16; }
}
`);
    const schema = generateJsonSchema(mod);
    const prop = (schema.properties as Record<string, unknown>).x as Record<string, unknown>;
    const xy = prop["x-yang"] as Record<string, unknown>;
    expect("builtin-type" in xy).toBe(false);
    const [lo, hi] = YANG_INTEGER_BOUNDS.uint16;
    expect(prop.minimum).toBe(lo);
    expect(prop.maximum).toBe(hi);

    const mod2 = parseJsonSchema(schema);
    const leaf = mod2.findStatement("x");
    expect((leaf?.data.type as { name?: string })?.name).toBe("uint16");
    expect((leaf?.data.type as { range?: string })?.range).toBeUndefined();
  });

  it("int32 range 0..max round-trips", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  typedef t { type int32 { range "0..max"; } }
  leaf x { type t; }
}
`);
    const schema = generateJsonSchema(mod);
    const tdef = (schema.$defs as Record<string, Record<string, unknown>>).t;
    const hi = YANG_INTEGER_BOUNDS.int32[1];
    expect(tdef.minimum).toBe(0);
    expect(tdef.maximum).toBe(hi);

    const mod2 = parseJsonSchema(schema);
    const td = mod2.typedefs["t"] as { type?: { name?: string; range?: string } };
    expect(td?.type?.name).toBe("int32");
    expect(td?.type?.range).toBe("0..max");
  });
});
