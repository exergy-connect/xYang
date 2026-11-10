import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { YangParser } from "../src";
import type { SerializedStatement } from "../src/core/model";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const EXT = resolve(repoRoot, "examples/ietf-yang-push/modules/ietf-yang-structure-ext@2020-06-17.yang");
const INDEX = "ietf-yang-structure-ext:structure-index";

const YANG = `
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  import ietf-yang-structure-ext { prefix sx; }
  grouping g { leaf n { type uint8; } }
  sx:structure msg { uses g; }
}
`;

function parse(expandUses: boolean) {
  const dir = mkdtempSync(join(tmpdir(), "xyang-pipeline-"));
  try {
    copyFileSync(EXT, join(dir, "ietf-yang-structure-ext@2020-06-17.yang"));
    const source = join(dir, "m.yang");
    writeFileSync(source, YANG);
    return new YangParser({ expandUses: expandUses }).parseFile(source);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function structureIndex(mod: ReturnType<typeof parse>): Record<string, SerializedStatement> | undefined {
  const runtime = mod.data.extension_runtime as Record<string, unknown> | undefined;
  const idx = runtime?.[INDEX];
  return idx && typeof idx === "object" ? (idx as Record<string, SerializedStatement>) : undefined;
}

describe("post-parse pass order", () => {
  it("indexes sx:structure after uses expansion", () => {
    const msg = structureIndex(parse(true))?.msg;
    const children = msg?.statements ?? [];
    expect(children.some((child) => child.keyword === "leaf" && child.name === "n")).toBe(true);
    expect(children.some((child) => child.keyword === "uses")).toBe(false);
  });

  it("leaves the structure index empty when expandUses is false", () => {
    expect(structureIndex(parse(false))).toBeUndefined();
  });
});
