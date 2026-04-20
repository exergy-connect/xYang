import { YangSyntaxError } from "../core/errors";

export enum YangTokenType {
  LBRACE = "{",
  RBRACE = "}",
  SEMICOLON = ";",
  COLON = ":",
  EQUALS = "=",
  PLUS = "+",
  SLASH = "/",

  STRING = "STRING",
  IDENTIFIER = "IDENTIFIER",
  INTEGER = "INTEGER",
  DOTTED_NUMBER = "DOTTED_NUMBER",

  MODULE = "module",
  YANG_VERSION = "yang-version",
  NAMESPACE = "namespace",
  PREFIX = "prefix",
  ORGANIZATION = "organization",
  CONTACT = "contact",
  DESCRIPTION = "description",
  REVISION = "revision",
  TYPEDEF = "typedef",
  IDENTITY = "identity",
  BASE = "base",
  TYPE = "type",
  BINARY = "binary",
  BITS = "bits",
  BOOLEAN = "boolean",
  DECIMAL64 = "decimal64",
  EMPTY = "empty",
  ENUMERATION = "enumeration",
  IDENTITYREF = "identityref",
  INSTANCE_IDENTIFIER = "instance-identifier",
  INT8 = "int8",
  INT16 = "int16",
  INT32 = "int32",
  INT64 = "int64",
  LEAFREF = "leafref",
  STRING_KW = "string",
  UINT8 = "uint8",
  UINT16 = "uint16",
  UINT32 = "uint32",
  UINT64 = "uint64",
  UNION = "union",
  PATH = "path",
  REQUIRE_INSTANCE = "require-instance",
  ENUM = "enum",
  VALUE = "value",
  STATUS = "status",
  BIT = "bit",
  POSITION = "position",
  PATTERN = "pattern",
  LENGTH = "length",
  FRACTION_DIGITS = "fraction-digits",
  RANGE = "range",

  GROUPING = "grouping",
  USES = "uses",
  REFINE = "refine",
  CONTAINER = "container",
  LIST = "list",
  LEAF = "leaf",
  LEAF_LIST = "leaf-list",
  ANYDATA = "anydata",
  ANYXML = "anyxml",
  CHOICE = "choice",
  CASE = "case",
  MUST = "must",
  WHEN = "when",
  PRESENCE = "presence",
  KEY = "key",
  MIN_ELEMENTS = "min-elements",
  MAX_ELEMENTS = "max-elements",
  ORDERED_BY = "ordered-by",
  MANDATORY = "mandatory",
  DEFAULT = "default",
  ERROR_MESSAGE = "error-message",
  ERROR_APP_TAG = "error-app-tag",
  TRUE = "true",
  FALSE = "false",

  IMPORT = "import",
  INCLUDE = "include",
  REVISION_DATE = "revision-date",
  FEATURE = "feature",
  IF_FEATURE = "if-feature",
  AUGMENT = "augment",
  SUBMODULE = "submodule",
  BELONGS_TO = "belongs-to",
  REFERENCE = "reference",
  ARGUMENT = "argument",
  YIN_ELEMENT = "yin-element",
  DEVIATION = "deviation",
  EXTENSION = "extension",
  RPC = "rpc",
  ACTION = "action",
  NOTIFICATION = "notification",
  INPUT = "input",
  OUTPUT = "output"
}

const PUNCTUATION = new Set<YangTokenType>([
  YangTokenType.LBRACE,
  YangTokenType.RBRACE,
  YangTokenType.SEMICOLON,
  YangTokenType.COLON,
  YangTokenType.EQUALS,
  YangTokenType.PLUS,
  YangTokenType.SLASH
]);

const LITERAL_TYPES = new Set<YangTokenType>([
  YangTokenType.STRING,
  YangTokenType.IDENTIFIER,
  YangTokenType.INTEGER,
  YangTokenType.DOTTED_NUMBER
]);

export const YANG_KEYWORDS: Record<string, YangTokenType> = Object.values(YangTokenType)
  .filter((tt) => !PUNCTUATION.has(tt) && !LITERAL_TYPES.has(tt))
  .reduce<Record<string, YangTokenType>>((acc, tt) => {
    acc[tt] = tt;
    return acc;
  }, {});

export function diagnosticSourceLines(content: string): string[] {
  if (!content) {
    return [];
  }
  return content.split("\n").map((segment) => segment.replace(/\r$/, ""));
}

export type Token = {
  value: string;
  line_num: number;
  char_pos: number;
};

export type YangToken = {
  type: YangTokenType;
  value: string;
  line_num: number;
  char_pos: number;
  // Compatibility aliases for existing TS parser code.
  kind: "identifier" | "string" | "number" | "symbol";
  line: number;
  column: number;
};

function classifyKind(type: YangTokenType): YangToken["kind"] {
  if (type === YangTokenType.STRING) {
    return "string";
  }
  if (type === YangTokenType.INTEGER || type === YangTokenType.DOTTED_NUMBER) {
    return "number";
  }
  if (PUNCTUATION.has(type)) {
    return "symbol";
  }
  return "identifier";
}

export function makeYangToken(type: YangTokenType, value: string, line_num: number, char_pos: number): YangToken {
  return {
    type,
    value,
    line_num,
    char_pos,
    kind: classifyKind(type),
    line: line_num,
    column: char_pos + 1
  };
}

export class TokenStream {
  readonly token_list: YangToken[];
  readonly tokens: string[];
  readonly positions: Array<[number, number]>;
  readonly filename?: string;
  index: number;

  private readonly source: string;
  private diagnostic_lines?: string[];

  constructor(token_list: YangToken[], source: string, filename?: string) {
    this.token_list = token_list;
    this.tokens = token_list.map((t) => t.value);
    this.positions = token_list.map((t) => [t.line_num, t.char_pos]);
    this.source = source;
    this.filename = filename;
    this.index = 0;
  }

  peek_token(): YangToken | undefined {
    return this.token_list[this.index];
  }

  peek(offset = 0): string | undefined {
    return this.token_list[this.index + offset]?.value;
  }

  consume(expected?: string): string {
    if (this.index >= this.tokens.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tokenVal = this.tokens[this.index];
    if (expected !== undefined && tokenVal !== expected) {
      throw this._make_error(`Expected '${expected}', got '${tokenVal}'`);
    }
    this.index += 1;
    return tokenVal;
  }

  consume_if(expected: string): boolean {
    if (this.peek() === expected) {
      this.consume();
      return true;
    }
    return false;
  }

  peek_type(): YangTokenType {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    return this.token_list[this.index].type;
  }

  peek_type_at(offset = 0): YangTokenType | undefined {
    return this.token_list[this.index + offset]?.type;
  }

  consume_type(expected: YangTokenType): string {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    if (tok.type !== expected) {
      throw this._make_error(`Expected ${expected}, got ${tok.type} ('${tok.value}')`);
    }
    this.index += 1;
    return tok.value;
  }

  consume_if_type(expected: YangTokenType): boolean {
    if (this.index >= this.token_list.length) {
      return false;
    }
    if (this.token_list[this.index].type === expected) {
      this.consume_type(expected);
      return true;
    }
    return false;
  }

  consume_oneof(allowed_types: YangTokenType[]): [string, YangTokenType] {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    if (!allowed_types.includes(tok.type)) {
      throw this._make_error(
        `Expected one of (${allowed_types.join(", ")}), got ${tok.type} ('${tok.value}')`
      );
    }
    this.index += 1;
    return [tok.value, tok.type];
  }

  has_more(): boolean {
    return this.index < this.tokens.length;
  }

  // Compatibility for prior TS parser helpers.
  hasMore(): boolean {
    return this.has_more();
  }

  /** Throw {@link YangSyntaxError} at the current token position. */
  syntaxError(message: string): never {
    throw this._make_error(message);
  }

  position(): [number, number] {
    if (this.index < this.positions.length) {
      return this.positions[this.index];
    }
    if (this.positions.length > 0) {
      return this.positions[this.positions.length - 1];
    }
    return [1, 0];
  }

  private diagnostic_lines_once(): string[] {
    if (!this.diagnostic_lines) {
      this.diagnostic_lines = diagnosticSourceLines(this.source);
    }
    return this.diagnostic_lines;
  }

  private _make_error(message: string, context_lines = 3): YangSyntaxError {
    const [line_num] = this.position();
    const lines = this.diagnostic_lines_once();
    const context: Array<[number, string]> = [];

    const startLine = Math.max(1, line_num - context_lines);
    const endLine = Math.min(lines.length, line_num + context_lines);
    for (let n = startLine; n <= endLine; n += 1) {
      if (n <= lines.length) {
        context.push([n, lines[n - 1]]);
      }
    }

    const line = line_num <= lines.length ? lines[line_num - 1] : "";
    return new YangSyntaxError(message, {
      line_num,
      line,
      context_lines: context,
      filename: this.filename
    });
  }
}

export type ParserContextParent = unknown;

export class ParserContext {
  module: unknown;
  current_parent: ParserContextParent;
  source_dir?: string;

  constructor(init: { module: unknown; current_parent: ParserContextParent; source_dir?: string }) {
    this.module = init.module;
    this.current_parent = init.current_parent;
    this.source_dir = init.source_dir;
  }

  push_parent(parent: ParserContextParent): ParserContext {
    return new ParserContext({
      module: this.module,
      current_parent: parent,
      source_dir: this.source_dir
    });
  }
}
