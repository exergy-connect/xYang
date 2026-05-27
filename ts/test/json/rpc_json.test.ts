import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";
import { XYANG_KEYS } from "../../src/json/schema-keys";
import { YangTokenType } from "../../src/parser/parser-context";

const RPC_YANG = `
module example-rpc {
  yang-version 1.1;
  namespace "urn:example:rpc";
  prefix erpc;

  rpc reboot {
    input {
      leaf delay-seconds {
        type uint16;
      }
    }
    output {
      leaf status-message {
        type string;
      }
    }
  }
}
`;

describe("python parity: json/test_rpc_json", () => {
  it("emits x-yang.rpcs and round-trips rpc input/output", () => {
    const mod = parseYangString(RPC_YANG);
    const schema = generateJsonSchema(mod);
    const rootXy = (schema["x-yang"] ?? {}) as Record<string, unknown>;
    const rpcs = rootXy[XYANG_KEYS.rpcs] as Record<string, unknown>;
    expect(rpcs.reboot).toBeDefined();

    const reboot = rpcs.reboot as Record<string, unknown>;
    expect((reboot["x-yang"] as Record<string, unknown>).type).toBe(YangTokenType.RPC);

    const delay = ((reboot.input as Record<string, unknown>).properties as Record<string, unknown>)[
      "delay-seconds"
    ] as Record<string, unknown>;
    expect((delay["x-yang"] as Record<string, unknown>).type).toBe(YangTokenType.LEAF);
    expect("builtin-type" in (delay["x-yang"] as Record<string, unknown>)).toBe(false);
    expect(delay.type).toBe("integer");
    expect(delay.minimum).toBe(0);
    expect(delay.maximum).toBe(65535);

    const msg = ((reboot.output as Record<string, unknown>).properties as Record<string, unknown>)[
      "status-message"
    ] as Record<string, unknown>;
    expect((msg["x-yang"] as Record<string, unknown>).type).toBe(YangTokenType.LEAF);
    expect(msg.type).toBe("string");

    const mod2 = parseJsonSchema(schema);
    const reboot2 = mod2.findStatement("reboot");
    expect(reboot2?.keyword).toBe(YangTokenType.RPC);
    expect(reboot2?.name).toBe("reboot");

    const inp = reboot2?.findStatement("input");
    expect(inp?.keyword).toBe(YangTokenType.INPUT);
    const delayLeaf = inp?.findStatement("delay-seconds");
    expect((delayLeaf?.data.type as { name?: string } | undefined)?.name).toBe("uint16");

    const out = reboot2?.findStatement("output");
    expect(out?.keyword).toBe(YangTokenType.OUTPUT);
    const msgLeaf = out?.findStatement("status-message");
    expect((msgLeaf?.data.type as { name?: string } | undefined)?.name).toBe("string");
  });
});
