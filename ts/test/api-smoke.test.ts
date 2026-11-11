import { describe, expect, it } from "vitest";
import { TypeConstraint, TypeSystem } from "../src/types";

describe("typescript bridge api", () => {
  it("validates primitive type through TypeSystem", () => {
    const [ok] = new TypeSystem().validate("abc", "string", new TypeConstraint({ length: "1..5" }));
    expect(ok).toBe(true);
  });
});
