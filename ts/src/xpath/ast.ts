export type XPathPathSegment = {
  step: string;
  predicate?: XPathAstNode;
  /** Module a `prefix:name` or `prefix:*` step is bound to; set by `bindXPathPrefixes`. */
  module?: string;
};

/** Lexical prefix of a `prefix:name` or `prefix:*` step, else undefined. */
export function stepPrefix(step: string): string | undefined {
  if (step === "." || step === ".." || !step.includes(":")) return undefined;
  return step.slice(0, step.indexOf(":"));
}

export function isWildcardStep(step: string): boolean {
  return step === "*" || step.endsWith(":*");
}

export type XPathLiteralNode = {
  kind: "literal";
  value: unknown;
};

export type XPathPathNode = {
  kind: "path";
  segments: XPathPathSegment[];
  isAbsolute: boolean;
};

export type XPathBinaryNode = {
  kind: "binary";
  operator: string;
  left: XPathAstNode;
  right: XPathAstNode;
};

export type XPathFunctionNode = {
  kind: "function";
  name: string;
  args: XPathAstNode[];
};

export type XPathAstNode = XPathLiteralNode | XPathPathNode | XPathBinaryNode | XPathFunctionNode;
