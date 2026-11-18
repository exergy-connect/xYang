import { describe, expect, it } from "vitest";
import { resolve } from "node:path";
import { YangParser, YangValidator, Normalization, generateJsonSchema, parseJsonSchema } from "../src";
import { iterInstance, projectInstance } from "../src/encoding/instance";

const model = new YangParser().parseFile(resolve("../examples/netlab/netlab.yang"));

describe("normalization API", () => {
  it("preserves inputs and interface attributes after native JSON reload", () => {
    const restored = parseJsonSchema(generateJsonSchema(model));
    const data = {
      links: [{ a: { mtu: 1400 }, mtu: 1500, b: null }],
      groups: { g: { members: ["a"] } }, nodes: { a: {}, b: {} }
    };
    const before = structuredClone(data);
    const projected = projectInstance([...iterInstance(data, restored, { nativeJson: true })], restored.name).data;
    expect(projected.links).toEqual([{ nodes: [{ node: "a", mtu: 1400 }, { node: "b" }], mtu: 1500 }]);
    expect(data).toEqual(before);
    expect(new YangValidator(restored).validateDetailed(data, { nativeJson: true }).valid).toBe(true);
  });

  it("rejects unsupported expressions even when the node is absent", () => {
    const restored = parseJsonSchema(generateJsonSchema(model));
    const links = restored.statements.find(s => s.name === "links")!;
    const rule = links.statements.find(s => s.resolved_extension_name === "normalize")!;
    rule.statements[0].statements[0].argument = "unsupported(.)";
    expect(() => new YangValidator(restored).validateDetailed({})).toThrow("unsupported function");
  });

  it("leaves an object unchanged when no keys match", () => {
    const module = new YangParser().parseFile(resolve("../tests/cases/normalization/map/m.yang"));
    const data = { inventory: [{ name: "a" }], connections: [{ label: "kept" }] };
    expect(projectInstance([...iterInstance(data, module)], module.name).data).toEqual(data);
  });


  it("constructs endpoint objects from a string after native JSON reload", () => {
    const module = new YangParser().parseFile(resolve("../tests/cases/normalization/string-map/m.yang"));
    const restored = parseJsonSchema(generateJsonSchema(module));
    const data = { inventory: [{ name: "a" }, { name: "b" }], connections: ["a-b"] };
    const original = structuredClone(data);
    const projected = projectInstance([...iterInstance(data, restored)], restored.name).data;
    expect(projected.connections).toEqual([{ members: [{ id: "a" }, { id: "b" }] }]);
    expect(data).toEqual(original);
  });


  it("exposes map normalization through the public Normalization class", () => {
    const module = new YangParser().parseFile(resolve("../tests/cases/normalization/string-map/m.yang"));
    const links = module.findStatement("connections")!;
    expect(new Normalization(module).visit(links, "a-b")).toEqual([
      { members: [{ id: "a" }, { id: "b" }] }, null
    ]);
  });

});
