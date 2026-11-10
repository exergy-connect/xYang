import { describe, expect, it } from "vitest";
import { parseValidateArgs } from "../src/cli/args";
import { normalizeRfc7951InstanceRoot } from "../src/cli/load-anydata-modules";

describe("cli validate args", () => {
  it("parses anydata flags and positional args", () => {
    const args = parseValidateArgs([
      "--include-path",
      "mods",
      "--anydata-validation",
      "complete",
      "--anydata-module",
      "ietf-yang-push.yang",
      "--anydata-module",
      "ietf-alarms.yang",
      "host.yang",
      "data.json"
    ]);

    expect(args.includePaths[0]).toMatch(/mods$/);
    expect(args.anydataValidation).toBe("complete");
    expect(args.anydataModulePaths).toHaveLength(2);
    expect(args.positional).toEqual(["host.yang", "data.json"]);
  });

  it("defaults anydata-validation to off", () => {
    const args = parseValidateArgs(["host.yang"]);
    expect(args.anydataValidation).toBe("off");
    expect(args.anydataModulePaths).toEqual([]);
    expect(args.format).toBe("text");
    expect(args.features).toBeNull();
  });

  it("parses format and features", () => {
    const args = parseValidateArgs([
      "--format",
      "json",
      "--features",
      '{"m":["f1"]}',
      "host.yang",
      "-"
    ]);
    expect(args.format).toBe("json");
    expect(args.features).toEqual({ m: ["f1"] });
    expect(args.positional).toEqual(["host.yang", "-"]);
  });

  it("accepts features null and rejects a non-object", () => {
    expect(parseValidateArgs(["--features", "null", "host.yang"]).features).toBeNull();
    expect(() => parseValidateArgs(["--features", "[1]", "host.yang"])).toThrow(/--features/);
    expect(() => parseValidateArgs(["--format", "yaml", "host.yang"])).toThrow(/--format/);
  });

  it("rejects invalid anydata-validation mode", () => {
    expect(() =>
      parseValidateArgs(["--anydata-validation", "strict", "host.yang"])
    ).toThrow("--anydata-validation must be off, complete, or candidate");
  });
});

describe("normalizeRfc7951InstanceRoot", () => {
  it("unwraps module-qualified top-level key", () => {
    const out = normalizeRfc7951InstanceRoot(
      { "ietf-yp-notification:envelope": { "event-time": "x" } },
      "ietf-yp-notification"
    );
    expect(out).toEqual({ envelope: { "event-time": "x" } });
  });

  it("leaves unqualified data unchanged", () => {
    const data = { envelope: { "event-time": "x" } };
    expect(normalizeRfc7951InstanceRoot(data, "ietf-yp-notification")).toEqual(data);
  });
});
