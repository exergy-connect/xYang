import { describe, it, expect } from "vitest";
import { inferRequiredFeatures, parseYangString } from "../src/index";
const source = `module example {
 yang-version 1.1; namespace "urn:example"; prefix ex;
 feature core; feature stats { if-feature "core"; } feature unused;
 container root { if-feature "core";
   list item { key "id"; leaf id { type string; }
     choice mode { if-feature "stats"; case detailed {
       leaf count { type uint32; }
     } }
   }
   leaf unsupported { if-feature "core or unused"; type string; }
   anydata payload;
 }
}`;
describe("inferRequiredFeatures", () => {
  it("collects ancestors, choices, prerequisites and deduplicates list rows", () => {
    const module = parseYangString(source);
    expect(inferRequiredFeatures(module, {})).toEqual([]);
    expect(inferRequiredFeatures(module, { "example:root": { item: [] } })).toEqual(["example:core"]);
    expect(inferRequiredFeatures(module, { root: { item: [
      { id: "a", count: 1 }, { id: "b", count: 2 }
    ] } })).toEqual(["example:core", "example:stats"]);
    expect(inferRequiredFeatures(module, { root: { payload: { opaque: 1 } } })).toEqual(["example:core"]);
  });
  it("rejects unknown members, unsupported conditions and malformed lists", () => {
    const module = parseYangString(source);
    expect(() => inferRequiredFeatures(module, {root: {unknown: 1}})).toThrow("Unknown or ambiguous");
    expect(() => inferRequiredFeatures(module, {root: {unsupported: "x"}})).toThrow("Unsupported if-feature");
    expect(() => inferRequiredFeatures(module, {root: {item: {}}})).toThrow("List array expected");
  });
});

it("resolves imported prerequisites using module names", () => {
  const lib = parseYangString(`module lib { namespace "urn:lib"; prefix l;
    feature base; feature extra { if-feature "base"; } }`);
  const main = parseYangString(`module main { namespace "urn:main"; prefix m;
    leaf value { if-feature "other:extra"; type string; } }`);
  main.data.import_prefixes = { other: lib.data };
  expect(inferRequiredFeatures(main, { value: "x" })).toEqual(["lib:base", "lib:extra"]);
});
it.each(["missing", "not a", "(a)", "a and", "a a"])("rejects condition %s", condition => {
  const module = parseYangString(`module m { namespace "urn:m"; prefix m;
    feature a; leaf x { type string; if-feature "${condition}"; } }`);
  expect(() => inferRequiredFeatures(module, { x: "v" })).toThrow();
});
