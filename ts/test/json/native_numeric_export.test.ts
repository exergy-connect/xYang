import { expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";
import { parseConvertArgs } from "../../src/cli/args";
const module = parseYangString(`module m { namespace "urn:m"; prefix m;
  typedef resistance { type decimal64 { fraction-digits 3; range "0..100"; } }
  leaf signed { type int64; }
  leaf unsigned { type uint64; }
  leaf ohms { type decimal64 { fraction-digits 3; range "0..100"; } default "4.32"; }
  leaf slots { type int64 { range "1..3 | 10"; } }
  leaf alias { type resistance; }
  leaf-list values { type resistance; }
  leaf mixed { type union { type int64; type boolean; } }
  leaf ref { type leafref { path "/signed"; require-instance false; } }
}`);
const names = ["signed", "unsigned", "ohms", "slots", "alias", "values", "mixed", "ref"];
it.each([false,true].flatMap((nativeJson) => names.map((name) => [nativeJson, name] as const)))(
  "native numeric schema and round trip (#226): %s %s", (nativeJson,name) => {
    const schema = generateJsonSchema(module,{nativeJson}).schema;
    const properties = schema.properties as Record<string, Record<string,unknown>>;
    const target = properties[name];
    let numeric = target;
    if (name === "values") numeric = target.items as Record<string,unknown>;
    if (name === "mixed") numeric = (target.oneOf as Record<string,unknown>[])[0];
    if (numeric.$ref) numeric = (schema.$defs as Record<string, Record<string,unknown>>).resistance;
    const decimal = ["ohms","alias","values"].includes(name);
    expect(numeric.type).toBe(nativeJson ? (decimal ? "number" : "integer") : "string");
    if (nativeJson && decimal) expect(numeric.multipleOf).toBe(0.001);
    if (nativeJson && name === "slots") expect(numeric.anyOf).toEqual([{minimum:1,maximum:3},{minimum:10,maximum:10}]);
    expect(generateJsonSchema(parseJsonSchema(schema),{nativeJson}).schema).toEqual(schema);
    expect((generateJsonSchema(module).schema.properties as Record<string, Record<string,unknown>>).signed.type).toBe("string");
  }
);
it("parses convert --native-json (#226)", () => {
  expect(parseConvertArgs(["--native-json","m.yang"]).nativeJson).toBe(true);
});
