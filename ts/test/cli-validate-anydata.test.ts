import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

const HOST_YANG = `
module example-push-host {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:host";
  prefix ph;
  container notification {
    anydata payload;
  }
}
`;

const PAYLOAD_YANG = `
module example-rfc8343-shape {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:8343-shape";
  prefix ifshape;
  container interfaces-state {
    list interface {
      key name;
      leaf name { type string; }
      leaf in-octets { type uint64; }
    }
  }
}
`;

describe("xyang-ts validate --anydata-*", () => {
  it("validates anydata subtree via CLI flags", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-cli-"));
    const hostPath = join(dir, "host.yang");
    const payloadPath = join(dir, "payload.yang");
    const dataPath = join(dir, "data.json");
    writeFileSync(hostPath, HOST_YANG);
    writeFileSync(payloadPath, PAYLOAD_YANG);
    writeFileSync(
      dataPath,
      JSON.stringify({
        notification: {
          payload: {
            "example-rfc8343-shape:interfaces-state": {
              interface: [{ name: "eth0", "in-octets": 42 }]
            }
          }
        }
      })
    );

    const cli = join(process.cwd(), "dist", "cli.js");
    const result = spawnSync(
      process.execPath,
      [
        cli,
        "validate",
        "--anydata-validation",
        "complete",
        "--anydata-module",
        payloadPath,
        hostPath,
        dataPath
      ],
      { encoding: "utf-8" }
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("Valid.");
  });
});
