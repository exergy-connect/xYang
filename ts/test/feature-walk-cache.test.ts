import { expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangValidator } from "../src";

it("refreshes feature guards on a restored JSON schema between walks (#263)", () => {
  const source = parseYangString(`module m {
    yang-version 1.1; namespace "urn:m"; prefix m; feature f;
    list item { key id; leaf id { type string; }
      leaf guarded { if-feature f; type string; }
    }
  }`);
  const module = parseJsonSchema(generateJsonSchema(source).schema);
  const validator = new YangValidator(module, { enabledFeaturesByModule: { m: new Set<string>() } });
  const data = { item: [{ id: "a", guarded: "x" }, { id: "b", guarded: "y" }] };
  expect(validator.validateDetailed(data).errors.map((error) => error.code)).toEqual(["if-feature", "if-feature"]);
  const list = module.findStatement("item")!;
  const leaf = list.statements.find((stmt) => stmt.name === "guarded")!;
  leaf.if_features = ["not f"];
  expect(validator.validateDetailed(data).valid).toBe(true);
});
