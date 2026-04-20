export type XPathTokenKind =
  | "identifier"
  | "number"
  | "string"
  | "operator"
  | "paren_open"
  | "paren_close"
  | "bracket_open"
  | "bracket_close"
  | "dot"
  | "dotdot"
  | "slash"
  | "comma"
  | "eof";

export type XPathToken = {
  kind: XPathTokenKind;
  value: string;
  position: number;
};

const OPERATORS = ["<=", ">=", "!=", "==", "//", "=", "<", ">", "+", "-", "*", "/"];

export function tokenizeXPath(expr: string): XPathToken[] {
  const tokens: XPathToken[] = [];
  let position = 0;

  const add = (kind: XPathTokenKind, value: string, at = position): void => {
    tokens.push({ kind, value, position: at });
  };

  while (position < expr.length) {
    const ch = expr[position];

    if (/\s/.test(ch)) {
      position += 1;
      continue;
    }

    if (ch === "\"" || ch === "'") {
      const quote = ch;
      const start = position;
      position += 1;
      let value = "";
      while (position < expr.length) {
        const c = expr[position];
        if (c === quote && expr[position - 1] !== "\\") {
          position += 1;
          break;
        }
        value += c;
        position += 1;
      }
      add("string", value, start);
      continue;
    }

    if (/\d/.test(ch) || (ch === "-" && /\d/.test(expr[position + 1] ?? ""))) {
      const start = position;
      let value = "";
      if (expr[position] === "-") {
        value += "-";
        position += 1;
      }
      while (position < expr.length && /\d/.test(expr[position])) {
        value += expr[position];
        position += 1;
      }
      if (expr[position] === "." && /\d/.test(expr[position + 1] ?? "")) {
        value += ".";
        position += 1;
        while (position < expr.length && /\d/.test(expr[position])) {
          value += expr[position];
          position += 1;
        }
      }
      add("number", value, start);
      continue;
    }

    if (/[A-Za-z_]/.test(ch)) {
      const start = position;
      let value = "";
      while (position < expr.length && /[A-Za-z0-9_:\-]/.test(expr[position])) {
        value += expr[position];
        position += 1;
      }
      add("identifier", value, start);
      continue;
    }

    if (ch === "/") {
      if (expr[position + 1] === "/") {
        add("operator", "//");
        position += 2;
      } else {
        add("slash", "/");
        position += 1;
      }
      continue;
    }

    if (ch === ".") {
      if (expr[position + 1] === ".") {
        add("dotdot", "..");
        position += 2;
      } else {
        add("dot", ".");
        position += 1;
      }
      continue;
    }

    if (ch === "(") {
      add("paren_open", "(");
      position += 1;
      continue;
    }
    if (ch === ")") {
      add("paren_close", ")");
      position += 1;
      continue;
    }
    if (ch === "[") {
      add("bracket_open", "[");
      position += 1;
      continue;
    }
    if (ch === "]") {
      add("bracket_close", "]");
      position += 1;
      continue;
    }
    if (ch === ",") {
      add("comma", ",");
      position += 1;
      continue;
    }

    const remaining = expr.slice(position);
    const op = OPERATORS.find((candidate) => remaining.startsWith(candidate));
    if (op) {
      add("operator", op);
      position += op.length;
      continue;
    }

    position += 1;
  }

  add("eof", "", position);
  return tokens;
}
