import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { YangParser } from "../src";
import { YangTokenizer } from "../src/parser/tokenizer";

it("normalizes quoted string concatenation in the tokenizer", () => {
  const stream = new YangTokenizer().tokenize('description "first " + "second";');

  expect(stream.tokens).toEqual(["description", "first second", ";"]);

  const unquoted = new YangTokenizer().tokenize('description "first " + second;');
  expect(unquoted.tokens).toEqual(["description", "first ", "+", "second", ";"]);
});

it("accepts a concatenated description in an imported module", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyang-import-string-concat-"));
  writeFileSync(join(dir, "dependency.yang"), `module dependency {
  yang-version 1.1;
  namespace "urn:dependency";
  prefix dep;
  typedef label {
    type string;
    description "first "
              + "second";
  }
}
`);
  const root = join(dir, "root.yang");
  writeFileSync(root, `module root {
  yang-version 1.1;
  namespace "urn:root";
  prefix root;
  import dependency { prefix dep; }
  leaf value { type dep:label; }
}
`);

  const module = new YangParser({ include_path: [dir] }).parseFile(root);
  const imports = (module.data as { import_prefixes: Record<string, unknown> }).import_prefixes;
  const imported = imports.dep as {
    typedefs: Record<string, { description: string }>;
  };

  expect(imported.typedefs.label?.description).toBe("first second");
});
