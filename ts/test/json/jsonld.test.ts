import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { generateJsonldContext, generateJsonldVocab, generateJsonSchema, parseJsonSchema, parseYangFile, parseYangString } from "../../src";
import { parseConvertArgs } from "../../src/cli/args";
const example = resolve(__dirname,"../../../examples/jsonld");
const module = parseYangFile(resolve(example,"catalog.yang"));
it.each(["context","vocab"])("JSON-LD example and native round trip (#229): %s", (kind) => {
  const build = kind === "context" ? generateJsonldContext : generateJsonldVocab;
  const original = generateJsonSchema(module);
  const expected = JSON.parse(readFileSync(resolve(example,`catalog.${kind}.jsonld`),"utf8"));
  expect(build(module)).toEqual(expected);
  expect(build(parseJsonSchema(original))).toEqual(expected);
  expect(generateJsonSchema(module)).toEqual(original);
});
it.each([["urn:m","urn:m#"],["urn:m:","urn:m:"],["https://example.invalid/m#","https://example.invalid/m#"],["https://example.invalid/m/","https://example.invalid/m/"]])("joins namespace IRIs (#229): %s", (namespace,base) => {
  const m = parseYangString(`module m { namespace "${namespace}"; prefix m; leaf name { type string; } }`);
  expect((generateJsonldContext(m)["@context"] as Record<string,unknown>).name).toEqual({"@id":base+"name"});
});
it("honors the vendor extension convention (#229)", () => {
  const m = parseYangString(`module m { namespace "urn:m"; prefix m;
    extension schema-org-property { argument name; } extension schema-org-class { argument name; }
    extension wikidata { argument id; } extension unit-code { argument code; }
    leaf url { type string; m:schema-org-property "url"; m:schema-org-class "URL"; m:wikidata "Q1"; m:unit-code "C62"; }
  }`);
  expect((generateJsonldContext(m)["@context"] as Record<string,unknown>).url).toEqual({"@id":"https://schema.org/url","@type":"@id"});
  expect((generateJsonldVocab(m)["@graph"] as unknown[])[0]).toMatchObject({"rdfs:range":{"@id":"https://schema.org/URL"},"skos:closeMatch":[{"@id":"http://www.wikidata.org/entity/Q1"}],"schema:unitCode":"C62"});
});
it("supports a subject-ID alias (#229)", () => {
  const m = parseYangString(`module xyang-jsonld { namespace "urn:jl"; prefix jl;
    extension iri { argument value; } leaf id { type string; jl:iri "@id"; } }`);
  expect((generateJsonldContext(m)["@context"] as Record<string,unknown>).id).toEqual({"@id":"@id"});
  expect(generateJsonldVocab(m)["@graph"]).toEqual([]);
});
it.each(['jl:iri "";', 'jl:iri "relative";', 'jl:iri "https://example.invalid/a"; jl:iri "https://example.invalid/b";'])("fails loudly for invalid mapping (#229): %s", (mapping) => {
  const m = parseYangString(`module xyang-jsonld { namespace "urn:jl"; prefix jl;
    extension iri { argument value; } leaf name { type string; ${mapping} } }`);
  expect(() => generateJsonldContext(m)).toThrow(/JSON-LD/);
});
it.each(["--jsonld","--jsonld-vocab"])("parses JSON-LD output mode (#229): %s", (flag) => {
  expect(parseConvertArgs([flag,"m.yang"])).toMatchObject(flag === "--jsonld" ? {jsonld:true} : {jsonldVocab:true});
});
it.each([["--jsonld","--jsonld-vocab"],["--jsonld","--native-json"]])("rejects incompatible JSON-LD options (#229): %s %s", (a,b) => {
  expect(() => parseConvertArgs([a,b,"missing.yang"])).toThrow();
});
it("does not expose grouping or choice names as data terms (#229)", () => {
  const m = parseYangString(`module m { namespace "urn:m"; prefix m;
    grouping named { leaf name { type string; } }
    container top { uses named; choice pick { leaf x { type string; } leaf y { type string; } } } }`);
  const context = generateJsonldContext(m)["@context"] as Record<string,Record<string,unknown>>;
  expect(Object.keys(context.top["@context"] as object)).toEqual(["name","x","y"]);
});
it("merges vocabulary metadata for repeated IRIs (#229)", () => {
  const m = parseYangString(`module xyang-jsonld { namespace "urn:jl"; prefix jl;
    extension iri { argument value; }
    leaf a { type string; description "First"; jl:iri "schema:name"; }
    leaf b { type string; description "Second"; jl:iri "schema:name"; } }`);
  expect(generateJsonldVocab(m)["@graph"]).toEqual([{"@id":"https://schema.org/name","@type":"rdf:Property","rdfs:label":["a","b"],"rdfs:comment":["First","Second"]}]);
});
