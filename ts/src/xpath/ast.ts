export type XPathPathSegment = {
  step: string;
  predicate?: XPathAstNode;
};

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
