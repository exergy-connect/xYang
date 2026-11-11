export type XPathPathSegment = {
  step: string;
  predicate?: XPathAstNode;
  /** Module a `prefix:*` step is bound to; set by `bindWildcardPrefixes`. */
  module?: string;
};

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
