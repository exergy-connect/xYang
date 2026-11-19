import type { XPathAstNode } from "./ast";
import { parseXPath } from "./parser";

/** True only when every statically identifiable data path stays within the subtree.
 * Paths are schema paths, expressed as local names from the module root.
 * Context-changing functions and wildcard steps cannot be proved local and fail closed.
 */
export function expressionIsWithinSubtree(
  expression: string,
  context: readonly string[],
  subtree: readonly string[]
): boolean {
  const within = (path: readonly string[]) => subtree.every((part, i) => path[i] === part);
  const visit = (node: XPathAstNode, base: readonly string[]): boolean => {
    if (node.kind === "literal") return true;
    if (node.kind === "binary") {
      if (node.operator === "/" && node.left.kind === "function" && node.left.name === "current") return within(context) && visit(node.right, context);
      return visit(node.left, base) && visit(node.right, base);
    }
    if (node.kind === "function") {
      // current() changes the context of a subsequent path; do not guess its dependencies.
      if (node.name === "deref") return false;
      if (node.name === "current") return within(context);
      return node.args.every((arg) => visit(arg, base));
    }
    const path = node.isAbsolute ? [] : [...base];
    for (const segment of node.segments) {
      if (segment.step === "..") path.pop();
      else if (segment.step !== ".") {
        if (segment.step.includes("*")) return false;
        path.push(segment.step.split(":").pop()!);
      }
      if (segment.predicate && !visit(segment.predicate, path)) return false;
    }
    return within(path);
  };
  return visit(parseXPath(expression), context);
}
