import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";
import { iterInstance, type InstanceNode } from "../src/encoding/instance";

const MODULE = `
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type int64; }
    }
    leaf marker { type empty; }
  }
}
`;

const RFC = { "m:top": { interface: [{ name: "eth0", mtu: "1500" }], marker: [null] } };
const NATIVE = { top: { interface: { eth0: { mtu: 1500 } }, marker: null } };

function shape(node: InstanceNode): unknown {
  const value = node.kind === "leaf" || node.kind === "leaf-list-item" || node.kind === "anydata" ? node.value : null;
  return [node.kind, node.stmt?.name ?? null, value, node.children.map(shape)];
}

function pointers(node: InstanceNode): string[] {
  return [node.pointer, ...node.children.flatMap(pointers)];
}

function leaf(nodes: InstanceNode[], name: string): InstanceNode | undefined {
  for (const node of nodes) {
    if (node.kind === "leaf" && node.stmt?.name === name) return node;
    const found = leaf(node.children, name);
    if (found) return found;
  }
  return undefined;
}

describe("iterInstance", () => {
  it("matches the repro in both modes except for pointer", () => {
    const module = parseYangString(MODULE);
    const rfc = [...iterInstance(RFC, module, { nativeJson: false })];
    const native = [...iterInstance(NATIVE, module, { nativeJson: true })];
    expect(rfc.map(shape)).toEqual(native.map(shape));
    expect(pointers(rfc[0])).not.toEqual(pointers(native[0]));
    expect(leaf(rfc, "mtu")?.value).toBe(1500n);
    expect(leaf(native, "mtu")?.value).toBe(1500n);
    expect(leaf(rfc, "name")?.value).toBe("eth0");
    expect(leaf(native, "name")?.value).toBe("eth0");
    expect(leaf(rfc, "marker")?.value).toBeNull();
    expect(leaf(native, "marker")?.value).toBeNull();
    expect(leaf(rfc, "mtu")?.pointer).toBe("/m:top/interface/0/mtu");
    expect(leaf(native, "mtu")?.pointer).toBe("/top/interface/eth0/mtu");
  });
});
