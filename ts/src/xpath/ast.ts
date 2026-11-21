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
  /**
   * Absolute, no `prefix:*` step, and every predicate is context-free (set by the parser, same
   * rule as Python `PathNode.is_cacheable`). Only such paths use the per-validation path cache.
   */
  isCacheable?: boolean;
  /** Original path text, including predicates, for reversible export. */
  source?: string;
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

const pathCacheKeys = new WeakMap<XPathPathNode, string>();

function astCacheKey(node: XPathAstNode): string {
  switch (node.kind) {
    case "path":
      return pathCacheKey(node);
    case "binary":
      return `(${astCacheKey(node.left)} ${node.operator} ${astCacheKey(node.right)})`;
    case "function":
      return `${node.name}(${node.args.map(astCacheKey).join(", ")})`;
    default:
      return JSON.stringify(node.value);
  }
}

/**
 * Path text plus each step's bound module and predicate (Python `_path_cache_key`). The same
 * text binds different modules in different modules, and predicates change the node-set, so
 * neither may share a path cache entry.
 */
export function pathCacheKey(path: XPathPathNode): string {
  let key = pathCacheKeys.get(path);
  if (key === undefined) {
    const steps = path.segments.map((segment) => {
      let step = segment.module === undefined ? segment.step : `${segment.step}@${segment.module}`;
      if (segment.predicate) step += `[${astCacheKey(segment.predicate)}]`;
      return step;
    });
    key = (path.isAbsolute ? "/" : "") + steps.join("/");
    pathCacheKeys.set(path, key);
  }
  return key;
}

/** Drop the memoized key after `bindXPathPrefixes` changes a step's module. */
export function forgetPathCacheKey(path: XPathPathNode): void {
  pathCacheKeys.delete(path);
}
