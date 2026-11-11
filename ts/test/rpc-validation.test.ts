import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { beforeAll, describe, expect, it } from "vitest";
import { parseYangString, validate, YangValidator } from "../src";
import { parseValidateArgs } from "../src/cli/args";

// Validate rpc input and output instances (issue #149). Shared cases: tests/cases/operations.

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const MODULE = `
module example-topology-tools {
  yang-version 1.1;
  namespace "urn:example:topology-tools";
  prefix ett;

  typedef node-name { type string { pattern "[a-z][a-z0-9]*"; } }

  container topology {
    list node { key name; leaf name { type node-name; } }
  }

  rpc add-link {
    input {
      leaf source { type node-name; mandatory true; }
      leaf target {
        type node-name;
        mandatory true;
        must ". != ../source" { error-message "A link cannot connect a node to itself."; }
      }
      leaf via { type leafref { path "/topology/node/name"; } }
    }
    output { leaf link-id { type string; mandatory true; } }
  }
}
`;

const SELF_LINK = { "example-topology-tools:input": { source: "r1", target: "r1" } };
const OTHER_LINK = { "example-topology-tools:input": { source: "r1", target: "r2" } };
const pairs = (errors: Array<{ path: string; code: string }>) => errors.map((e) => [e.path, e.code]);

describe("rpc input and output", () => {
  const module = parseYangString(MODULE);

  it("without rpc the wrapper is an unknown field (the old behavior)", () => {
    expect(pairs(validate(module, SELF_LINK).errors)).toEqual([["/example-topology-tools:input", "unknown-field"]]);
  });

  it("a self link fails must with the error message", () => {
    const result = validate(module, SELF_LINK, { rpc: "add-link" });
    expect(result.valid).toBe(false);
    expect(result.errors.map((e) => [e.path, e.code, e.message])).toEqual([
      ["/example-topology-tools:input/target", "must", "A link cannot connect a node to itself."]
    ]);
    expect(validate(module, OTHER_LINK, { rpc: "add-link", direction: "input" }).valid).toBe(true);
  });

  it("takes bare parameters with nativeJson", () => {
    const result = validate(module, { source: "r1", target: "r1" }, { rpc: "add-link", nativeJson: true });
    expect(pairs(result.errors)).toEqual([["/target", "must"]]);
  });

  it("validates the output", () => {
    expect(validate(module, { "example-topology-tools:output": { "link-id": "l1" } }, { rpc: "add-link", direction: "output" }).valid).toBe(true);
    const bad = validate(module, { "example-topology-tools:output": {} }, { rpc: "add-link", direction: "output" });
    expect(pairs(bad.errors)).toEqual([["/example-topology-tools:output/link-id", "mandatory"]]);
  });

  it("joins the context to the operation node", () => {
    const data = { "example-topology-tools:input": { source: "r1", target: "r2", via: "r3" } };
    const context = { "example-topology-tools:topology": { node: [{ name: "r3" }] } };
    expect(validate(module, data, { rpc: "add-link", context }).valid).toBe(true);
    expect(pairs(validate(module, data, { rpc: "add-link" }).errors)).toEqual([
      ["/example-topology-tools:input/via", "leafref"]
    ]);
  });

  it("does not mutate the module or the caller's data", () => {
    const statements = [...module.statements];
    const rpc = statements.find((s) => s.keyword === "rpc")!;
    const body = [...rpc.statements];
    const data = structuredClone(SELF_LINK);
    const context = { "example-topology-tools:topology": { node: [{ name: "r1" }] } };
    const snapshot = structuredClone(context);
    validate(module, data, { rpc: "add-link", context });
    validate(module, data);
    expect(data).toEqual(SELF_LINK);
    expect(context).toEqual(snapshot);
    expect(module.statements.length).toBe(statements.length);
    expect(module.statements.every((s, i) => s === statements[i])).toBe(true);
    expect(rpc.statements.every((s, i) => s === body[i])).toBe(true);
    expect(rpc.statements[0]!.name).toBe("input");
  });

  it("validate() text output uses the wrapper path", () => {
    const result = new YangValidator(module).validate(SELF_LINK, { rpc: "add-link" });
    expect(result.isValid).toBe(false);
    expect(result.errors[0]).toContain("A link cannot connect a node to itself.");
  });

  it.each([
    [{ rpc: "nope" }, "no rpc 'nope'"],
    [{ direction: "output" as const }, "direction applies only together with rpc or action"],
    [{ context: {} }, "context applies only together with rpc or action"],
    [{ rpc: "add-link", direction: "sideways" as never }, "direction must be 'input' or 'output'"],
    [{ rpc: "add-link", context: [] as never }, "context must be a JSON object"],
    [{ rpc: "" }, "rpc must be a non-empty rpc name"]
  ])("rejects options %j", (options, message) => {
    expect(() => validate(module, OTHER_LINK, options)).toThrow(message);
  });
});

describe("rpc CLI", () => {
  let cli = "";
  let dir = "";
  let yang = "";
  const write = (name: string, value: unknown): string => {
    const path = join(dir, name);
    writeFileSync(path, JSON.stringify(value));
    return path;
  };
  const run = (...args: string[]) => spawnSync(process.execPath, [cli, "validate", ...args], { encoding: "utf-8" });

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "xyang-rpc-"));
    yang = join(dir, "topology.yang");
    writeFileSync(yang, MODULE);
    cli = join(dir, "cli.mjs");
    await build({
      absWorkingDir: tsRoot,
      entryPoints: [resolve(tsRoot, "src/cli.ts")],
      bundle: true,
      platform: "node",
      format: "esm",
      target: "node22",
      outfile: cli,
      logLevel: "silent"
    });
  });

  it("parses --rpc, --output and --context", () => {
    const args = parseValidateArgs(["--rpc", "add-link", "--output", "--context", "ctx.json", "m.yang"]);
    expect(args).toMatchObject({ rpc: "add-link", output: true, contextFile: "ctx.json" });
    expect(parseValidateArgs(["m.yang"])).toMatchObject({ rpc: undefined, output: false, contextFile: undefined });
    expect(() => parseValidateArgs(["--output", "m.yang"])).toThrow("apply only together with --rpc");
    expect(() => parseValidateArgs(["--context", "c.json", "m.yang"])).toThrow("apply only together with --rpc");
  });

  it("defaults to input and reports the must", () => {
    const bad = run("--format", "json", "--rpc", "add-link", yang, write("self.json", SELF_LINK));
    expect(bad.status).toBe(1);
    expect(JSON.parse(bad.stdout).errors).toEqual([
      {
        path: "/example-topology-tools:input/target",
        code: "must",
        message: "A link cannot connect a node to itself."
      }
    ]);
    const good = run("--rpc", "add-link", yang, write("other.json", OTHER_LINK));
    expect(good.status).toBe(0);
    expect(good.stdout.trim()).toBe("Valid.");
  });

  it("validates the output and native JSON", () => {
    const out = run("--format", "json", "--rpc", "add-link", "--output", yang, write("out.json", { "example-topology-tools:output": {} }));
    expect(out.status).toBe(1);
    expect(JSON.parse(out.stdout).errors[0].path).toBe("/example-topology-tools:output/link-id");
    const native = run("--format", "json", "--native-json", "--rpc", "add-link", yang, write("n.json", { source: "a", target: "a" }));
    expect(JSON.parse(native.stdout).errors[0].path).toBe("/target");
  });

  it("reads --context", () => {
    const data = write("via.json", { "example-topology-tools:input": { source: "r1", target: "r2", via: "r3" } });
    const context = write("ctx.json", { "example-topology-tools:topology": { node: [{ name: "r3" }] } });
    expect(run("--rpc", "add-link", "--context", context, yang, data).status).toBe(0);
    expect(run("--rpc", "add-link", yang, data).status).toBe(1);
  });

  it.each([[["--rpc", "nope"]], [["--output"]], [["--context", "ctx.json"]]])("usage error %j exits 2", (extra) => {
    const args = extra.map((item) => (item === "ctx.json" ? write("ctx.json", {}) : item));
    const proc = run(...args, yang, write("in.json", OTHER_LINK));
    expect(proc.status).toBe(2);
    expect(proc.stdout).toBe("");
    expect(proc.stderr.length).toBeGreaterThan(0);
  });

  it("a missing context file exits 2", () => {
    expect(run("--rpc", "add-link", "--context", join(dir, "missing.json"), yang, write("in.json", OTHER_LINK)).status).toBe(2);
  });
});

const ACTION_MODULE = `
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;

  container interfaces {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type uint16; }
      action reset {
        input {
          leaf delay {
            type uint16;
            must ". < ../../ex:mtu" { error-message "delay must be below the interface mtu."; }
          }
        }
        output { leaf ok { type boolean; mandatory true; } }
      }
    }
  }
}
`;

const SERVER = { "ex:interfaces": { interface: [{ name: "eth0", mtu: 1500 }, { name: "eth1", mtu: 9000 }] } };
const ETH0 = "/ex:interfaces/interface=eth0/reset";

describe("action input and output with a validated context", () => {
  const module = parseYangString(ACTION_MODULE);

  it("must reads the selected parent entry", () => {
    const data = { "ex:input": { delay: 1600 } };
    expect(validate(module, data, { action: ETH0, context: SERVER }).errors.map((e) => [e.path, e.code, e.message])).toEqual([
      ["/ex:input/delay", "must", "delay must be below the interface mtu."]
    ]);
    expect(validate(module, data, { action: "/ex:interfaces/interface=eth1/reset", context: SERVER }).valid).toBe(true);
  });

  it("validates the output", () => {
    const result = validate(module, { "ex:output": {} }, { action: ETH0, direction: "output", context: SERVER });
    expect(pairs(result.errors)).toEqual([["/ex:output/ok", "mandatory"]]);
  });

  it("reports a parent missing from the context on the context", () => {
    const result = validate(module, { "ex:input": {} }, { action: "/ex:interfaces/interface=eth9/reset", context: SERVER });
    expect(result.errors.map((e) => [e.document, e.path, e.code])).toEqual([["context", "", "action-parent"]]);
  });

  it.each([
    [{ action: ETH0 }, "action needs context"],
    [{ action: ETH0, rpc: "x", context: {} }, "mutually exclusive"],
    [{ action: "/ex:interfaces/interface/reset", context: {} }, "needs its 1 key value"],
    [{ action: "/ex:interfaces/interface=eth0/nope", context: {} }, "has no action 'ex:nope'"],
    [{ action: "interfaces/interface=eth0/reset", context: {} }, "data resource identifier"]
  ])("rejects %j", (options, message) => {
    expect(() => validate(module, { "ex:input": {} }, options)).toThrow(message);
  });

  it("reports an invalid context before the operation", () => {
    const bad = { "ex:interfaces": { interface: [{ name: "eth0", mtu: "big" }] } };
    const result = validate(module, { "ex:input": { delay: 99999 } }, { action: ETH0, context: bad });
    expect(result.errors.map((e) => [e.document, e.path, e.code])).toEqual([["context", "/ex:interfaces/interface/0/mtu", "type"]]);
    const text = new YangValidator(module).validate({ "ex:input": {} }, { action: ETH0, context: bad });
    expect(text.isValid).toBe(false);
    expect(text.errors[0]).toMatch(/^context /);
  });

  it("does not mutate the module or the context", () => {
    const server = structuredClone(SERVER);
    const iface = module.findStatement("interfaces")!.statements[0]!;
    const before = [...iface.statements];
    validate(module, { "ex:input": { delay: 1 } }, { action: ETH0, context: server });
    expect(server).toEqual(SERVER);
    expect(iface.statements.every((s, i) => s === before[i])).toBe(true);
    expect(iface.statements.length).toBe(before.length);
  });
});

describe("action CLI", () => {
  let cli = "";
  let dir = "";
  let yang = "";
  const write = (name: string, value: unknown): string => {
    const path = join(dir, name);
    writeFileSync(path, JSON.stringify(value));
    return path;
  };
  const run = (...args: string[]) => spawnSync(process.execPath, [cli, "validate", ...args], { encoding: "utf-8" });

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "xyang-action-"));
    yang = join(dir, "ex.yang");
    writeFileSync(yang, ACTION_MODULE);
    cli = join(dir, "cli.mjs");
    await build({
      absWorkingDir: tsRoot,
      entryPoints: [resolve(tsRoot, "src/cli.ts")],
      bundle: true,
      platform: "node",
      format: "esm",
      target: "node22",
      outfile: cli,
      logLevel: "silent"
    });
  });

  it("parses --action", () => {
    expect(parseValidateArgs(["--action", ETH0, "--context", "c.json", "m.yang"])).toMatchObject({ action: ETH0, contextFile: "c.json" });
    expect(() => parseValidateArgs(["--action", ETH0, "--rpc", "x", "m.yang"])).toThrow("mutually exclusive");
  });

  it("validates an action input and output", () => {
    const ctx = write("server.json", SERVER);
    const bad = run("--format", "json", "--action", ETH0, "--context", ctx, yang, write("in.json", { "ex:input": { delay: 1600 } }));
    expect(bad.status).toBe(1);
    expect(JSON.parse(bad.stdout).errors[0].path).toBe("/ex:input/delay");
    expect(run("--action", ETH0, "--output", "--context", ctx, yang, write("out.json", { "ex:output": { ok: true } })).status).toBe(0);
  });

  it("marks context errors with the document", () => {
    const ctx = write("bad.json", { "ex:interfaces": { interface: [{ name: "eth0", mtu: "big" }] } });
    const proc = run("--format", "json", "--action", ETH0, "--context", ctx, yang, write("in.json", { "ex:input": {} }));
    expect(proc.status).toBe(1);
    expect(JSON.parse(proc.stdout).errors).toMatchObject([{ document: "context", path: "/ex:interfaces/interface/0/mtu", code: "type" }]);
  });

  it.each([[["--action", ETH0]], [["--action", "/ex:interfaces/interface/reset", "--context", "CTX"]]])(
    "usage error %j exits 2",
    (extra) => {
      const ctx = write("server.json", SERVER);
      const proc = run(...extra.map((item) => (item === "CTX" ? ctx : item)), yang, write("in.json", { "ex:input": {} }));
      expect(proc.status).toBe(2);
      expect(proc.stdout).toBe("");
    }
  );

  it("an undeclared XPath prefix exits 2", () => {
    const bad = join(dir, "m.yang");
    writeFileSync(
      bad,
      'module m { yang-version 1.1; namespace "urn:m"; prefix m; container top { leaf a { type leafref { path "/x:top/x:b"; } } leaf b { type string; } } }'
    );
    const proc = run("--format", "json", bad, write("d.json", {}));
    expect(proc.status).toBe(2);
    expect(proc.stderr).toContain("unknown prefix 'x'");
  });
});
