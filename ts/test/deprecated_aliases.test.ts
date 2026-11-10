import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { YangParser } from "../src";
import { YangLeafStmt, YangStatementList } from "../src/core/ast";

describe("deprecated snake_case aliases (#72)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("still accepts expand_uses and include_path, warns once, and lets camelCase win", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const dir = mkdtempSync(join(tmpdir(), "xyang-deprecated-"));

    const legacy = new YangParser({ expand_uses: false, include_path: [dir] });
    expect(legacy.expandUses).toBe(false);
    expect(legacy.includePath).toEqual([resolve(dir)]);

    const messages = warn.mock.calls.map((call) => String(call[0]));
    expect(messages.some((message) => message.includes("expand_uses"))).toBe(true);
    expect(messages.some((message) => message.includes("include_path"))).toBe(true);

    warn.mockClear();
    const again = new YangParser({ expand_uses: false, include_path: [dir] });
    expect(again.expandUses).toBe(false);
    expect(warn).not.toHaveBeenCalled();

    const preferred = new YangParser({
      expandUses: false,
      expand_uses: true,
      includePath: [dir],
      include_path: [tmpdir()]
    });
    expect(preferred.expandUses).toBe(false);
    expect(preferred.includePath).toEqual([resolve(dir)]);
  });

  it("keeps find_statement and get_all_leaves working as one-time deprecated aliases", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const leaf = new YangLeafStmt({ name: "name" });
    const list = new YangStatementList([leaf]);

    expect(list.getAllLeaves()).toEqual([leaf]);
    expect(warn).not.toHaveBeenCalled();

    expect(list.find_statement("name")).toBe(list.findStatement("name"));
    expect(list.get_all_leaves()).toEqual([leaf]);
    const messages = warn.mock.calls.map((call) => String(call[0]));
    expect(messages.some((message) => message.includes("find_statement"))).toBe(true);
    expect(messages.some((message) => message.includes("get_all_leaves"))).toBe(true);

    warn.mockClear();
    expect(list.find_statement("name")).toBe(leaf);
    expect(list.get_all_leaves()).toEqual([leaf]);
    expect(warn).not.toHaveBeenCalled();
  });
});
