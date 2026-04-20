export class YangError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "YangError";
  }
}

export class YangSyntaxError extends SyntaxError {
  readonly messageText: string;
  readonly line_num?: number;
  readonly line?: string;
  readonly context_lines: Array<[number, string]>;
  readonly filename?: string;

  constructor(
    message: string,
    options: {
      line_num?: number;
      line?: string;
      context_lines?: Array<[number, string]>;
      filename?: string;
    } = {}
  ) {
    const { line_num, line, context_lines = [], filename } = options;

    const parts: string[] = [];
    if (filename) {
      parts.push(`${filename}:`);
    }
    if (line_num) {
      parts.push(`${line_num}:`);
    }
    parts.push(message);

    let rendered = parts.join(" ");
    if (context_lines.length > 0) {
      rendered += "\n";
      for (const [ctxLineNum, ctxLine] of context_lines) {
        const marker = ctxLineNum === line_num ? ">>> " : "    ";
        rendered += `${marker}${String(ctxLineNum).padStart(4, " ")} | ${ctxLine}\n`;
      }
      if (line_num && line) {
        rendered += `     ${" ".repeat(String(line_num).length + 3)}${"^".repeat(Math.max(1, line.trim().length))}`;
      }
    }

    super(rendered);
    this.name = "YangSyntaxError";
    this.messageText = message;
    this.line_num = line_num;
    this.line = line;
    this.context_lines = context_lines;
    this.filename = filename;
  }

  override toString(): string {
    return this.messageText;
  }
}

export class YangSemanticError extends YangError {
  constructor(message: string) {
    super(message);
    this.name = "YangSemanticError";
  }
}

export class YangRefineTargetNotFoundError extends YangSemanticError {
  readonly target_path: string;

  constructor(target_path: string) {
    super(`Refine target path matches no node in the used grouping: '${target_path}'`);
    this.name = "YangRefineTargetNotFoundError";
    this.target_path = target_path;
  }
}

export class YangCircularUsesError extends YangSemanticError {
  readonly prefix_chain: readonly string[];
  readonly repeated: string;

  constructor(prefix_chain: readonly string[], repeated: string) {
    const cycle = [...prefix_chain, repeated].join(" -> ");
    super(
      "Circular uses chain: groupings are expanded at compile-time and this " +
        `cycle would not terminate (${cycle}). Restructure groupings to break the cycle.`
    );
    this.name = "YangCircularUsesError";
    this.prefix_chain = [...prefix_chain];
    this.repeated = repeated;
  }
}

export class XPathSyntaxError extends Error {
  readonly messageText: string;
  readonly position?: number;
  readonly expression?: string;

  constructor(
    message: string,
    options: {
      position?: number;
      expression?: string;
      context_before?: number;
      context_after?: number;
    } = {}
  ) {
    const { position, expression, context_before = 10, context_after = 10 } = options;

    if (expression !== undefined && position !== undefined) {
      const start = Math.max(0, position - context_before);
      const end = Math.min(expression.length, position + context_after);
      const context = expression.slice(start, end);
      const pointerPos = position - start;

      const parts = [message, `\nExpression: ${context}`, `           ${" ".repeat(pointerPos)}^`];
      if (position < expression.length) {
        parts.push(`Position: ${position} (character: ${JSON.stringify(expression[position])})`);
      } else {
        parts.push(`Position: ${position} (end of expression)`);
      }
      super(parts.join("\n"));
    } else {
      super(message);
    }

    this.name = "XPathSyntaxError";
    this.messageText = message;
    this.position = position;
    this.expression = expression;
  }

  override toString(): string {
    return this.messageText;
  }
}

export class XPathEvaluationError extends Error {
  readonly messageText: string;

  constructor(message: string) {
    super(message);
    this.name = "XPathEvaluationError";
    this.messageText = message;
  }

  override toString(): string {
    return this.messageText;
  }
}

export class UnsupportedXPathError extends Error {
  readonly messageText: string;
  readonly expression?: string;
  readonly construct?: string;

  constructor(message: string, options: { expression?: string; construct?: string } = {}) {
    const parts = [message];
    if (options.construct) {
      parts.push(`Unsupported construct: ${options.construct}`);
    }
    if (options.expression) {
      parts.push(`Expression: ${options.expression}`);
    }
    super(parts.join("\n"));

    this.name = "UnsupportedXPathError";
    this.messageText = message;
    this.expression = options.expression;
    this.construct = options.construct;
  }

  override toString(): string {
    return this.messageText;
  }
}
