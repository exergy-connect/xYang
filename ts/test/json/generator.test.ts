import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString, YangParser } from "../../src";

describe("python parity: json/test_generator", () => {
  it("emits typedefs under $defs and uses $ref on leafs", () => {
    const module = parseYangString(`
module v {
  yang-version 1.1;
  namespace "urn:v";
  prefix v;

  typedef version-string {
    type string {
      pattern "\\\\d+";
    }
  }

  container data-model {
    leaf version {
      type version-string;
    }
  }
}
`);

    const schema = generateJsonSchema(module);
    const defs = schema.$defs as Record<string, unknown>;
    expect(defs).toBeDefined();
    expect((defs["version-string"] as Record<string, unknown>)["x-yang"]).toEqual({
      "string-patterns": [{ pattern: "\\\\d+", "invert-match": false }]
    });

    const leaf = (((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
      .properties as Record<string, unknown>)["version"] as Record<string, unknown>;
    expect(leaf.$ref).toBe("#/$defs/version-string");

    const round = parseJsonSchema(schema);
    expect((round.typedefs["version-string"] as { type?: { name?: string } })?.type?.name).toBe("string");
    const dm = round.findStatement("data-model");
    const version = dm?.findStatement("version");
    expect((version?.data.type as Record<string, unknown> | undefined)?.name).toBe("version-string");
  });

  it("round-trips if-features metadata on leaf", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature f;

  container data-model {
    leaf x {
      if-feature "f";
      type string;
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const leaf = (((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
      .properties as Record<string, unknown>)["x"] as Record<string, unknown>;
    expect((leaf["x-yang"] as Record<string, unknown>)["if-features"]).toEqual(["f"]);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const x = dm?.findStatement("x");
    expect(x?.data.if_features).toEqual(["f"]);
  });

  it("emits and parses leafref metadata and type shape", () => {
    const module = parseYangString(`
module lr {
  yang-version 1.1;
  namespace "urn:lr";
  prefix lr;

  container data-model {
    leaf port {
      type int32;
    }
    leaf peer {
      type leafref {
        path "/data-model/port";
        require-instance true;
      }
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const peer = (((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
      .properties as Record<string, unknown>)["peer"] as Record<string, unknown>;
    const xYang = peer["x-yang"] as Record<string, unknown>;
    expect(xYang.type).toBe("leafref");
    expect(xYang.path).toBe("/data-model/port");
    expect(xYang["require-instance"]).toBe(true);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const peerLeaf = dm?.findStatement("peer");
    const t = (peerLeaf?.data.type as Record<string, unknown> | undefined) ?? {};
    expect(t.name).toBe("leafref");
    expect(t.path).toBe("/data-model/port");
    expect(t.require_instance).toBe(true);
  });

  it("hoists choice/case into oneOf and restores choice on parse", () => {
    const module = parseYangString(`
module c {
  yang-version 1.1;
  namespace "urn:c";
  prefix c;

  container data-model {
    choice mode {
      mandatory true;
      case a {
        leaf primitive { type string; }
      }
      case b {
        leaf entity { type string; }
      }
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const dm = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    expect(Array.isArray(dm.oneOf)).toBe(true);
    expect((dm.oneOf as unknown[]).length).toBe(2);

    const round = parseJsonSchema(schema);
    const dataModel = round.findStatement("data-model");
    const choice = dataModel?.statements.find((s) => s.keyword === "choice");
    expect(choice).toBeDefined();
    expect(choice?.name).toBe("mode");
    expect(choice?.statements.length).toBe(2);
  });

  it("decimal64 emits multipleOf and round-trips fraction-digits", () => {
    const module = parseYangString(`
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix t;
  container data-model {
    leaf x { type decimal64 { fraction-digits 3; } }
  }
}
`);
    const schema = generateJsonSchema(module);
    const x = (((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
      .properties as Record<string, unknown>)["x"] as Record<string, unknown>;
    expect(x.type).toBe("number");
    expect(x.multipleOf).toBe(0.001);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const leaf = dm?.findStatement("x");
    const t = (leaf?.data.type as Record<string, unknown> | undefined) ?? {};
    expect(t.name).toBe("decimal64");
    expect(t.fraction_digits).toBe(3);
  });

  it("expands uses at emit time when parser keeps uses in AST", () => {
    const module = new YangParser({ expand_uses: false }).parseString(`
module u {
  yang-version 1.1;
  namespace "urn:u";
  prefix u;
  grouping common {
    leaf x { type string; }
  }
  container data-model {
    uses common;
  }
}
`);

    const dataModel = module.findStatement("data-model");
    expect(dataModel?.statements.some((s) => s.keyword === "uses")).toBe(true);

    const schema = generateJsonSchema(module);
    const dmSchema = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    const dmProps = dmSchema.properties as Record<string, unknown>;
    expect(dmProps.x).toBeDefined();
  });
});
