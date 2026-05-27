import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";

describe("rpc input output (RFC 7950 §7.14)", () => {
  it("parses module-level rpc with input and output leaves", () => {
    const yang = `
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
    const mod = parseYangString(yang);
    const reboot = mod.findStatement("reboot");
    expect(reboot?.keyword).toBe("rpc");
    expect(reboot?.name).toBe("reboot");

    const inp = reboot?.findStatement("input");
    expect(inp?.keyword).toBe("input");
    const delay = inp?.findStatement("delay-seconds");
    expect(delay?.keyword).toBe("leaf");
    expect((delay?.data.type as { name?: string } | undefined)?.name).toBe("uint16");

    const out = reboot?.findStatement("output");
    expect(out?.keyword).toBe("output");
    const msg = out?.findStatement("status-message");
    expect(msg?.keyword).toBe("leaf");
    expect((msg?.data.type as { name?: string } | undefined)?.name).toBe("string");
  });
});
