import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangString } from "../../src";

describe("python parity: json/test_if_features_json", () => {
  it("emits leaf if-features and round-trips through parseJsonSchema", () => {
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
    const leafSchema = (
      ((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
        .properties as Record<string, unknown>
    ).x as Record<string, unknown>;
    expect((leafSchema["x-yang"] as Record<string, unknown>)["if-features"]).toEqual(["f"]);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const leaf = dm?.findStatement("x");
    expect(leaf?.data.if_features).toEqual(["f"]);
  });

  it("round-trips choice and case if-features with hoisted oneOf schema", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature cf;
  feature bf;
  container data-model {
    choice ch {
      if-feature "cf";
      case a {
        if-feature "bf";
        leaf la { type string; }
      }
      case b {
        leaf lb { type string; }
      }
    }
  }
}
`);

    const schema = generateJsonSchema(module);
    const dmSchema = (schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>;
    const dmXYang = dmSchema["x-yang"] as Record<string, unknown>;
    const choiceMeta = dmXYang.choice as Record<string, unknown>;
    expect(choiceMeta["if-features"]).toEqual(["cf"]);
    const branches = dmSchema.oneOf as Array<Record<string, unknown>>;
    const branchA = branches.find((b) => Boolean((b.properties as Record<string, unknown>)?.la));
    expect(branchA).toBeDefined();
    expect(((branchA as Record<string, unknown>)["x-yang"] as Record<string, unknown>)["if-features"]).toEqual(["bf"]);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const ch = dm?.statements.find((s) => s.keyword === "choice");
    expect(ch).toBeDefined();
    expect(ch?.data.if_features).toEqual(["cf"]);
    const caseA = ch?.findStatement("a");
    expect(caseA?.data.if_features).toEqual(["bf"]);
  });

  it("round-trips multiple if-feature lines on one leaf (AND semantics storage)", () => {
    const module = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container data-model {
    leaf z {
      if-feature "p";
      if-feature "q";
      type string;
    }
  }
}
`);
    const schema = generateJsonSchema(module);
    const zSchema = (
      ((schema.properties as Record<string, unknown>)["data-model"] as Record<string, unknown>)
        .properties as Record<string, unknown>
    ).z as Record<string, unknown>;
    expect((zSchema["x-yang"] as Record<string, unknown>)["if-features"]).toEqual(["p", "q"]);

    const round = parseJsonSchema(schema);
    const dm = round.findStatement("data-model");
    const leaf = dm?.findStatement("z");
    expect(leaf?.data.if_features).toEqual(["p", "q"]);
  });
});
