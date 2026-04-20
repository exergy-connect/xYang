import { XPathSyntaxError } from "../core/errors";
import { XPathAstNode, XPathBinaryNode, XPathFunctionNode, XPathLiteralNode, XPathPathNode } from "./ast";
import { XPathToken, tokenizeXPath } from "./tokenizer";

const COMPARISON_OPS = new Set(["=", "!=", "<", ">", "<=", ">="]);
const ADDITIVE_OPS = new Set(["+", "-"]);

class XPathParser {
  private readonly tokens: XPathToken[];

  private position = 0;

  constructor(private readonly expression: string) {
    this.tokens = tokenizeXPath(expression);
  }

  parse(): XPathAstNode {
    if (this.current().kind === "eof") {
      throw new XPathSyntaxError("Empty expression", { expression: this.expression, position: 0 });
    }
    const node = this.parseExpression();
    const token = this.current();
    if (token.kind !== "eof") {
      throw new XPathSyntaxError(`Unexpected token: ${token.value || token.kind}`, {
        expression: this.expression,
        position: token.position
      });
    }
    return node;
  }

  private current(): XPathToken {
    return this.tokens[this.position] ?? { kind: "eof", value: "", position: this.expression.length };
  }

  private consume(expectedKind?: XPathToken["kind"]): XPathToken {
    const token = this.current();
    if (expectedKind && token.kind !== expectedKind) {
      throw new XPathSyntaxError(`Expected ${expectedKind}, got ${token.kind} (${token.value})`, {
        expression: this.expression,
        position: token.position
      });
    }
    this.position += 1;
    return token;
  }

  private isKeyword(value: string): boolean {
    const token = this.current();
    return token.kind === "identifier" && token.value.toLowerCase() === value.toLowerCase();
  }

  private parseExpression(): XPathAstNode {
    return this.parseLogicalOr();
  }

  private parseLogicalOr(): XPathAstNode {
    let left = this.parseLogicalAnd();
    while (this.isKeyword("or")) {
      this.consume();
      const right = this.parseLogicalAnd();
      left = { kind: "binary", operator: "or", left, right };
    }
    return left;
  }

  private parseLogicalAnd(): XPathAstNode {
    let left = this.parseComparison();
    while (this.isKeyword("and")) {
      this.consume();
      const right = this.parseComparison();
      left = { kind: "binary", operator: "and", left, right };
    }
    return left;
  }

  private parseComparison(): XPathAstNode {
    let left = this.parseAdditive();
    const token = this.current();
    if (token.kind === "operator" && COMPARISON_OPS.has(token.value)) {
      const op = this.consume("operator").value;
      const right = this.parseAdditive();
      left = { kind: "binary", operator: op, left, right };
    }
    return left;
  }

  private parseAdditive(): XPathAstNode {
    let left = this.parseMultiplicative();
    while (true) {
      const token = this.current();
      if (token.kind === "operator" && ADDITIVE_OPS.has(token.value)) {
        const op = this.consume("operator").value;
        const right = this.parseMultiplicative();
        left = { kind: "binary", operator: op, left, right };
      } else {
        return left;
      }
    }
  }

  private parseMultiplicative(): XPathAstNode {
    let left = this.parseUnary();
    while (true) {
      const token = this.current();
      if (token.kind === "slash") {
        this.consume("slash");
        const right = this.parsePath(false);
        left = { kind: "binary", operator: "/", left, right };
      } else if (token.kind === "operator" && token.value === "*") {
        this.consume("operator");
        const right = this.parseUnary();
        left = { kind: "binary", operator: "*", left, right };
      } else {
        return left;
      }
    }
  }

  private parseUnary(): XPathAstNode {
    const token = this.current();
    if (token.kind === "operator" && token.value === "-") {
      this.consume("operator");
      const operand = this.parseUnary();
      return { kind: "binary", operator: "-", left: { kind: "literal", value: 0 }, right: operand };
    }
    if (token.kind === "operator" && token.value === "+") {
      this.consume("operator");
      return this.parseUnary();
    }
    if (this.isKeyword("not")) {
      this.consume();
      this.consume("paren_open");
      const arg = this.parseExpression();
      this.consume("paren_close");
      return { kind: "function", name: "not", args: [arg] };
    }
    return this.parsePrimary();
  }

  private parsePrimary(): XPathAstNode {
    const token = this.current();

    if (token.kind === "string") {
      return { kind: "literal", value: this.consume("string").value };
    }

    if (token.kind === "number") {
      const raw = this.consume("number").value;
      const parsed = raw.includes(".") ? Number.parseFloat(raw) : Number.parseInt(raw, 10);
      if (Number.isNaN(parsed)) {
        throw new XPathSyntaxError(`Invalid number: ${raw}`, {
          expression: this.expression,
          position: token.position
        });
      }
      return { kind: "literal", value: parsed };
    }

    if (token.kind === "identifier") {
      if (this.isKeyword("true")) {
        this.consume();
        if (this.current().kind === "paren_open") {
          this.consume("paren_open");
          this.consume("paren_close");
        }
        return { kind: "literal", value: true };
      }
      if (this.isKeyword("false")) {
        this.consume();
        if (this.current().kind === "paren_open") {
          this.consume("paren_open");
          this.consume("paren_close");
        }
        return { kind: "literal", value: false };
      }
      const next = this.tokens[this.position + 1];
      if (next?.kind === "paren_open") {
        return this.parseFunctionCall();
      }
      return this.parsePath(false);
    }

    if (token.kind === "dot") {
      this.consume("dot");
      if (this.current().kind === "paren_open") {
        this.consume("paren_open");
        this.consume("paren_close");
        return { kind: "function", name: "current", args: [] };
      }
      return this.parsePath(false, ".");
    }

    if (token.kind === "dotdot") {
      return this.parsePath(false);
    }

    if (token.kind === "slash") {
      this.consume("slash");
      return this.parsePath(true);
    }

    if (token.kind === "paren_open") {
      this.consume("paren_open");
      if (this.current().kind === "string" || this.current().kind === "number") {
        const first = this.parsePrimary();
        if (first.kind === "literal" && this.current().kind === "comma") {
          const values: unknown[] = [first.value];
          while (this.current().kind === "comma") {
            this.consume("comma");
            const nextLiteral = this.parsePrimary();
            if (nextLiteral.kind !== "literal") {
              throw new XPathSyntaxError("Value list may only contain literals", {
                expression: this.expression,
                position: this.current().position
              });
            }
            values.push(nextLiteral.value);
          }
          this.consume("paren_close");
          return { kind: "literal", value: values };
        }
        if (this.current().kind === "paren_close") {
          this.consume("paren_close");
          return first;
        }
      }
      const inner = this.parseExpression();
      this.consume("paren_close");
      return inner;
    }

    throw new XPathSyntaxError(`Unexpected token: ${token.value || token.kind}`, {
      expression: this.expression,
      position: token.position
    });
  }

  private parseFunctionCall(): XPathAstNode {
    const name = this.consume("identifier").value;
    this.consume("paren_open");
    const args: XPathAstNode[] = [];
    if (this.current().kind !== "paren_close") {
      args.push(this.parseExpression());
      while (this.current().kind === "comma") {
        this.consume("comma");
        args.push(this.parseExpression());
      }
    }
    this.consume("paren_close");
    const node: XPathFunctionNode = { kind: "function", name, args };
    return node;
  }

  private parsePath(isAbsolute: boolean, firstStep?: string): XPathAstNode {
    const segments: XPathPathNode["segments"] = [];

    const pushStep = (step: string): boolean => {
      const segment: XPathPathNode["segments"][number] = { step };
      segments.push(segment);
      if (this.current().kind === "bracket_open") {
        this.consume("bracket_open");
        segment.predicate = this.parseExpression();
        this.consume("bracket_close");
      }
      if (this.current().kind === "slash") {
        this.consume("slash");
        return true;
      }
      return false;
    };

    if (firstStep !== undefined) {
      pushStep(firstStep);
    }

    while (this.current().kind === "dot" || this.current().kind === "dotdot" || this.current().kind === "identifier") {
      const step = this.consume().value;
      if (!pushStep(step)) {
        break;
      }
    }

    const node: XPathPathNode = { kind: "path", segments, isAbsolute };
    return node;
  }
}

export function parseXPath(expression: string): XPathAstNode {
  return new XPathParser(expression).parse();
}
