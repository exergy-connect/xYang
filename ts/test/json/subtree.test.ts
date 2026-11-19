import { describe, expect, it } from "vitest";
import { YangParser, generateJsonSchema, parseJsonSchema } from "../../src/index";

const model = new YangParser().parseString(`module m { namespace "urn:m"; prefix m;
  typedef external-ref { type leafref { path "/m:outside/m:name"; } }
  container outside { leaf name { type string { length "2..8"; } } }
  container topology {
    must "count(nodes) > 0";
    must "/m:outside/name = 'foo'";
    list nodes { key "name"; leaf name { type string; } }
    leaf via-typedef { type external-ref; }
    leaf external { type leafref { path "/m:outside/m:name"; } }
    leaf internal { type leafref { path "/m:topology/m:nodes/m:name"; } }
    leaf conditional { when "/m:outside/m:name = 'foo'"; type string; }
    leaf literal { type string { pattern 'a$?'; } }
  }
}`);

describe("subtree schema export", () => {
  it("selects the container and filters external constraints", () => {
    const {schema, diagnostics} = generateJsonSchema(model, {path: "/m:topology"});
    const meta = schema["x-yang"] as any;
    expect(meta.must.map((m: any) => m.must)).toEqual(["count(nodes) > 0"]);
    expect(diagnostics.map(d => d.constraint)).toEqual(["must", "leafref", "leafref", "when"]);
    const props = schema.properties as any;
    expect(props.external.minLength).toBe(2);
    expect(props["via-typedef"].minLength).toBe(2);
    expect(props["via-typedef"]["x-yang"].path).toBeUndefined();
    expect(props.external["x-yang"].path).toBeUndefined();
    expect(props.conditional["x-yang"].when).toBeUndefined();
    expect(new RegExp(props.literal.pattern).test("a$")).toBe(true);
    expect(new RegExp(props.literal.pattern).test("a")).toBe(true);
    expect(props.internal["x-yang"].path).toBe("/m:topology/m:nodes/m:name");
  });
  it("rejects importing a projection as a complete module", () => {
    const { schema } = generateJsonSchema(model, {path: "/m:topology"});
    expect(() => parseJsonSchema(schema)).toThrow(/projection/);
  });
  it("supports native single-key list values", () => {
    const { schema } = generateJsonSchema(model, {path: "/m:topology", nativeJson: true});
    const nodes = (schema.properties as any).nodes;
    expect(nodes.anyOf[0].type).toBe("array");
    expect(nodes.anyOf[1].additionalProperties.required).not.toContain("name");
  });
  it("rejects unknown nodes", () => {
    expect(() => generateJsonSchema(model, {path: "/m:missing"})).toThrow(/not found/);
  });
});

it("rejects leafrefs in unions rather than silently losing their constraints", () => {
  const unionModel = new YangParser().parseString(`module u { namespace "urn:u"; prefix u;
    container top { leaf target { type string; } leaf value { type union {
      type leafref { path "../target"; } type string;
    } } }
  }`);
  expect(() => generateJsonSchema(unionModel, { path: "/u:top" })).toThrow(/union containing a leafref/);
});

it('rejects XSD regex shorthands that cannot be encoded consistently', () => {
  const module = new YangParser().parseString(String.raw`module p { namespace "urn:p"; prefix p;
    container top { leaf value { type string { pattern '\d+'; } } }
  }`);
  expect(() => generateJsonSchema(module, { path: '/p:top' })).toThrow(/XSD regex/);
});

it('preserves leafref typedef predicates in diagnostics', () => {
  const module = new YangParser().parseString(`module m { namespace "urn:m"; prefix m;
    list a { key name; leaf name { type string; } }
    typedef t { type leafref { path "/a[name = current()/../x]/name"; } }
    container top { leaf x { type string; } leaf v { type t; } }
  }`);
  expect(generateJsonSchema(module, { path: '/m:top' }).diagnostics[0].expression).toBe('/a[name = current()/../x]/name');
});

it('resolves current() predicates from the leaf context', () => {
  const module = new YangParser().parseString(`module p { namespace "urn:p"; prefix p;
    container top {
      list nodes { key name; leaf name { type string; } leaf target { type string; } }
      list links { key index; leaf index { type uint32; } leaf node { type string; }
        leaf value { type leafref { path "/top/nodes[name = current()/../node]/target"; } }
      }
    }
  }`);
  expect(generateJsonSchema(module, { path: '/p:top' }).diagnostics).toHaveLength(0);
  expect(generateJsonSchema(module, { path: '/p:top/links' }).diagnostics[0].expression)
    .toBe('/top/nodes[name = current()/../node]/target');
});

it('preserves leafref typedef predicates through native JSON', () => {
  const module = new YangParser().parseString(`module m { namespace "urn:m"; prefix m;
    list a { key name; leaf name { type string; } }
    typedef t { type leafref { path "/a[name = current()/../x]/name"; } }
    container top { leaf x { type string; } leaf v { type t; } }
  }`);
  const native = generateJsonSchema(module).schema;
  const reloaded = parseJsonSchema(native);
  expect(generateJsonSchema(reloaded, { path: '/m:top' }).diagnostics[0].expression)
    .toBe('/a[name = current()/../x]/name');
});
