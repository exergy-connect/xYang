#!/usr/bin/env node
import {
  resolveQualifiedTopLevel
} from "./chunk-6D65YJDB.js";
import {
  ParserContext,
  TokenStream,
  TypeConstraint,
  TypeSystem,
  XPathSyntaxError,
  YANG_INTEGER_BOUNDS,
  YangCircularUsesError,
  YangRefineTargetNotFoundError,
  YangSemanticError,
  YangSyntaxError,
  jsonIntegerBoundsForBuiltin,
  makeYangToken,
  yangIntegerFromJsonBounds
} from "./chunk-JVFM24VE.js";

// src/core/model.ts
function asStatement(data) {
  if (!data || typeof data !== "object") {
    return void 0;
  }
  return new YangStatement(data);
}
var YangStatement = class _YangStatement {
  data;
  constructor(data) {
    this.data = data;
  }
  get name() {
    return this.data.name;
  }
  get keyword() {
    return this.data.keyword;
  }
  get argument() {
    return this.data.argument;
  }
  get statements() {
    const items = Array.isArray(this.data.statements) ? this.data.statements : [];
    return items.map((item) => new _YangStatement(item));
  }
  findStatement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
};
var YangModule = class {
  data;
  source;
  constructor(data, source) {
    this.data = data;
    this.source = source;
  }
  get name() {
    return this.data.name;
  }
  get yangVersion() {
    return this.data.yang_version;
  }
  get namespace() {
    return this.data.namespace;
  }
  get prefix() {
    return this.data.prefix;
  }
  get organization() {
    const v = this.data.organization;
    return typeof v === "string" && v.length > 0 ? v : void 0;
  }
  get contact() {
    const v = this.data.contact;
    return typeof v === "string" && v.length > 0 ? v : void 0;
  }
  /** First module-level ``description`` substatement (RFC 7950). */
  get description() {
    const v = this.data.description;
    return typeof v === "string" ? v : void 0;
  }
  get typedefs() {
    return this.data.typedefs ?? {};
  }
  /** Identity names → `{ bases }` from parsed `identity` / `base` statements (RFC 7950). */
  get identities() {
    const raw = this.data.identities;
    if (!raw || typeof raw !== "object") {
      return {};
    }
    return raw;
  }
  get statements() {
    const raw = this.data.statements;
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw.map(asStatement).filter((stmt) => Boolean(stmt));
  }
  findStatement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
};

// src/ext/anydata_validation.ts
function rejectUnknownKeys(kwargs, allowed) {
  const unexpected = Object.keys(kwargs).filter((k) => !allowed.has(k)).sort();
  if (unexpected.length > 0) {
    throw new TypeError(`unexpected keyword arguments: ${JSON.stringify(unexpected)}`);
  }
}
function parseAnydataExtensionConfig(config) {
  rejectUnknownKeys(config, /* @__PURE__ */ new Set(["modules", "mode"]));
  const mode = config.mode === void 0 ? "complete" /* COMPLETE */ : config.mode;
  const seenNames = /* @__PURE__ */ new Set();
  for (let i = 0; i < config.modules.length; i += 1) {
    const mod = config.modules[i];
    const moduleName2 = mod.name;
    if (!moduleName2) {
      throw new TypeError(`modules[${i}] must have a module name`);
    }
    if (seenNames.has(moduleName2)) {
      throw new TypeError(`duplicate module name '${moduleName2}' in modules`);
    }
    seenNames.add(moduleName2);
  }
  return {
    modules: [...config.modules],
    mode
  };
}

// src/parser/yang-parser.ts
import { existsSync, readFileSync, readdirSync } from "fs";
import { dirname, resolve } from "path";

// src/parser/keywords.ts
var MODULE = "module";
var YANG_VERSION = "yang-version";
var NAMESPACE = "namespace";
var PREFIX = "prefix";
var ORGANIZATION = "organization";
var CONTACT = "contact";
var DESCRIPTION = "description";
var REVISION = "revision";
var TYPEDEF = "typedef";
var IDENTITY = "identity";
var BASE = "base";
var TYPE = "type";
var ENUMERATION = "enumeration";
var PATH = "path";
var REQUIRE_INSTANCE = "require-instance";
var ENUM = "enum";
var STATUS = "status";
var BIT = "bit";
var POSITION = "position";
var PATTERN = "pattern";
var MODIFIER = "modifier";
var LENGTH = "length";
var FRACTION_DIGITS = "fraction-digits";
var RANGE = "range";
var GROUPING = "grouping";
var USES = "uses";
var REFINE = "refine";
var CONTAINER = "container";
var LIST = "list";
var LEAF = "leaf";
var LEAF_LIST = "leaf-list";
var ANYDATA = "anydata";
var ANYXML = "anyxml";
var CHOICE = "choice";
var CASE = "case";
var MUST = "must";
var WHEN = "when";
var PRESENCE = "presence";
var KEY = "key";
var MIN_ELEMENTS = "min-elements";
var MAX_ELEMENTS = "max-elements";
var ORDERED_BY = "ordered-by";
var MANDATORY = "mandatory";
var CONFIG = "config";
var DEFAULT = "default";
var ERROR_MESSAGE = "error-message";
var ERROR_APP_TAG = "error-app-tag";
var TRUE = "true";
var FALSE = "false";
var IMPORT = "import";
var INCLUDE = "include";
var REVISION_DATE = "revision-date";
var FEATURE = "feature";
var IF_FEATURE = "if-feature";
var AUGMENT = "augment";
var SUBMODULE = "submodule";
var BELONGS_TO = "belongs-to";
var REFERENCE = "reference";
var ARGUMENT = "argument";
var YIN_ELEMENT = "yin-element";
var DEVIATION = "deviation";
var EXTENSION = "extension";
var RPC = "rpc";
var ACTION = "action";
var NOTIFICATION = "notification";
var INPUT = "input";
var OUTPUT = "output";

// src/xpath/tokenizer.ts
var OPERATORS = ["<=", ">=", "!=", "==", "//", "=", "<", ">", "+", "-", "*", "/"];
function tokenizeXPath(expr) {
  const tokens = [];
  let position = 0;
  const add = (kind, value, at = position) => {
    tokens.push({ kind, value, position: at });
  };
  while (position < expr.length) {
    const ch = expr[position];
    if (/\s/.test(ch)) {
      position += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
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
    if (/\d/.test(ch) || ch === "-" && /\d/.test(expr[position + 1] ?? "")) {
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

// src/xpath/parser.ts
var COMPARISON_OPS = /* @__PURE__ */ new Set(["=", "!=", "<", ">", "<=", ">="]);
var ADDITIVE_OPS = /* @__PURE__ */ new Set(["+", "-"]);
var XPathParser = class {
  constructor(expression) {
    this.expression = expression;
    this.tokens = tokenizeXPath(expression);
  }
  expression;
  tokens;
  position = 0;
  parse() {
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
  current() {
    return this.tokens[this.position] ?? { kind: "eof", value: "", position: this.expression.length };
  }
  consume(expectedKind) {
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
  isKeyword(value) {
    const token = this.current();
    return token.kind === "identifier" && token.value.toLowerCase() === value.toLowerCase();
  }
  parseExpression() {
    return this.parseLogicalOr();
  }
  parseLogicalOr() {
    let left = this.parseLogicalAnd();
    while (this.isKeyword("or")) {
      this.consume();
      const right = this.parseLogicalAnd();
      left = { kind: "binary", operator: "or", left, right };
    }
    return left;
  }
  parseLogicalAnd() {
    let left = this.parseComparison();
    while (this.isKeyword("and")) {
      this.consume();
      const right = this.parseComparison();
      left = { kind: "binary", operator: "and", left, right };
    }
    return left;
  }
  parseComparison() {
    let left = this.parseAdditive();
    const token = this.current();
    if (token.kind === "operator" && COMPARISON_OPS.has(token.value)) {
      const op = this.consume("operator").value;
      const right = this.parseAdditive();
      left = { kind: "binary", operator: op, left, right };
    }
    return left;
  }
  parseAdditive() {
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
  parseMultiplicative() {
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
  parseUnary() {
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
  parsePrimary() {
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
          const values = [first.value];
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
  parseFunctionCall() {
    const name = this.consume("identifier").value;
    this.consume("paren_open");
    const args = [];
    if (this.current().kind !== "paren_close") {
      args.push(this.parseExpression());
      while (this.current().kind === "comma") {
        this.consume("comma");
        args.push(this.parseExpression());
      }
    }
    this.consume("paren_close");
    const node = { kind: "function", name, args };
    return node;
  }
  parsePath(isAbsolute, firstStep, allowPredicate = true) {
    const segments = [];
    const pushStep = (step) => {
      const segment = { step };
      segments.push(segment);
      while (this.current().kind === "bracket_open") {
        if (!allowPredicate) {
          throw new XPathSyntaxError("Predicates are not allowed in this path context", {
            expression: this.expression,
            position: this.current().position
          });
        }
        this.consume("bracket_open");
        const pred = this.parseExpression();
        if (segment.predicate === void 0) {
          segment.predicate = pred;
        } else {
          segment.predicate = { kind: "binary", operator: "and", left: segment.predicate, right: pred };
        }
        this.consume("bracket_close");
      }
      if (this.current().kind === "slash") {
        this.consume("slash");
        return true;
      }
      return false;
    };
    if (firstStep !== void 0) {
      pushStep(firstStep);
    }
    while (this.current().kind === "dot" || this.current().kind === "dotdot" || this.current().kind === "identifier") {
      const step = this.consume().value;
      if (!pushStep(step)) {
        break;
      }
    }
    const node = { kind: "path", segments, isAbsolute };
    return node;
  }
  parsePathExpression(options = {}) {
    const allowPredicate = options.allowPredicate ?? true;
    if (this.current().kind === "eof") {
      throw new XPathSyntaxError("Empty path expression", {
        expression: this.expression,
        position: 0
      });
    }
    let isAbsolute = false;
    if (this.current().kind === "slash") {
      isAbsolute = true;
      this.consume("slash");
    }
    const node = this.parsePath(isAbsolute, void 0, allowPredicate);
    const token = this.current();
    if (token.kind !== "eof") {
      throw new XPathSyntaxError(`Unexpected token: ${token.value || token.kind}`, {
        expression: this.expression,
        position: token.position
      });
    }
    return node;
  }
};
function parseXPath(expression) {
  return new XPathParser(expression).parse();
}
function parseXPathPath(expression, options = {}) {
  return new XPathParser(expression).parsePathExpression(options);
}

// src/core/ast.ts
var YangStatementList = class {
  statements;
  constructor(statements = []) {
    this.statements = statements;
  }
  find_statement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
  findStatement(name) {
    return this.find_statement(name);
  }
  get_all_leaves() {
    const leaves = [];
    for (const stmt of this.statements) {
      leaves.push(...this.collectLeaves(stmt));
    }
    return leaves;
  }
  getAllLeaves() {
    return this.get_all_leaves();
  }
  collectLeaves(stmt) {
    if (stmt instanceof YangLeafStmt) {
      return [stmt];
    }
    if (stmt instanceof YangContainerStmt || stmt instanceof YangListStmt) {
      const leaves = [];
      for (const child of stmt.statements) {
        leaves.push(...this.collectLeaves(child));
      }
      return leaves;
    }
    return [];
  }
};
var YangStatement2 = class extends YangStatementList {
  keyword;
  name;
  description;
  reference;
  constructor(init = {}) {
    super(init.statements ?? []);
    this.keyword = init.keyword ?? "";
    this.name = init.name ?? "";
    this.description = init.description ?? "";
    this.reference = init.reference ?? "";
  }
  get_schema_node() {
    return void 0;
  }
  getSchemaNode() {
    return this.get_schema_node();
  }
  child_names(_data) {
    return this.name ? /* @__PURE__ */ new Set([this.name]) : /* @__PURE__ */ new Set();
  }
  childNames(data) {
    return this.child_names(data);
  }
};
var YangStatementWithMust = class extends YangStatement2 {
  must_statements;
  constructor(init = {}) {
    super(init);
    this.must_statements = init.must_statements ?? [];
  }
};
var YangStatementWithWhen = class extends YangStatement2 {
  when;
  if_features;
  /** RFC 7950 §7.21.1; undefined means inherit from parent. */
  config;
  constructor(init = {}) {
    super(init);
    this.when = init.when;
    this.if_features = init.if_features ?? [];
    this.config = init.config;
  }
  get_schema_node() {
    return this.name || void 0;
  }
};
var YangTypedefStmt = class extends YangStatement2 {
  type;
  default;
  constructor(init = {}) {
    super(init);
    this.keyword = "typedef";
    this.type = init.type;
    this.default = init.default;
  }
  get_schema_node() {
    return this.name || void 0;
  }
};
var YangIdentityStmt = class extends YangStatement2 {
  bases;
  if_features;
  constructor(init = {}) {
    super(init);
    this.keyword = "identity";
    this.bases = init.bases ?? [];
    this.if_features = init.if_features ?? [];
  }
  get_schema_node() {
    return void 0;
  }
};
var YangBitStmt = class {
  name;
  position;
  constructor(init = {}) {
    this.name = init.name ?? "";
    this.position = init.position;
  }
};
var YangPatternSpec = class {
  pattern;
  invert_match;
  error_message;
  error_app_tag;
  constructor(init = {}) {
    this.pattern = init.pattern ?? "";
    this.invert_match = init.invert_match ?? false;
    this.error_message = init.error_message;
    this.error_app_tag = init.error_app_tag;
  }
};
var YangTypeStmt = class {
  name;
  patterns;
  length;
  range;
  fraction_digits;
  enums;
  bits;
  types;
  path;
  require_instance;
  identityref_bases;
  constructor(init = {}) {
    this.name = init.name ?? "";
    this.patterns = init.patterns ?? [];
    this.length = init.length;
    this.range = init.range;
    this.fraction_digits = init.fraction_digits;
    this.enums = init.enums ?? [];
    this.bits = init.bits ?? [];
    this.types = init.types ?? [];
    this.path = init.path;
    this.require_instance = init.require_instance ?? true;
    this.identityref_bases = init.identityref_bases ?? [];
  }
};
var YangContainerStmt = class extends YangStatementWithWhen {
  must_statements;
  presence;
  constructor(init = {}) {
    super(init);
    this.keyword = "container";
    this.must_statements = init.must_statements ?? [];
    this.presence = init.presence;
  }
};
var YangNotificationStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super(init);
    this.keyword = "notification";
  }
};
var YangInputStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super({ name: "input", ...init });
    this.keyword = "input";
  }
};
var YangOutputStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super({ name: "output", ...init });
    this.keyword = "output";
  }
};
var YangRpcStmt = class extends YangStatementWithWhen {
  must_statements;
  constructor(init = {}) {
    super(init);
    this.keyword = "rpc";
    this.must_statements = init.must_statements ?? [];
  }
};
var YangListStmt = class extends YangStatementWithWhen {
  must_statements;
  key;
  min_elements;
  max_elements;
  constructor(init = {}) {
    super(init);
    this.keyword = "list";
    this.must_statements = init.must_statements ?? [];
    this.key = init.key;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
  }
};
var YangLeafStmt = class extends YangStatementWithWhen {
  must_statements;
  type;
  mandatory;
  default;
  constructor(init = {}) {
    super(init);
    this.keyword = "leaf";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.mandatory = init.mandatory ?? false;
    this.default = init.default;
  }
};
var YangLeafListStmt = class extends YangStatementWithWhen {
  must_statements;
  type;
  min_elements;
  max_elements;
  defaults;
  constructor(init = {}) {
    super(init);
    this.keyword = "leaf-list";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.defaults = init.defaults ?? [];
  }
};
var YangAnydataStmt = class extends YangStatementWithWhen {
  must_statements;
  mandatory;
  constructor(init = {}) {
    super(init);
    this.keyword = "anydata";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
};
var YangAnyxmlStmt = class extends YangStatementWithWhen {
  must_statements;
  mandatory;
  constructor(init = {}) {
    super(init);
    this.keyword = "anyxml";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
};
var YangExtensionStmt = class extends YangStatement2 {
  argument_name;
  argument_yin_element;
  apply_callback;
  constructor(init = {}) {
    super(init);
    this.keyword = "extension";
    this.argument_name = init.argument_name ?? "";
    this.argument_yin_element = init.argument_yin_element;
    this.apply_callback = init.apply_callback;
  }
  apply(invocation, options) {
    if (!this.apply_callback) {
      return invocation;
    }
    return this.apply_callback(invocation, options.context_module);
  }
  get_schema_node() {
    return void 0;
  }
};
var YangExtensionInvocationStmt = class extends YangStatementWithWhen {
  must_statements;
  prefix;
  resolved_module;
  resolved_extension;
  argument;
  constructor(init) {
    super(init);
    this.keyword = "extension-invocation";
    this.must_statements = init.must_statements ?? [];
    this.prefix = init.prefix;
    this.resolved_module = init.resolved_module;
    this.resolved_extension = init.resolved_extension;
    this.argument = init.argument;
    if (!this.prefix) {
      throw new Error("extension invocation requires a non-empty prefix");
    }
    if (!this.resolved_module) {
      throw new Error("extension invocation requires resolved_module");
    }
    if (!this.resolved_extension) {
      throw new Error("extension invocation requires resolved_extension");
    }
  }
  get_schema_node() {
    return void 0;
  }
};
var YangParsedXPathBase = class {
  expression;
  description;
  ast;
  constructor(init) {
    this.expression = init.expression;
    this.description = init.description ?? "";
    if (this.expression) {
      this.ast = parseXPath(this.expression);
    }
  }
};
var YangMustStmt = class extends YangParsedXPathBase {
  error_message;
  constructor(init) {
    super(init);
    this.error_message = init.error_message ?? "";
  }
};
var YangWhenStmt = class extends YangParsedXPathBase {
  evaluate_with_parent_context;
  constructor(init) {
    super(init);
    this.evaluate_with_parent_context = init.evaluate_with_parent_context ?? false;
  }
  get condition() {
    return this.expression;
  }
};
var YangGroupingStmt = class extends YangStatement2 {
  constructor(init = {}) {
    super(init);
    this.keyword = "grouping";
  }
};
var YangUsesStmt = class extends YangStatementWithWhen {
  grouping_name;
  refines;
  augmentations;
  constructor(init = {}) {
    super(init);
    this.keyword = "uses";
    this.grouping_name = init.grouping_name ?? "";
    this.refines = init.refines ?? [];
    this.augmentations = init.augmentations ?? [];
  }
  get_schema_node() {
    return void 0;
  }
};
var YangAugmentStmt = class extends YangStatementWithWhen {
  augment_path;
  constructor(init = {}) {
    super(init);
    this.keyword = "augment";
    this.augment_path = init.augment_path ?? "";
  }
  get_schema_node() {
    return void 0;
  }
};
var YangRefineStmt = class extends YangStatementWithMust {
  target_path;
  type;
  min_elements;
  max_elements;
  refined_defaults;
  refined_mandatory;
  refined_config;
  if_features;
  constructor(init = {}) {
    super(init);
    this.keyword = "refine";
    this.target_path = init.target_path ?? "";
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.refined_defaults = init.refined_defaults ?? [];
    this.refined_mandatory = init.refined_mandatory;
    this.refined_config = init.refined_config;
    this.if_features = init.if_features ?? [];
  }
};
var YangChoiceStmt = class extends YangStatementWithWhen {
  mandatory;
  cases;
  constructor(init = {}) {
    super(init);
    this.keyword = "choice";
    this.mandatory = init.mandatory ?? false;
    this.cases = init.cases ?? [];
  }
  child_names(data) {
    for (const c of this.cases) {
      if (c.statements.some((s) => s.name && s.name in data)) {
        return new Set(c.statements.map((s) => s.name).filter((name) => Boolean(name)));
      }
    }
    return /* @__PURE__ */ new Set();
  }
  validate_case_unique_child_names() {
    const seen = /* @__PURE__ */ new Map();
    for (const c of this.cases) {
      for (const sub of c.statements) {
        const seg = sub.get_schema_node();
        if (!seg) {
          continue;
        }
        if (seen.has(seg)) {
          const prevCase = seen.get(seg);
          throw new YangSemanticError(
            `Choice '${this.name}': schema node '${seg}' appears in case '${prevCase}' and again in case '${c.name}' (RFC 7950: names of nodes in the cases of a choice must be unique).`
          );
        }
        seen.set(seg, c.name);
      }
    }
  }
};
var YangCaseStmt = class extends YangStatementWithWhen {
  constructor(init = {}) {
    super(init);
    this.keyword = "case";
  }
  child_names(_data) {
    return new Set(this.statements.map((s) => s.name).filter((name) => Boolean(name)));
  }
};

// src/parser/statements/anydata.ts
var AnydataStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_anydata(tokens, context) {
    tokens.consume(ANYDATA);
    const name = tokens.consume();
    const stmt = new YangAnydataStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/anyxml.ts
var AnyxmlStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_anyxml(tokens, context) {
    tokens.consume(ANYXML);
    const name = tokens.consume();
    const stmt = new YangAnyxmlStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/metadata-substatements.ts
function withMetadataSubstatements(parsers, dispatch) {
  const out = { ...dispatch };
  out[DESCRIPTION] ??= (tokens, context) => {
    parsers.parse_description(tokens, context);
  };
  out[REFERENCE] ??= (tokens, context) => {
    parsers.parse_reference(tokens, context);
  };
  out[STATUS] ??= (tokens, context) => {
    parsers.parse_status_ignored(tokens, context);
  };
  return out;
}
function withDataNodeSubstatements(parsers, dispatch) {
  const out = withMetadataSubstatements(parsers, dispatch);
  out[CONFIG] ??= (tokens, context) => {
    parsers.parse_config(tokens, context);
  };
  out[STATUS] ??= (tokens, context) => {
    parsers.parse_status_ignored(tokens, context);
  };
  return out;
}

// src/parser/statements/augment.ts
var AugmentStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
    this.augmentBodyDispatch = withDataNodeSubstatements(this.parsers, {
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [CONTAINER]: (tokens, context) => {
        this.parsers.container_parser.parse_container(tokens, context);
      },
      [LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [CHOICE]: (tokens, context) => {
        this.parsers.choice_parser.parse_choice(tokens, context);
      },
      [CASE]: (tokens, context) => {
        this.parsers.choice_parser.parse_case(tokens, context);
      },
      [ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [NOTIFICATION]: (tokens, context) => {
        this.parsers.notification_parser.parse_notification(tokens, context);
      }
    });
  }
  parsers;
  augmentBodyDispatch;
  parse_augment(tokens, context) {
    tokens.consume(AUGMENT);
    const augment_path = this.parsers.parse_string_concatenation(tokens);
    const stmt = new YangAugmentStmt({ name: "augment", augment_path });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const handler = this.parsers.substatement_handler(tokens, this.augmentBodyDispatch);
        if (handler) {
          handler(tokens, child);
        } else if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
          this.parsers.parse_prefixed_extension_statement_public(tokens, child);
        } else if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, "augment")) {
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    const parent = context.current_parent;
    if (parent instanceof YangUsesStmt) {
      parent.augmentations.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/bits.ts
var BitsStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_type_bit(tokens, context, type_stmt) {
    tokens.consume(BIT);
    const name = tokens.consume();
    let position;
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        if (tokens.peek() === POSITION) {
          tokens.consume(POSITION);
          position = Number.parseInt(tokens.consume_type("INTEGER" /* INTEGER */), 10);
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    type_stmt.bits.push(new YangBitStmt({ name, position }));
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  finalize_bits_type(type_stmt) {
    let max = -1;
    for (const bit of type_stmt.bits) {
      if (bit.position === void 0) {
        bit.position = max + 1;
      }
      max = Math.max(max, bit.position);
    }
  }
};

// src/parser/statements/choice.ts
var INLINE_CHOICE_SCHEMA_KEYS = /* @__PURE__ */ new Set([
  LEAF,
  LEAF_LIST,
  CONTAINER,
  LIST,
  ANYDATA,
  ANYXML,
  CHOICE
]);
var ChoiceStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
    this.choiceSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [CASE]: (tokens, context) => {
        this.parse_case(tokens, context);
      },
      [MANDATORY]: (tokens, context) => {
        this.parse_choice_mandatory(tokens, context);
      }
    });
    this.caseSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [CONTAINER]: (tokens, context) => {
        this.parsers.container_parser.parse_container(tokens, context);
      },
      [LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [CHOICE]: (tokens, context) => {
        this.parse_choice(tokens, context);
      }
    });
  }
  parsers;
  choiceSubstatementDispatch;
  caseSubstatementDispatch;
  parse_choice(tokens, context) {
    tokens.consume(CHOICE);
    const name = tokens.consume();
    const stmt = new YangChoiceStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parse_choice_substatement(tokens, child, name);
      }
      tokens.consume_type("}" /* RBRACE */);
      stmt.validate_case_unique_child_names();
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
  parse_choice_substatement(tokens, context, choiceName) {
    const unsupported = `choice '${choiceName}'`;
    const handler = this.parsers.substatement_handler(tokens, this.choiceSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    const key = this.parsers.dispatch_key(tokens);
    if (typeof key === "string" && INLINE_CHOICE_SCHEMA_KEYS.has(key)) {
      this.parse_choice_implicit_case(tokens, context);
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupported);
  }
  parse_choice_implicit_case(tokens, context) {
    const choice = context.current_parent;
    if (!(choice instanceof YangChoiceStmt)) {
      tokens.syntaxError("internal: implicit choice case outside choice body");
    }
    const caseStmt = new YangCaseStmt({ name: "" });
    const caseCtx = context.push_parent(caseStmt);
    const handler = this.parsers.substatement_handler(tokens, this.caseSubstatementDispatch);
    if (!handler) {
      tokens.syntaxError(`internal: unsupported implicit choice schema '${String(tokens.peek())}'`);
    }
    handler(tokens, caseCtx);
    if (caseStmt.statements.length === 0) {
      tokens.syntaxError("Expected a schema node in implicit choice case (RFC 7950 \xA77.9.2)");
    }
    const first = caseStmt.statements[0];
    const caseName = first.name || first.get_schema_node();
    if (!caseName) {
      tokens.syntaxError("Implicit choice case requires a named schema node (RFC 7950 \xA77.9.2)");
    }
    caseStmt.name = caseName;
    choice.cases.push(caseStmt);
  }
  parse_case(tokens, context) {
    tokens.consume(CASE);
    const name = tokens.consume();
    const stmt = new YangCaseStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parse_case_substatement(tokens, child, name);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    const parent = context.current_parent;
    if (parent instanceof YangChoiceStmt) {
      parent.cases.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
  parse_case_substatement(tokens, context, caseName) {
    const unsupported = `case '${caseName}'`;
    const handler = this.parsers.substatement_handler(tokens, this.caseSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (this.parsers.skip_unsupported_if_present(tokens, unsupported)) {
      return;
    }
    this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupported);
  }
  parse_choice_mandatory(tokens, context) {
    tokens.consume(MANDATORY);
    const [, tt] = tokens.consume_oneof([TRUE, FALSE]);
    const parent = context.current_parent;
    if (parent instanceof YangChoiceStmt) {
      parent.mandatory = tt === TRUE;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/container.ts
var ContainerStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
    this.containerSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [PRESENCE]: (tokens, context) => {
        this.parsers.parse_presence(tokens, context);
      },
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [CONTAINER]: (tokens, context) => {
        this.parse_container(tokens, context);
      },
      [LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [CHOICE]: (tokens, context) => {
        this.parsers.choice_parser.parse_choice(tokens, context);
      },
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [NOTIFICATION]: (tokens, context) => {
        this.parsers.notification_parser.parse_notification(tokens, context);
      }
    });
  }
  parsers;
  containerSubstatementDispatch;
  parseContainerSubstatement(tokens, context, containerName) {
    const handler = this.parsers.substatement_handler(tokens, this.containerSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `container '${containerName}'`)) {
    }
  }
  parse_container(tokens, context) {
    tokens.consume(CONTAINER);
    const name = tokens.consume();
    const stmt = new YangContainerStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parseContainerSubstatement(tokens, child, name);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/extension.ts
var ExtensionStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_extension_stmt(tokens, context) {
    tokens.consume(EXTENSION);
    const name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    const ext = new YangExtensionStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(ext);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === ARGUMENT) {
          this.parse_extension_argument_stmt(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    context.module.extensions[name] = ext;
    this.parsers.add_to_parent_or_module(context, ext);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return ext;
  }
  parse_extension_argument_stmt(tokens, context) {
    tokens.consume(ARGUMENT);
    const arg = tokens.peek_type() === "STRING" /* STRING */ ? tokens.consume_type("STRING" /* STRING */) : tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    const parent = context.current_parent;
    if (parent instanceof YangExtensionStmt) {
      parent.argument_name = arg;
    }
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        if (tokens.peek() === YIN_ELEMENT) {
          tokens.consume(YIN_ELEMENT);
          const [, tt] = tokens.consume_oneof([TRUE, FALSE]);
          parent.argument_yin_element = tt === TRUE;
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/feature.ts
var FeatureStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_feature_stmt(tokens, context) {
    tokens.consume(FEATURE);
    const name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    (context.module.features ??= /* @__PURE__ */ new Set()).add(name);
    const featParent = { if_features: [] };
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(featParent);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    if (featParent.if_features.length > 0) {
      const mod = context.module;
      const fif = mod.feature_if_features ??= {};
      fif[name] = [...featParent.if_features];
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_if_feature_stmt(tokens, context) {
    tokens.consume(IF_FEATURE);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const parent = context.current_parent;
    if (parent && Array.isArray(parent.if_features)) {
      parent.if_features.push(expression);
    }
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, context);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/grouping.ts
var GroupingStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_grouping(tokens, context) {
    tokens.consume(GROUPING);
    const name = tokens.consume();
    const stmt = new YangGroupingStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    context.module.groupings[name] = stmt;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/identity.ts
var IdentityStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_identity(tokens, context) {
    tokens.consume(IDENTITY);
    const name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    const stmt = new YangIdentityStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        if (tokens.peek() === BASE) {
          this.parse_identity_base(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    context.module.identities[name] = stmt;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_identity_base(tokens, context) {
    tokens.consume(BASE);
    const base = this.parsers.consume_qname_from_identifier(tokens);
    const parent = context.current_parent;
    if (parent instanceof YangIdentityStmt) {
      parent.bases.push(base);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/leaf.ts
var LeafStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_leaf(tokens, context) {
    tokens.consume(LEAF);
    const name = tokens.consume();
    const stmt = new YangLeafStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/leaf_list.ts
var LeafListStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_leaf_list(tokens, context) {
    tokens.consume(LEAF_LIST);
    const name = tokens.consume();
    const stmt = new YangLeafListStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/list.ts
var ListStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_list(tokens, context) {
    tokens.consume(LIST);
    const name = tokens.consume();
    const stmt = new YangListStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/module.ts
var ModuleStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_module(tokens, context) {
    tokens.consume(MODULE);
    context.module.name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    tokens.consume_type("{" /* LBRACE */);
    while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
      this.parsers.parseStatement(tokens, context);
    }
    tokens.consume_type("}" /* RBRACE */);
  }
  parse_yang_version(tokens, context) {
    tokens.consume(YANG_VERSION);
    const [version] = tokens.consume_oneof(["IDENTIFIER" /* IDENTIFIER */, "DOTTED_NUMBER" /* DOTTED_NUMBER */]);
    context.module.yang_version = version;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_namespace(tokens, context) {
    tokens.consume(NAMESPACE);
    context.module.namespace = tokens.consume_type("STRING" /* STRING */);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_prefix(tokens, context) {
    tokens.consume(PREFIX);
    const tt = this.parsers.dispatch_key(tokens);
    context.module.prefix = tt === "STRING" /* STRING */ ? tokens.consume_type("STRING" /* STRING */) : tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_organization(tokens, context) {
    tokens.consume(ORGANIZATION);
    context.module.organization = tokens.consume_type("STRING" /* STRING */);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_contact(tokens, context) {
    tokens.consume(CONTACT);
    context.module.contact = tokens.consume_type("STRING" /* STRING */);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_import_stmt(tokens, context) {
    tokens.consume(IMPORT);
    const moduleName2 = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    let localPrefix;
    let revisionDate;
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === PREFIX) {
          tokens.consume(PREFIX);
          localPrefix = tokens.peek_type() === "STRING" /* STRING */ ? tokens.consume_type("STRING" /* STRING */) : tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
          tokens.consume_if_type(";" /* SEMICOLON */);
          continue;
        }
        if (tt === REVISION_DATE) {
          revisionDate = this.parsers.revision_parser.parse_revision_date_statement(tokens);
          continue;
        }
        this.skip_nested_statement(tokens);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    if (!localPrefix || localPrefix.trim().length === 0) {
      throw new YangSemanticError(`Import '${moduleName2}' is missing required prefix substatement`);
    }
    this.parsers.register_import(context, moduleName2, localPrefix, revisionDate, tokens);
  }
  parse_include_stmt(tokens, context) {
    tokens.consume(INCLUDE);
    tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, context);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_prefix_value_stmt(tokens) {
    tokens.consume(PREFIX);
    if (tokens.peek_type() === "STRING" /* STRING */) {
      tokens.consume_type("STRING" /* STRING */);
    } else {
      tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  skip_nested_statement(tokens) {
    let depth = 0;
    while (tokens.has_more()) {
      const tt = this.parsers.dispatch_key(tokens);
      if (tt === "{" /* LBRACE */) {
        depth += 1;
        tokens.consume_type("{" /* LBRACE */);
        continue;
      }
      if (tt === "}" /* RBRACE */) {
        if (depth === 0) {
          return;
        }
        depth -= 1;
        tokens.consume_type("}" /* RBRACE */);
        continue;
      }
      if (tt === ";" /* SEMICOLON */ && depth === 0) {
        tokens.consume_type(";" /* SEMICOLON */);
        return;
      }
      tokens.consume();
    }
  }
};

// src/parser/statements/notification.ts
var NotificationStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_notification(tokens, context) {
    tokens.consume(NOTIFICATION);
    const name = tokens.consume();
    const stmt = new YangNotificationStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/rpc.ts
var RpcStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
    this.ioSubstatementDispatch = withMetadataSubstatements(this.parsers, {
      [TYPEDEF]: (tokens, context) => {
        this.parsers.typedef_parser.parse_typedef(tokens, context);
      },
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [CONTAINER]: (tokens, context) => {
        this.parsers.container_parser.parse_container(tokens, context);
      },
      [LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [CHOICE]: (tokens, context) => {
        this.parsers.choice_parser.parse_choice(tokens, context);
      },
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      }
    });
    this.rpcSubstatementDispatch = withMetadataSubstatements(this.parsers, {
      [WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [INPUT]: (tokens, context) => {
        this.parse_input(tokens, context);
      },
      [OUTPUT]: (tokens, context) => {
        this.parse_output(tokens, context);
      },
      [IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      }
    });
  }
  parsers;
  ioSubstatementDispatch;
  rpcSubstatementDispatch;
  parseIoSubstatement(tokens, context, blockName) {
    const handler = this.parsers.substatement_handler(tokens, this.ioSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `${blockName} block`)) {
    }
  }
  parseIoBlock(tokens, context, keyword, ioStmt) {
    tokens.consume(keyword);
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(ioStmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parseIoSubstatement(tokens, child, keyword);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, ioStmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return ioStmt;
  }
  parse_input(tokens, context) {
    return this.parseIoBlock(tokens, context, INPUT, new YangInputStmt());
  }
  parse_output(tokens, context) {
    return this.parseIoBlock(tokens, context, OUTPUT, new YangOutputStmt());
  }
  parseRpcSubstatement(tokens, context, rpcName) {
    const handler = this.parsers.substatement_handler(tokens, this.rpcSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `rpc '${rpcName}'`)) {
    }
  }
  parse_rpc(tokens, context) {
    tokens.consume(RPC);
    const rpcName = tokens.consume();
    const rpcStmt = new YangRpcStmt({ name: rpcName });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(rpcStmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parseRpcSubstatement(tokens, child, rpcName);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, rpcStmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return rpcStmt;
  }
};

// src/parser/statements/must.ts
var MustStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_must(tokens, context) {
    tokens.consume(MUST);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const stmt = new YangMustStmt({ expression });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        if (tokens.peek() === ERROR_MESSAGE) {
          this.parse_must_error_message(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    const parent = context.current_parent;
    if (Array.isArray(parent?.must_statements)) {
      parent.must_statements.push(stmt);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
  parse_must_error_message(tokens, context) {
    tokens.consume(ERROR_MESSAGE);
    const parent = context.current_parent;
    if (parent instanceof YangMustStmt) {
      parent.error_message = tokens.consume_type("STRING" /* STRING */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/refine.ts
var RefineStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_refine(tokens, context) {
    tokens.consume(REFINE);
    const parts = [tokens.consume()];
    while (tokens.has_more() && tokens.peek_type() === "/" /* SLASH */) {
      tokens.consume_type("/" /* SLASH */);
      parts.push(tokens.consume());
    }
    const target_path = parts.join("/");
    const stmt = new YangRefineStmt({ name: "refine", target_path });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    if (context.current_parent instanceof YangUsesStmt) {
      context.current_parent.refines.push(stmt);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/revision.ts
var RevisionStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_revision(tokens, context) {
    tokens.consume(REVISION);
    let date = "";
    if (tokens.peek_type() === "STRING" /* STRING */) {
      date = tokens.consume_type("STRING" /* STRING */);
    } else {
      while (tokens.has_more() && !["{" /* LBRACE */, ";" /* SEMICOLON */].includes(tokens.peek_type())) {
        date += tokens.consume();
      }
    }
    const rev = {
      date,
      description: "",
      reference: ""
    };
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        if (tokens.peek() === DESCRIPTION) {
          tokens.consume(DESCRIPTION);
          rev.description = tokens.consume_type("STRING" /* STRING */);
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else if (tokens.peek() === REFERENCE) {
          tokens.consume(REFERENCE);
          rev.reference = this.parsers.parse_string_argument(tokens);
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    (context.module.revisions ??= []).push(rev);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_revision_date_statement(tokens) {
    tokens.consume(REVISION_DATE);
    let date = "";
    if (tokens.peek_type() === "STRING" /* STRING */) {
      date = tokens.consume_type("STRING" /* STRING */);
    } else {
      while (tokens.has_more() && tokens.peek_type() !== ";" /* SEMICOLON */) {
        date += tokens.consume();
      }
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    return date;
  }
};

// src/parser/statements/submodule.ts
var SubmoduleStatementParser = class {
  constructor(parsers, module_parser) {
    this.parsers = parsers;
    this.module_parser = module_parser;
  }
  parsers;
  module_parser;
  parse_submodule(tokens, context) {
    tokens.consume(SUBMODULE);
    context.module.name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    tokens.consume_type("{" /* LBRACE */);
    while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
      if (tokens.peek() === BELONGS_TO) {
        this.parse_belongs_to(tokens, context);
      } else {
        this.parsers.parseStatement(tokens, context);
      }
    }
    tokens.consume_type("}" /* RBRACE */);
  }
  parse_belongs_to(tokens, context) {
    tokens.consume(BELONGS_TO);
    context.module.belongs_to_module = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    tokens.consume_type("{" /* LBRACE */);
    while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
      if (tokens.peek() === PREFIX) {
        this.module_parser.parse_prefix_value_stmt(tokens);
      } else {
        this.parsers.parseStatement(tokens, context);
      }
    }
    tokens.consume_type("}" /* RBRACE */);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/type.ts
var TypeStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_type(tokens, context) {
    tokens.consume(TYPE);
    const name = tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ ? this.parsers.consume_qname_from_identifier(tokens) : tokens.consume();
    const type_stmt = new YangTypeStmt({ name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(type_stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === PATTERN) {
          this.parse_type_pattern(tokens, child, type_stmt);
        } else if (tt === LENGTH) {
          this.parse_type_length(tokens, child, type_stmt);
        } else if (tt === RANGE) {
          this.parse_type_range(tokens, child, type_stmt);
        } else if (tt === FRACTION_DIGITS) {
          this.parse_type_fraction_digits(tokens, child, type_stmt);
        } else if (tt === ENUM) {
          this.parse_type_enum(tokens, child, type_stmt);
        } else if (tt === BIT) {
          this.parsers.bits_parser.parse_type_bit(tokens, child, type_stmt);
        } else if (tt === PATH) {
          this.parse_type_path(tokens, child, type_stmt);
        } else if (tt === REQUIRE_INSTANCE) {
          this.parse_type_require_instance(tokens, child, type_stmt);
        } else if (tt === BASE) {
          this.parse_type_base(tokens, child, type_stmt);
        } else if (tt === TYPE) {
          const nested = this.parse_type(tokens, child);
          type_stmt.types.push(nested);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
      if (type_stmt.name === ENUMERATION && type_stmt.enums.length === 0) {
        tokens.syntaxError("enumeration type must contain at least one enum statement");
      }
    }
    const parent = context.current_parent;
    if (parent && "type" in parent && !parent.type) {
      parent.type = type_stmt;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    return type_stmt;
  }
  parse_type_base(tokens, _context, type_stmt) {
    tokens.consume(BASE);
    type_stmt.identityref_bases.push(this.parsers.consume_qname_from_identifier(tokens));
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_pattern(tokens, _context, type_stmt) {
    tokens.consume(PATTERN);
    const pattern = this.parsers.parse_string_concatenation(tokens);
    let invertMatch = false;
    let patternErrorMessage;
    let patternErrorAppTag;
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === ERROR_MESSAGE) {
          tokens.consume(ERROR_MESSAGE);
          patternErrorMessage = this.parsers.parse_string_concatenation(tokens);
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else if (tt === ERROR_APP_TAG) {
          tokens.consume(ERROR_APP_TAG);
          patternErrorAppTag = this.parsers.parse_string_concatenation(tokens);
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else if (tt === MODIFIER) {
          tokens.consume(MODIFIER);
          invertMatch = tokens.consume() === "invert-match";
          tokens.consume_if_type(";" /* SEMICOLON */);
        } else {
          this.parsers.parseStatement(tokens, _context);
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    type_stmt.patterns.push(
      new YangPatternSpec({
        pattern,
        invert_match: invertMatch,
        error_message: patternErrorMessage,
        error_app_tag: patternErrorAppTag
      })
    );
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_length(tokens, _context, type_stmt) {
    tokens.consume(LENGTH);
    type_stmt.length = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_range(tokens, _context, type_stmt) {
    tokens.consume(RANGE);
    type_stmt.range = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_fraction_digits(tokens, _context, type_stmt) {
    tokens.consume(FRACTION_DIGITS);
    type_stmt.fraction_digits = Number.parseInt(tokens.consume_type("INTEGER" /* INTEGER */), 10);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_enum(tokens, _context, type_stmt) {
    tokens.consume(ENUM);
    type_stmt.enums.push(tokens.consume());
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        tokens.consume();
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_path(tokens, _context, type_stmt) {
    tokens.consume(PATH);
    const path = this.parsers.parse_string_argument(tokens);
    type_stmt.path = parseXPathPath(path);
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_type_require_instance(tokens, _context, type_stmt) {
    tokens.consume(REQUIRE_INSTANCE);
    const [, tt] = tokens.consume_oneof([TRUE, FALSE]);
    type_stmt.require_instance = tt === TRUE;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/statements/typedef.ts
var TypedefStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
    this.typedefBodyDispatch = withMetadataSubstatements(this.parsers, {
      [TYPE]: (tokens, context) => {
        this.parsers.type_parser.parse_type(tokens, context);
      },
      [DEFAULT]: (tokens, context) => {
        this.parsers.parse_typedef_default(tokens, context);
      }
    });
  }
  parsers;
  typedefBodyDispatch;
  parse_typedef(tokens, context) {
    tokens.consume(TYPEDEF);
    const name = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    const stmt = new YangTypedefStmt({ name });
    const unsupportedCtx = `typedef '${name}'`;
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        const handler = this.parsers.substatement_handler(tokens, this.typedefBodyDispatch);
        if (handler) {
          handler(tokens, child);
        } else if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupportedCtx)) {
        }
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    context.module.typedefs[name] = stmt;
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/uses.ts
var UsesStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_uses(tokens, context) {
    tokens.consume(USES);
    const grouping_name = tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ ? this.parsers.consume_qname_from_identifier(tokens) : tokens.consume();
    const stmt = new YangUsesStmt({ name: "uses", grouping_name });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(";" /* SEMICOLON */);
    return stmt;
  }
};

// src/parser/statements/when.ts
var WhenStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_when(tokens, context) {
    tokens.consume(WHEN);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const whenStmt = new YangWhenStmt({ expression });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const child = context.push_parent(whenStmt);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    if (context.current_parent instanceof YangStatementWithWhen) {
      context.current_parent.when = whenStmt;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
};

// src/parser/unsupported-skip.ts
var UNSUPPORTED_CONSTRUCT_TYPES = /* @__PURE__ */ new Set([DEVIATION, ACTION]);
function _consume_balanced_braces(tokens) {
  let depth = 0;
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === "{" /* LBRACE */) {
      depth += 1;
      tokens.consume_type("{" /* LBRACE */);
    } else if (pt === "}" /* RBRACE */) {
      depth -= 1;
      tokens.consume_type("}" /* RBRACE */);
      if (depth === 0) {
        return;
      }
    } else {
      tokens.consume();
    }
  }
}
function skip_unsupported_construct(tokens, { context }) {
  const tok = tokens.peek_token();
  if (!tok || !UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value)) {
    return;
  }
  const kw = tok.value;
  const [line_num, char_pos] = tokens.position();
  const where = tokens.filename ?? "<string>";
  console.warn(`Ignoring unsupported YANG statement '${kw}' (${context}) at ${where}:${line_num}:${char_pos}`);
  tokens.consume();
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === "{" /* LBRACE */) {
      _consume_balanced_braces(tokens);
      break;
    }
    if (pt === ";" /* SEMICOLON */) {
      tokens.consume_type(";" /* SEMICOLON */);
      return;
    }
    if (pt === "}" /* RBRACE */) {
      return;
    }
    tokens.consume();
  }
  tokens.consume_if_type(";" /* SEMICOLON */);
}
function is_unsupported_construct_start(tokens) {
  const tok = tokens.peek_token();
  return tok !== void 0 && UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value);
}
function skip_status_substatement(tokens) {
  tokens.consume(STATUS);
  if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */) {
    tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
  }
  tokens.consume_if_type(";" /* SEMICOLON */);
}

// src/parser/statement-parsers.ts
function serializedKeywordFromAstStatement(stmt) {
  if (typeof stmt.keyword === "string" && stmt.keyword.trim().length > 0) {
    return stmt.keyword;
  }
  throw new YangSemanticError("Internal error: cannot serialize AST statement without a keyword");
}
var StatementParsers = class {
  importResolver;
  anydata_parser = new AnydataStatementParser(this);
  anyxml_parser = new AnyxmlStatementParser(this);
  augment_parser = new AugmentStatementParser(this);
  bits_parser = new BitsStatementParser(this);
  choice_parser = new ChoiceStatementParser(this);
  container_parser = new ContainerStatementParser(this);
  extension_parser = new ExtensionStatementParser(this);
  feature_parser = new FeatureStatementParser(this);
  grouping_parser = new GroupingStatementParser(this);
  identity_parser = new IdentityStatementParser(this);
  leaf_parser = new LeafStatementParser(this);
  leaf_list_parser = new LeafListStatementParser(this);
  list_parser = new ListStatementParser(this);
  module_parser = new ModuleStatementParser(this);
  notification_parser = new NotificationStatementParser(this);
  rpc_parser = new RpcStatementParser(this);
  must_parser = new MustStatementParser(this);
  refine_parser = new RefineStatementParser(this);
  revision_parser = new RevisionStatementParser(this);
  submodule_parser = new SubmoduleStatementParser(this, this.module_parser);
  type_parser = new TypeStatementParser(this);
  typedef_parser = new TypedefStatementParser(this);
  uses_parser = new UsesStatementParser(this);
  when_parser = new WhenStatementParser(this);
  statementKeywordHandlers = {
    [LEAF]: (tokens, context) => this.fromAst(this.leaf_parser.parse_leaf(tokens, context)),
    [LEAF_LIST]: (tokens, context) => this.fromAst(this.leaf_list_parser.parse_leaf_list(tokens, context)),
    [CONTAINER]: (tokens, context) => this.fromAst(this.container_parser.parse_container(tokens, context)),
    [LIST]: (tokens, context) => this.fromAst(this.list_parser.parse_list(tokens, context)),
    [NOTIFICATION]: (tokens, context) => this.fromAst(this.notification_parser.parse_notification(tokens, context)),
    [RPC]: (tokens, context) => this.fromAst(this.rpc_parser.parse_rpc(tokens, context)),
    [ANYDATA]: (tokens, context) => this.fromAst(this.anydata_parser.parse_anydata(tokens, context)),
    [ANYXML]: (tokens, context) => this.fromAst(this.anyxml_parser.parse_anyxml(tokens, context)),
    [CHOICE]: (tokens, context) => this.fromAst(this.choice_parser.parse_choice(tokens, context)),
    [CASE]: () => {
      throw new YangSyntaxError("'case' is only valid as a substatement of 'choice' (RFC 7950)");
    },
    [INPUT]: () => {
      throw new YangSyntaxError("'input' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [OUTPUT]: () => {
      throw new YangSyntaxError("'output' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [TYPEDEF]: (tokens, context) => this.fromAst(this.typedef_parser.parse_typedef(tokens, context)),
    [TYPE]: (tokens, context) => this.fromType(this.type_parser.parse_type(tokens, context)),
    [USES]: (tokens, context) => this.fromAst(this.uses_parser.parse_uses(tokens, context)),
    [REFINE]: (tokens, context) => {
      this.refine_parser.parse_refine(tokens, context);
      return { __class__: "YangStatement", keyword: "refine", statements: [] };
    },
    [MUST]: (tokens, context) => this.fromMust(this.must_parser.parse_must(tokens, context)),
    [WHEN]: (tokens, context) => {
      this.when_parser.parse_when(tokens, context);
      return { __class__: "YangStatement", keyword: "when", statements: [] };
    },
    [EXTENSION]: (tokens, context) => this.fromAst(this.extension_parser.parse_extension_stmt(tokens, context)),
    [FEATURE]: (tokens, context) => {
      this.feature_parser.parse_feature_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "feature", statements: [] };
    },
    [IF_FEATURE]: (tokens, context) => {
      this.feature_parser.parse_if_feature_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "if-feature", statements: [] };
    },
    [IDENTITY]: (tokens, context) => {
      this.identity_parser.parse_identity(tokens, context);
      return { __class__: "YangStatement", keyword: "identity", statements: [] };
    },
    [GROUPING]: (tokens, context) => {
      this.grouping_parser.parse_grouping(tokens, context);
      return { __class__: "YangStatement", keyword: "grouping", statements: [] };
    },
    [AUGMENT]: (tokens, context) => this.fromAst(this.augment_parser.parse_augment(tokens, context)),
    [REVISION]: (tokens, context) => {
      this.revision_parser.parse_revision(tokens, context);
      return { __class__: "YangStatement", keyword: "revision", statements: [] };
    },
    [DESCRIPTION]: (tokens, context) => {
      const desc = this.parse_description(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "description",
        argument: desc,
        name: "description",
        statements: []
      };
    },
    [MANDATORY]: (tokens, context) => {
      this.parse_leaf_mandatory(tokens, context);
      return { __class__: "YangStatement", keyword: "mandatory", statements: [] };
    },
    [DEFAULT]: (tokens, context) => {
      this.parse_leaf_default(tokens, context);
      return { __class__: "YangStatement", keyword: "default", statements: [] };
    },
    [KEY]: (tokens, context) => {
      this.parse_list_key(tokens, context);
      return { __class__: "YangStatement", keyword: "key", statements: [] };
    },
    [MIN_ELEMENTS]: (tokens, context) => {
      this.parse_min_elements(tokens, context);
      return { __class__: "YangStatement", keyword: "min-elements", statements: [] };
    },
    [MAX_ELEMENTS]: (tokens, context) => {
      this.parse_max_elements(tokens, context);
      return { __class__: "YangStatement", keyword: "max-elements", statements: [] };
    },
    [ORDERED_BY]: (tokens, context) => {
      this.parse_ordered_by(tokens);
      return { __class__: "YangStatement", keyword: "ordered-by", statements: [] };
    },
    [PRESENCE]: (tokens, context) => {
      this.parse_presence(tokens, context);
      return { __class__: "YangStatement", keyword: "presence", statements: [] };
    },
    [REFERENCE]: (tokens, context) => {
      this.parse_reference(tokens, context);
      return { __class__: "YangStatement", keyword: "reference", statements: [] };
    },
    [CONFIG]: (tokens, context) => {
      this.parse_config(tokens, context);
      return { __class__: "YangStatement", keyword: "config", statements: [] };
    }
  };
  constructor(options = {}) {
    this.importResolver = options.importResolver;
  }
  dispatch_key(tokens) {
    return tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ ? tokens.peek() ?? "" : tokens.peek_type();
  }
  assertStatementStartAllowed(tokens, allowed, restrictionContext) {
    const set = allowed instanceof Set ? allowed : new Set(allowed);
    const kw = this.dispatch_key(tokens);
    if (set.has(kw)) {
      return;
    }
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      return;
    }
    const ctx = restrictionContext ? ` ${restrictionContext}` : "";
    const got = tokens.peek() ?? "<end>";
    const allowedLabels = [...set].map((t) => String(t)).sort().join(", ");
    throw new YangSyntaxError(
      `Invalid statement starting with '${got}'${ctx}. Allowed here: ${allowedLabels}; prefixed extension statements (identifier:keyword) are also allowed.`
    );
  }
  parseModule(tokens, context) {
    const root = this.parseStatement(tokens, context);
    if (root.keyword !== "module") {
      throw new YangSemanticError("Expected top-level 'module' statement");
    }
    return root;
  }
  /** Serialize an in-memory AST statement (e.g. under `grouping`) for module data / uses expansion. */
  serializeAstStatement(stmt) {
    return this.fromAst(stmt);
  }
  parseStatement(tokens, context, options) {
    if (options?.allowedStatementStarts) {
      this.assertStatementStartAllowed(tokens, options.allowedStatementStarts, options.restrictionContext);
    }
    const kw = this.dispatch_key(tokens);
    if (tokens.peek_type() === "IDENTIFIER" /* IDENTIFIER */ && tokens.peek_type_at(1) === ":" /* COLON */) {
      return this.parse_prefixed_extension_statement(tokens, context);
    }
    const handler = this.statementKeywordHandlers[kw];
    if (handler) {
      return handler(tokens, context);
    }
    return this.parse_statement_generic(tokens, context);
  }
  parse_statement_generic(tokens, context) {
    const tokenType = this.dispatch_key(tokens);
    if (tokenType === MODULE) {
      return this.parse_top_level_module(tokens, context);
    }
    if (tokenType === SUBMODULE) {
      this.submodule_parser.parse_submodule(tokens, context);
      return { __class__: "YangStatement", keyword: "submodule", statements: [] };
    }
    if (tokenType === YANG_VERSION) {
      this.module_parser.parse_yang_version(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "yang-version",
        argument: context.module.yang_version,
        name: "yang-version",
        statements: []
      };
    }
    if (tokenType === NAMESPACE) {
      this.module_parser.parse_namespace(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "namespace",
        argument: context.module.namespace,
        name: "namespace",
        statements: []
      };
    }
    if (tokenType === PREFIX) {
      this.module_parser.parse_prefix(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "prefix",
        argument: context.module.prefix,
        name: "prefix",
        statements: []
      };
    }
    if (tokenType === ORGANIZATION) {
      this.module_parser.parse_organization(tokens, context);
      return { __class__: "YangStatement", keyword: "organization", statements: [] };
    }
    if (tokenType === CONTACT) {
      this.module_parser.parse_contact(tokens, context);
      return { __class__: "YangStatement", keyword: "contact", statements: [] };
    }
    if (tokenType === IMPORT) {
      this.module_parser.parse_import_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "import", statements: [] };
    }
    if (tokenType === INCLUDE) {
      this.module_parser.parse_include_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "include", statements: [] };
    }
    if (this.skip_unsupported_if_present(tokens, "generic")) {
      return { __class__: "YangStatement", keyword: "unsupported", statements: [] };
    }
    const peek = tokens.peek();
    if (peek === INPUT || peek === OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }
    const first = tokens.consume();
    let keyword = first;
    if (tokens.peek_type() === ":" /* COLON */) {
      tokens.consume_type(":" /* COLON */);
      keyword = `${keyword}:${tokens.consume_type("IDENTIFIER" /* IDENTIFIER */)}`;
    }
    const argument = this.parse_argument(tokens);
    const statements = [];
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        statements.push(this.parseStatement(tokens, context));
      }
      tokens.consume_type("}" /* RBRACE */);
      tokens.consume_if_type(";" /* SEMICOLON */);
    } else {
      tokens.consume_if_type(";" /* SEMICOLON */);
    }
    const out = { __class__: "YangStatement", keyword, name: argument, argument, statements };
    if (keyword === "type") {
      out.type = this.extract_type_shape(out);
    }
    return out;
  }
  parse_argument(tokens) {
    const parts = [];
    while (tokens.has_more()) {
      const t = tokens.peek_type();
      if (t === ";" /* SEMICOLON */ || t === "{" /* LBRACE */) {
        break;
      }
      if (t === "STRING" /* STRING */) {
        parts.push(this.parse_string_concatenation(tokens));
      } else if (t === "+" /* PLUS */) {
        tokens.consume_type("+" /* PLUS */);
      } else {
        parts.push(tokens.consume());
      }
    }
    return parts.join("").trim();
  }
  parse_string_concatenation(tokens) {
    const parts = [tokens.consume_type("STRING" /* STRING */)];
    while (tokens.has_more() && tokens.peek_type() === "+" /* PLUS */) {
      tokens.consume_type("+" /* PLUS */);
      parts.push(tokens.consume_type("STRING" /* STRING */));
    }
    return parts.join("");
  }
  parse_string_argument(tokens) {
    if (tokens.peek_type() === "STRING" /* STRING */) {
      return this.parse_string_concatenation(tokens);
    }
    return tokens.consume().replace(/^['"]|['"]$/g, "");
  }
  substatement_handler(tokens, dispatch) {
    const key = this.dispatch_key(tokens);
    if (typeof key === "string") {
      return dispatch[key];
    }
    return void 0;
  }
  skip_unsupported_or_raise_unknown(tokens, context) {
    const peek = tokens.peek();
    if (peek === INPUT || peek === OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }
    if (this.skip_unsupported_if_present(tokens, context)) {
      return true;
    }
    const bad = tokens.peek() ?? "<eof>";
    tokens.syntaxError(`Invalid or unknown statement '${bad}' in ${context}`);
  }
  parse_prefixed_extension_statement_public(tokens, context) {
    this.parse_prefixed_extension_statement(tokens, context);
  }
  consume_qname_from_identifier(tokens) {
    const parts = [tokens.consume_type("IDENTIFIER" /* IDENTIFIER */)];
    while (tokens.consume_if_type(":" /* COLON */)) {
      parts.push(tokens.consume_type("IDENTIFIER" /* IDENTIFIER */));
    }
    return parts.join(":");
  }
  add_to_parent_or_module(context, stmt) {
    const parent = context.current_parent;
    if (parent && Array.isArray(parent.statements)) {
      parent.statements.push(stmt);
      return;
    }
    const module = context.module;
    if (Array.isArray(module.statements)) {
      module.statements.push(stmt);
    }
  }
  skip_unsupported_if_present(tokens, context) {
    if (!is_unsupported_construct_start(tokens)) {
      return false;
    }
    skip_unsupported_construct(tokens, { context });
    return true;
  }
  parse_top_level_module(tokens, context) {
    tokens.consume(MODULE);
    const moduleName2 = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    context.module.name = moduleName2;
    tokens.consume_type("{" /* LBRACE */);
    const moduleStatements = [];
    while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
      moduleStatements.push(this.parseStatement(tokens, context));
    }
    tokens.consume_type("}" /* RBRACE */);
    return {
      __class__: "YangStatement",
      keyword: "module",
      name: moduleName2,
      argument: moduleName2,
      statements: moduleStatements
    };
  }
  fromAst(stmt) {
    const keyword = serializedKeywordFromAstStatement(stmt);
    const children = [
      ...this.serializeAstChildren(stmt.statements ?? []),
      ...this.serializeAstChildren(stmt.cases ?? [])
    ];
    const out = {
      __class__: "YangStatement",
      keyword,
      name: stmt.name,
      argument: stmt.name,
      statements: children
    };
    if (stmt.type) {
      out.type = this.fromTypeShape(stmt.type);
    }
    if (stmt.mandatory !== void 0) {
      out.mandatory = stmt.mandatory;
    }
    if (stmt.default !== void 0) {
      out.default = stmt.default;
    }
    const config = stmt.config;
    if (typeof config === "boolean") {
      out.config = config;
    }
    if (keyword === "leaf-list") {
      const llDefaults = stmt.defaults;
      if (Array.isArray(llDefaults) && llDefaults.length > 0) {
        out.defaults = [...llDefaults];
      }
    }
    if (stmt.key !== void 0) {
      out.key = stmt.key;
    }
    const minElements = stmt.min_elements;
    if (typeof minElements === "number") {
      out.min_elements = minElements;
    }
    const maxElements = stmt.max_elements;
    if (typeof maxElements === "number") {
      out.max_elements = maxElements;
    }
    if (stmt.description) {
      out.description = stmt.description;
    }
    const reference = stmt.reference;
    if (reference) {
      out.reference = reference;
    }
    if (Array.isArray(stmt.if_features) && stmt.if_features.length > 0) {
      out.if_features = [...stmt.if_features];
    }
    if (keyword === "extension") {
      if (typeof stmt.argument_name === "string") {
        out.argument_name = stmt.argument_name;
      }
      if (typeof stmt.argument_yin_element === "boolean") {
        out.argument_yin_element = stmt.argument_yin_element;
      }
    }
    if (keyword === "augment" && typeof stmt.augment_path === "string") {
      out.argument = stmt.augment_path;
      out.augment_path = stmt.augment_path;
    }
    if (keyword === "extension-invocation") {
      out.keyword = stmt.name ?? "extension-invocation";
      out.argument = stmt.argument;
      out.prefix = stmt.prefix;
      out.resolved_module_name = stmt.resolved_module?.name;
      out.resolved_extension_name = stmt.resolved_extension?.name;
    }
    if (stmt.when && typeof stmt.when.expression === "string") {
      out.when = {
        expression: stmt.when.expression,
        description: stmt.when.description ?? "",
        evaluate_with_parent_context: stmt.when.evaluate_with_parent_context ?? false
      };
    }
    if (Array.isArray(stmt.must_statements) && stmt.must_statements.length > 0) {
      out.statements = [
        ...out.statements ?? [],
        ...stmt.must_statements.map((mustStmt) => this.fromMust(mustStmt))
      ];
    }
    if (keyword === "uses") {
      const u = stmt;
      if (typeof u.grouping_name === "string" && u.grouping_name.length > 0) {
        out.grouping_name = u.grouping_name;
        out.argument = u.grouping_name;
      }
      if (Array.isArray(u.refines) && u.refines.length > 0) {
        out.refines = u.refines.map((r) => this.serializeRefineStmt(r));
      }
    }
    const presence = stmt.presence;
    if (typeof presence === "string" && presence.length > 0) {
      out.presence = presence;
    }
    return out;
  }
  serializeRefineStmt(r) {
    const out = {
      __class__: "YangStatement",
      keyword: "refine",
      name: "refine",
      argument: r.target_path,
      refine_target_path: r.target_path,
      statements: []
    };
    if (typeof r.min_elements === "number") {
      out.min_elements = r.min_elements;
    }
    if (typeof r.max_elements === "number") {
      out.max_elements = r.max_elements;
    }
    if (typeof r.refined_mandatory === "boolean") {
      out.refined_mandatory = r.refined_mandatory;
    }
    if (Array.isArray(r.refined_defaults) && r.refined_defaults.length > 0) {
      out.refined_defaults = [...r.refined_defaults];
    }
    if (typeof r.refined_config === "boolean") {
      out.refined_config = r.refined_config;
    }
    if (Array.isArray(r.if_features) && r.if_features.length > 0) {
      out.if_features = [...r.if_features];
    }
    if (typeof r.description === "string" && r.description.length > 0) {
      out.description = r.description;
    }
    if (Array.isArray(r.must_statements) && r.must_statements.length > 0) {
      out.statements = r.must_statements.map((m) => this.fromMust(m));
    }
    return out;
  }
  serializeAstChildren(children) {
    const out = [];
    for (const child of children) {
      if (!child || typeof child !== "object") {
        continue;
      }
      out.push(this.fromAst(child));
    }
    return out;
  }
  fromType(type_stmt) {
    return {
      __class__: "YangStatement",
      keyword: "type",
      name: type_stmt.name,
      argument: type_stmt.name,
      type: this.fromTypeShape(type_stmt),
      statements: []
    };
  }
  fromMust(must_stmt) {
    return {
      __class__: "YangStatement",
      keyword: "must",
      name: must_stmt.expression,
      argument: must_stmt.expression,
      error_message: must_stmt.error_message,
      description: must_stmt.description,
      statements: []
    };
  }
  fromTypeShape(type_stmt) {
    return {
      name: type_stmt.name,
      patterns: type_stmt.patterns.map((p) => ({
        pattern: p.pattern,
        invert_match: p.invert_match,
        error_message: p.error_message,
        error_app_tag: p.error_app_tag
      })),
      length: type_stmt.length,
      range: type_stmt.range,
      fraction_digits: type_stmt.fraction_digits,
      path: type_stmt.path,
      require_instance: type_stmt.require_instance,
      identityref_bases: [...type_stmt.identityref_bases],
      enums: [...type_stmt.enums],
      bits: type_stmt.bits.map((b) => ({ name: b.name, position: b.position ?? 0 })),
      types: type_stmt.types.map((t) => this.fromTypeShape(t))
    };
  }
  extract_type_shape(typeStmt) {
    const name = typeStmt.argument ?? "string";
    const shape = { name };
    for (const child of typeStmt.statements ?? []) {
      if (child.keyword === "pattern" && child.argument) {
        const patterns = shape.patterns ?? [];
        patterns.push({ pattern: child.argument, invert_match: false });
        shape.patterns = patterns;
      }
      if (child.keyword === "length" && child.argument) shape.length = child.argument;
      if (child.keyword === "range" && child.argument) shape.range = child.argument;
      if (child.keyword === "fraction-digits" && child.argument) {
        const n = Number.parseInt(child.argument, 10);
        if (!Number.isNaN(n)) shape.fraction_digits = n;
      }
      if (child.keyword === "enum" && child.argument) shape.enums = [...shape.enums ?? [], child.argument];
      if (child.keyword === "bit" && child.argument) {
        const bits = shape.bits ?? [];
        bits.push({ name: child.argument, position: bits.length === 0 ? 0 : Math.max(...bits.map((b) => b.position)) + 1 });
        shape.bits = bits;
      }
      if (name === "union" && child.keyword === "type") {
        shape.types = [...shape.types ?? [], this.extract_type_shape(child)];
      }
    }
    return shape;
  }
  parse_description(tokens, context) {
    tokens.consume(DESCRIPTION);
    const desc = tokens.consume_type("STRING" /* STRING */);
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        tokens.consume();
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    const parent = context.current_parent;
    if (parent && "description" in parent) {
      parent.description = desc;
    }
    return desc;
  }
  parse_optional_description(tokens, context) {
    if (tokens.has_more() && tokens.peek() === DESCRIPTION) {
      this.parse_description(tokens, context);
    }
  }
  parse_reference(tokens, context) {
    tokens.consume(REFERENCE);
    const ref = tokens.consume_type("STRING" /* STRING */);
    tokens.consume_if_type(";" /* SEMICOLON */);
    const parent = context.current_parent;
    if (parent && typeof parent === "object" && "reference" in parent) {
      parent.reference = ref;
    }
  }
  parse_reference_string_only(tokens, context) {
    this.parse_reference(tokens, context);
  }
  parse_status_ignored(tokens, _context) {
    skip_status_substatement(tokens);
  }
  parse_config(tokens, context) {
    tokens.consume(CONFIG);
    const value = tokens.consume_oneof([TRUE, FALSE])[1];
    const parent = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_config = value === TRUE;
    } else if (parent && typeof parent === "object" && "config" in parent) {
      parent.config = value === TRUE;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_typedef_default(tokens, context) {
    tokens.consume(DEFAULT);
    const parent = context.current_parent;
    if (parent instanceof YangTypedefStmt) {
      parent.default = this.parse_default_value_tokens(tokens);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  register_import(context, moduleName2, localPrefix, revisionDate, tokens) {
    const module = context.module;
    const ownPrefix = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (localPrefix === ownPrefix) {
      throw new YangSemanticError(`Import prefix '${localPrefix}' must differ from this module's prefix`);
    }
    const imports = module.import_prefixes ?? {};
    module.import_prefixes = imports;
    if (imports[localPrefix]) {
      throw new YangSemanticError(`Duplicate import prefix '${localPrefix}'`);
    }
    if (!this.importResolver) {
      throw new YangSemanticError("Import resolution is not configured for this parser instance");
    }
    imports[localPrefix] = this.importResolver(moduleName2, localPrefix, revisionDate, context, tokens);
  }
  parse_ordered_by(tokens) {
    tokens.consume(ORDERED_BY);
    tokens.consume();
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_list_key(tokens, context) {
    tokens.consume(KEY);
    const [value] = tokens.consume_oneof(["STRING" /* STRING */, "IDENTIFIER" /* IDENTIFIER */]);
    const parent = context.current_parent;
    if (parent && "key" in parent) parent.key = value;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_min_elements(tokens, context) {
    tokens.consume(MIN_ELEMENTS);
    const value = Number.parseInt(tokens.consume_type("INTEGER" /* INTEGER */), 10);
    const parent = context.current_parent;
    if (parent && "min_elements" in parent) parent.min_elements = value;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_max_elements(tokens, context) {
    tokens.consume(MAX_ELEMENTS);
    const value = Number.parseInt(tokens.consume_type("INTEGER" /* INTEGER */), 10);
    const parent = context.current_parent;
    if (parent && "max_elements" in parent) parent.max_elements = value;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_leaf_mandatory(tokens, context) {
    tokens.consume(MANDATORY);
    const [, tt] = tokens.consume_oneof([TRUE, FALSE]);
    const parent = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_mandatory = tt === TRUE;
      tokens.consume_if_type(";" /* SEMICOLON */);
      return;
    }
    if (parent && typeof parent === "object" && "mandatory" in parent) {
      parent.mandatory = tt === TRUE;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_leaf_default(tokens, context) {
    tokens.consume(DEFAULT);
    const value = this.parse_default_value_tokens(tokens);
    const parent = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_defaults.push(value);
    } else if (parent instanceof YangLeafListStmt) {
      parent.defaults.push(value);
    } else if (parent && typeof parent === "object" && "default" in parent) {
      parent.default = value;
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_presence(tokens, context) {
    tokens.consume(PRESENCE);
    const parent = context.current_parent;
    const value = tokens.consume_type("STRING" /* STRING */);
    if (parent && "presence" in parent) parent.presence = value;
    tokens.consume_if_type(";" /* SEMICOLON */);
  }
  parse_default_value_tokens(tokens) {
    const tt = tokens.peek_type();
    if (tt === "STRING" /* STRING */) return tokens.consume_type("STRING" /* STRING */);
    if (tt === "INTEGER" /* INTEGER */) return tokens.consume_type("INTEGER" /* INTEGER */);
    if (tt === "IDENTIFIER" /* IDENTIFIER */) return tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    if (tt === TRUE) {
      tokens.consume(TRUE);
      return "true";
    }
    if (tt === FALSE) {
      tokens.consume(FALSE);
      return "false";
    }
    throw new YangSemanticError(`Expected default value, got ${tt}`);
  }
  parse_prefixed_extension_statement(tokens, context) {
    const prefix = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    tokens.consume_type(":" /* COLON */);
    const extensionName = tokens.consume_type("IDENTIFIER" /* IDENTIFIER */);
    const resolvedModule = this.resolve_prefixed_module(context, prefix);
    if (!resolvedModule) {
      throw new YangSemanticError(`Unknown extension prefix '${prefix}' in invocation ${prefix}:${extensionName}`);
    }
    const resolvedExtension = this.resolve_extension_definition(resolvedModule, extensionName);
    if (!resolvedExtension) {
      throw new YangSemanticError(
        `Unknown extension '${extensionName}' in module '${resolvedModule.name ?? ""}' for invocation ${prefix}:${extensionName}`
      );
    }
    const argument = this.consume_optional_extension_argument(tokens);
    const invocation = new YangExtensionInvocationStmt({
      name: `${prefix}:${extensionName}`,
      prefix,
      resolved_module: resolvedModule,
      resolved_extension: resolvedExtension,
      argument
    });
    if (tokens.consume_if_type("{" /* LBRACE */)) {
      const childContext = context.push_parent(invocation);
      while (tokens.has_more() && tokens.peek_type() !== "}" /* RBRACE */) {
        this.parseStatement(tokens, childContext);
      }
      tokens.consume_type("}" /* RBRACE */);
    }
    tokens.consume_if_type(";" /* SEMICOLON */);
    this.add_to_parent_or_module(context, invocation);
    return this.fromAst(invocation);
  }
  consume_optional_extension_argument(tokens) {
    if (!tokens.has_more()) {
      return void 0;
    }
    const tt = tokens.peek_type();
    if (tt === "{" /* LBRACE */ || tt === ";" /* SEMICOLON */) {
      return void 0;
    }
    if (tt === "STRING" /* STRING */) {
      return this.parse_string_concatenation(tokens);
    }
    if (tt === "IDENTIFIER" /* IDENTIFIER */ || tt === "INTEGER" /* INTEGER */ || tt === "DOTTED_NUMBER" /* DOTTED_NUMBER */ || tt === TRUE || tt === FALSE) {
      return tokens.consume();
    }
    return void 0;
  }
  resolve_prefixed_module(context, prefix) {
    const module = context.module;
    const ownPrefix = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (prefix === ownPrefix) {
      return module;
    }
    const imports = module.import_prefixes;
    return imports?.[prefix];
  }
  resolve_extension_definition(resolvedModule, extensionName) {
    const direct = resolvedModule.extensions?.[extensionName];
    if (direct) {
      return direct;
    }
    const statements = Array.isArray(resolvedModule.statements) ? resolvedModule.statements : [];
    const extStmt = statements.find((stmt) => stmt.keyword === "extension" && stmt.name === extensionName);
    if (!extStmt) {
      return void 0;
    }
    return new YangExtensionStmt({
      name: extensionName,
      argument_name: typeof extStmt.argument_name === "string" ? extStmt.argument_name : "",
      argument_yin_element: typeof extStmt.argument_yin_element === "boolean" ? extStmt.argument_yin_element : void 0
    });
  }
};

// src/parser/yang-strings.ts
function unescapeYangQuotedString(content, quote) {
  if (quote !== "'" && quote !== '"') {
    throw new Error(`quote must be "'" or '"', got ${JSON.stringify(quote)}`);
  }
  const out = [];
  let i = 0;
  const n = content.length;
  while (i < n) {
    const ch = content[i];
    if (ch !== "\\" || i + 1 >= n) {
      out.push(ch);
      i += 1;
      continue;
    }
    const nxt = content[i + 1];
    if (nxt === "\\") {
      out.push("\\");
      i += 2;
      continue;
    }
    if (nxt === "n") {
      out.push("\n");
      i += 2;
      continue;
    }
    if (nxt === "t") {
      out.push("	");
      i += 2;
      continue;
    }
    if (quote === '"' && nxt === '"') {
      out.push('"');
      i += 2;
      continue;
    }
    if (quote === "'" && nxt === "'") {
      out.push("'");
      i += 2;
      continue;
    }
    if (nxt === "\r" || nxt === "\n") {
      i += 2;
      if (nxt === "\r" && i < n && content[i] === "\n") {
        i += 1;
      }
      while (i < n && (content[i] === " " || content[i] === "	")) {
        i += 1;
      }
      continue;
    }
    out.push("\\", nxt);
    i += 2;
  }
  return out.join("");
}

// src/parser/tokenizer.ts
var IDENTIFIER_START = /[A-Za-z_]/;
var IDENTIFIER_CONT = /[A-Za-z0-9_.-]/;
var YangTokenizer = class {
  tokenize(content, filename) {
    const token_list = [];
    let i = 0;
    const content_len = content.length;
    let current_line = 1;
    let line_start = 0;
    const advance = () => {
      if (i < content_len && content[i] === "\n") {
        current_line += 1;
        line_start = i + 1;
      }
      i += 1;
    };
    const add_token = (tok_type, value, token_start, line_num, line_start_pos) => {
      const char_pos = token_start - line_start_pos;
      token_list.push(makeYangToken(tok_type, value, line_num, char_pos));
    };
    while (i < content_len) {
      if (/\s/.test(content[i])) {
        advance();
        continue;
      }
      if (content[i] === "/" && i + 1 < content_len && content[i + 1] === "*") {
        advance();
        advance();
        while (i < content_len) {
          if (i + 1 < content_len && content[i] === "*" && content[i + 1] === "/") {
            advance();
            advance();
            break;
          }
          advance();
        }
        continue;
      }
      if (content[i] === "/" && i + 1 < content_len && content[i + 1] === "/") {
        advance();
        advance();
        while (i < content_len && content[i] !== "\n") {
          advance();
        }
        continue;
      }
      const ch = content[i];
      if (ch === '"' || ch === "'") {
        const quote = ch;
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len) {
          if (content[i] === quote) {
            break;
          }
          if (content[i] === "\\" && i + 1 < content_len) {
            advance();
            advance();
          } else {
            advance();
          }
        }
        add_token(
          "STRING" /* STRING */,
          unescapeYangQuotedString(content.slice(start, i), quote),
          token_start,
          token_line,
          token_line_start
        );
        advance();
        continue;
      }
      if (ch === "-" && i + 1 < content_len && /\d/.test(content[i + 1])) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len && /\d/.test(content[i])) {
          advance();
        }
        add_token(
          "INTEGER" /* INTEGER */,
          `-${content.slice(start, i)}`,
          token_start,
          token_line,
          token_line_start
        );
        continue;
      }
      if (/\d/.test(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        while (i < content_len && /\d/.test(content[i])) {
          advance();
        }
        if (i < content_len && content[i] === "." && i + 1 < content_len && /\d/.test(content[i + 1])) {
          advance();
          while (i < content_len && /\d/.test(content[i])) {
            advance();
          }
          add_token(
            "DOTTED_NUMBER" /* DOTTED_NUMBER */,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        } else {
          add_token(
            "INTEGER" /* INTEGER */,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        }
        continue;
      }
      if (IDENTIFIER_START.test(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        advance();
        while (i < content_len && IDENTIFIER_CONT.test(content[i])) {
          advance();
        }
        const lexeme = content.slice(start, i);
        add_token("IDENTIFIER" /* IDENTIFIER */, lexeme, token_start, token_line, token_line_start);
        continue;
      }
      if (ch === "{") {
        add_token("{" /* LBRACE */, ch, i, current_line, line_start);
        advance();
      } else if (ch === "}") {
        add_token("}" /* RBRACE */, ch, i, current_line, line_start);
        advance();
      } else if (ch === ";") {
        add_token(";" /* SEMICOLON */, ch, i, current_line, line_start);
        advance();
      } else if (ch === ":") {
        add_token(":" /* COLON */, ch, i, current_line, line_start);
        advance();
      } else if (ch === "=") {
        add_token("=" /* EQUALS */, ch, i, current_line, line_start);
        advance();
      } else if (ch === "+") {
        add_token("+" /* PLUS */, ch, i, current_line, line_start);
        advance();
      } else if (ch === "/") {
        add_token("/" /* SLASH */, ch, i, current_line, line_start);
        advance();
      } else {
        advance();
      }
    }
    return new TokenStream(token_list, content, filename);
  }
};

// src/ext/rfc8791.ts
var STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index";
function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function asStatements(value) {
  return Array.isArray(value) ? value : [];
}
function deepCloneStatement(stmt) {
  return JSON.parse(JSON.stringify(stmt));
}
function mergeRootIfFeatures(stmt, inherited) {
  if (inherited.length === 0) {
    return;
  }
  const current = Array.isArray(stmt.if_features) ? stmt.if_features : [];
  stmt.if_features = [...inherited, ...current];
}
function mergeRootWhen(stmt, inheritedWhen) {
  if (!inheritedWhen || typeof inheritedWhen.expression !== "string") {
    return;
  }
  const inheritedExpr = inheritedWhen.expression;
  const existing = isObject(stmt.when) ? stmt.when : void 0;
  const existingExpr = typeof existing?.expression === "string" ? existing.expression : void 0;
  if (existingExpr) {
    const existingDescription = typeof existing?.description === "string" ? existing.description : "";
    stmt.when = {
      expression: `(${inheritedExpr}) and (${existingExpr})`,
      description: existingDescription,
      evaluate_with_parent_context: true
    };
    return;
  }
  stmt.when = {
    expression: inheritedExpr,
    description: typeof inheritedWhen.description === "string" ? inheritedWhen.description : "",
    evaluate_with_parent_context: true
  };
}
function parsePrefixedPath(path, kind) {
  const raw = String(path ?? "").trim();
  if (!raw.startsWith("/")) {
    throw new YangSemanticError(`${kind} requires an absolute path argument`);
  }
  const segments = raw.slice(1).split("/").map((part) => part.trim()).filter((part) => part.length > 0);
  if (segments.length === 0) {
    throw new YangSemanticError(`${kind} path cannot be empty`);
  }
  return segments.map((segment) => {
    const idx = segment.indexOf(":");
    if (idx <= 0 || idx === segment.length - 1) {
      throw new YangSemanticError(`${kind}: invalid path segment '${segment}', expected 'prefix:identifier'`);
    }
    return { prefix: segment.slice(0, idx), name: segment.slice(idx + 1) };
  });
}
function resolvePrefixedModule(ctxModule, prefix, fullPath, kind) {
  const ownPrefix = String(ctxModule.prefix ?? "").replace(/^['"]|['"]$/g, "");
  if (prefix === ownPrefix) {
    return ctxModule;
  }
  const imports = isObject(ctxModule.import_prefixes) ? ctxModule.import_prefixes : void 0;
  const resolved = imports && isObject(imports[prefix]) ? imports[prefix] : void 0;
  if (!resolved) {
    throw new YangSemanticError(`${kind}: unknown prefix '${prefix}' in path '${fullPath}'`);
  }
  return resolved;
}
function findNamedChild(owner, name) {
  const children = asStatements(owner.statements);
  return children.find((child) => child.name === name);
}
function findTopLevelStructure(moduleData, name) {
  const runtime = isObject(moduleData.extension_runtime) ? moduleData.extension_runtime : void 0;
  const structureIndex = runtime && isObject(runtime[STRUCTURE_INDEX_KEY]) ? runtime[STRUCTURE_INDEX_KEY] : void 0;
  const indexed = structureIndex?.[name];
  if (isObject(indexed)) {
    return indexed;
  }
  const statements = asStatements(moduleData.statements);
  return statements.find((stmt) => {
    const extName = typeof stmt.resolved_extension_name === "string" ? stmt.resolved_extension_name : "";
    return extName === "structure" && String(stmt.argument ?? "").trim() === name;
  });
}
function resolveAugmentStructureTarget(ctxModule, path) {
  const segments = parsePrefixedPath(path, "augment-structure");
  const first = segments[0];
  const firstModule = resolvePrefixedModule(ctxModule, first.prefix, path, "augment-structure");
  let current = findTopLevelStructure(firstModule, first.name);
  if (!current) {
    throw new YangSemanticError(`augment-structure: no top-level structure '${first.name}' in path '${path}'`);
  }
  for (const segment of segments.slice(1)) {
    resolvePrefixedModule(ctxModule, segment.prefix, path, "augment-structure");
    const next = findNamedChild(current, segment.name);
    if (!next) {
      throw new YangSemanticError(`augment-structure: no child '${segment.name}' in path '${path}'`);
    }
    current = next;
  }
  return current;
}
function applyRFC8791Invocation(stmt, contextModule) {
  const moduleName2 = String(stmt.resolved_module_name ?? "");
  const extName = String(stmt.resolved_extension_name ?? "");
  if (moduleName2 !== "ietf-yang-structure-ext") {
    return stmt;
  }
  if (extName === "structure") {
    const runtime = isObject(contextModule.extension_runtime) ? contextModule.extension_runtime : contextModule.extension_runtime = {};
    const idx = isObject(runtime[STRUCTURE_INDEX_KEY]) ? runtime[STRUCTURE_INDEX_KEY] : runtime[STRUCTURE_INDEX_KEY] = {};
    const structureName = String(stmt.argument ?? "").trim();
    if (structureName.length > 0) {
      idx[structureName] = stmt;
      stmt.name = structureName;
    }
    stmt.data_node_kind = "container";
    return stmt;
  }
  if (extName === "augment-structure") {
    const targetPath = String(stmt.argument ?? "");
    const target = resolveAugmentStructureTarget(contextModule, targetPath);
    const copies = asStatements(stmt.statements).map((child) => deepCloneStatement(child));
    const inheritedIfFeatures = Array.isArray(stmt.if_features) ? stmt.if_features : [];
    const inheritedWhen = isObject(stmt.when) ? stmt.when : void 0;
    for (const copy of copies) {
      mergeRootIfFeatures(copy, inheritedIfFeatures);
      mergeRootWhen(copy, inheritedWhen);
      const targetChildren = asStatements(target.statements);
      targetChildren.push(copy);
      target.statements = targetChildren;
    }
    return void 0;
  }
  return stmt;
}
function walkAndApply(owner, contextModule) {
  const statements = asStatements(owner.statements);
  const out = [];
  for (const statement of statements) {
    let current = statement;
    if (typeof statement.resolved_module_name === "string" && typeof statement.resolved_extension_name === "string") {
      current = applyRFC8791Invocation(statement, contextModule);
    }
    if (!current) {
      continue;
    }
    walkAndApply(current, contextModule);
    out.push(current);
  }
  owner.statements = out;
}
function applyBuiltinExtensionInvocations(moduleData) {
  walkAndApply(moduleData, moduleData);
}

// src/transform/uses-expand.ts
function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}
function mergeIfFeaturesFromParentUses(usesStmt, child) {
  const ufs = usesStmt.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child.if_features) ? child.if_features : [];
  child.if_features = [...ufs, ...existing];
}
function mergeWhenFromParentUses(usesStmt, child) {
  const uw = usesStmt.when;
  if (!uw || typeof uw.expression !== "string" || uw.expression.trim() === "") {
    return;
  }
  const usesWhen = {
    ...deepClone(uw),
    evaluate_with_parent_context: true
  };
  const existing = child.when;
  if (!existing?.expression) {
    child.when = usesWhen;
    return;
  }
  child.when = {
    ...existing,
    expression: `(${existing.expression}) and (${uw.expression})`,
    description: String(existing.description ?? ""),
    evaluate_with_parent_context: true
  };
}
function findNodeByNameDepthFirst(nodes, name) {
  for (const n of nodes) {
    if (n.name === name) {
      return n;
    }
  }
  for (const n of nodes) {
    const hit = findNodeByNameDepthFirst(n.statements ?? [], name);
    if (hit) {
      return hit;
    }
  }
  return void 0;
}
function findRefineTarget(nodes, segments) {
  if (segments.length === 0) {
    return void 0;
  }
  const [head, ...rest] = segments;
  const found = findNodeByNameDepthFirst(nodes, head);
  if (!found) {
    return void 0;
  }
  if (rest.length === 0) {
    return found;
  }
  return findRefineTarget(found.statements ?? [], rest);
}
function applyRefinesFromUses(usesStmt, expanded) {
  const refines = usesStmt.refines;
  if (!Array.isArray(refines) || refines.length === 0) {
    return;
  }
  for (const rf of refines) {
    const pathRaw = rf.refine_target_path ?? rf.argument ?? "";
    const segments = pathRaw.split("/").map((s) => s.trim()).filter(Boolean);
    if (segments.length === 0) {
      continue;
    }
    const target = findRefineTarget(expanded, segments);
    if (!target) {
      throw new YangRefineTargetNotFoundError(pathRaw);
    }
    if (typeof rf.min_elements === "number") {
      target.min_elements = rf.min_elements;
    }
    if (typeof rf.max_elements === "number") {
      target.max_elements = rf.max_elements;
    }
    if (typeof rf.refined_mandatory === "boolean") {
      target.mandatory = rf.refined_mandatory;
    }
    if (typeof rf.refined_config === "boolean") {
      target.config = rf.refined_config;
    }
    const refinedDefaults = rf.refined_defaults;
    if (Array.isArray(refinedDefaults) && refinedDefaults.length > 0) {
      if (target.keyword === "leaf" /* LEAF */) {
        target.default = refinedDefaults[0];
      } else if (target.keyword === "leaf-list" /* LEAF_LIST */) {
        target.defaults = [...refinedDefaults];
      }
    }
    const rif = rf.if_features;
    if (Array.isArray(rif) && rif.length > 0) {
      const cur = Array.isArray(target.if_features) ? target.if_features : [];
      target.if_features = [...rif, ...cur];
    }
    const refinedDesc = typeof rf.description === "string" ? rf.description.trim() : "";
    if (refinedDesc) {
      target.description = refinedDesc;
    }
    const extra = rf.statements ?? [];
    if (extra.length > 0) {
      target.statements = [...target.statements ?? [], ...deepClone(extra)];
    }
  }
}
function expandGroupingBody(groupingName, groupings, stack) {
  if (stack.includes(groupingName)) {
    throw new YangCircularUsesError(stack, groupingName);
  }
  const g = groupings[groupingName];
  if (!g) {
    throw new YangSemanticError(`Unknown grouping '${groupingName}'`);
  }
  const nextStack = [...stack, groupingName];
  const rawChildren = g.statements ?? [];
  const flattened = [];
  for (const child of rawChildren) {
    if (child.keyword === "uses") {
      const gn = String(child.grouping_name ?? child.argument ?? "").trim();
      if (!gn) {
        continue;
      }
      const body = expandGroupingBody(gn, groupings, nextStack);
      applyRefinesFromUses(child, body);
      for (const stmt of body) {
        mergeIfFeaturesFromParentUses(child, stmt);
        mergeWhenFromParentUses(child, stmt);
        flattened.push(deepClone(stmt));
      }
    } else {
      flattened.push(deepClone(child));
    }
  }
  return flattened.map((stmt) => expandUsesUnderStatement(stmt, groupings, nextStack));
}
function expandUsesUnderStatement(stmt, groupings, stack) {
  if (stmt.statements?.length) {
    stmt.statements = expandStatementList(stmt.statements, groupings, stack);
  }
  return stmt;
}
function expandStatementList(statements, groupings, stack) {
  const out = [];
  for (const stmt of statements) {
    if (stmt.keyword === "uses") {
      const gn = String(stmt.grouping_name ?? stmt.argument ?? "").trim();
      if (!gn) {
        continue;
      }
      const expanded = expandGroupingBody(gn, groupings, stack);
      applyRefinesFromUses(stmt, expanded);
      for (const e of expanded) {
        mergeIfFeaturesFromParentUses(stmt, e);
        mergeWhenFromParentUses(stmt, e);
        out.push(expandUsesUnderStatement(e, groupings, stack));
      }
    } else {
      out.push(expandUsesUnderStatement(deepClone(stmt), groupings, stack));
    }
  }
  return out;
}
function expandUses(module) {
  const data = module.data;
  const groupings = data.groupings;
  if (!groupings || Object.keys(groupings).length === 0) {
    return module;
  }
  const cloned = deepClone(data);
  if (data.features instanceof Set) {
    cloned.features = new Set(data.features);
  }
  if (data.feature_if_features && typeof data.feature_if_features === "object") {
    cloned.feature_if_features = { ...data.feature_if_features };
  }
  const g = cloned.groupings;
  const top = cloned.statements ?? [];
  cloned.statements = expandStatementList(top, g, []);
  delete cloned.groupings;
  return new YangModule(cloned, module.source);
}

// src/validator/semantic-validation.ts
function iterStatements(statements) {
  const out = [];
  for (const stmt of statements ?? []) {
    out.push(stmt);
    out.push(...iterStatements(stmt.statements));
  }
  return out;
}
function validateListKeyConstraints(module) {
  for (const stmt of iterStatements(module.data.statements)) {
    if (stmt.keyword !== "list" || typeof stmt.key !== "string" || stmt.key.trim() === "") {
      continue;
    }
    const keyLeaves = new Map(
      (stmt.statements ?? []).filter((child) => child.keyword === "leaf" && typeof child.name === "string").map((child) => [child.name, child])
    );
    for (const keyName of stmt.key.split(/\s+/).filter(Boolean)) {
      const child = keyLeaves.get(keyName);
      if (child === void 0) {
        throw new YangSemanticError(
          `List '${stmt.name ?? ""}': key leaf '${keyName}' does not exist (RFC 7950: each list key name must refer to a child leaf).`
        );
      }
      let illegal;
      if (child.when !== void 0) {
        illegal = "when";
      } else if (Array.isArray(child.if_features) && child.if_features.length > 0) {
        illegal = "if-feature";
      }
      if (illegal === void 0) {
        continue;
      }
      throw new YangSemanticError(
        `List '${stmt.name ?? ""}': key leaf '${child.name}' must not have '${illegal}' (RFC 7950: 'when' and 'if-feature' are illegal on list keys).`
      );
    }
  }
}
function validateSemantics(module) {
  validateListKeyConstraints(module);
}

// src/parser/yang-parser.ts
function serializeIdentities(raw) {
  const out = {};
  if (!raw) {
    return out;
  }
  for (const [name, stmt] of Object.entries(raw)) {
    out[name] = { bases: Array.isArray(stmt.bases) ? [...stmt.bases] : [] };
  }
  return out;
}
function buildModuleData(root, moduleState) {
  if (root.keyword !== "module") {
    throw new YangSemanticError("Only 'module' roots are currently supported by TS parser");
  }
  const statements = root.statements ?? [];
  const typedefs = {};
  for (const stmt of statements) {
    if (stmt.keyword === "typedef" && stmt.argument) {
      const typeStmt = stmt.statements?.find((child) => child.keyword === "type");
      typedefs[stmt.argument] = {
        name: stmt.argument,
        description: typeof stmt.description === "string" ? stmt.description : "",
        reference: typeof stmt.reference === "string" ? stmt.reference : "",
        default: stmt.default,
        type: stmt.type ?? typeStmt?.type,
        statements: stmt.statements ?? []
      };
    }
  }
  const features = moduleState.features;
  const featureIfFeatures = moduleState.feature_if_features;
  const moduleDescriptionStmt = statements.find((stmt) => stmt.keyword === "description");
  const moduleDescription = typeof moduleDescriptionStmt?.argument === "string" ? moduleDescriptionStmt.argument : "";
  return {
    __class__: "YangModule",
    name: root.argument,
    yang_version: statements.find((stmt) => stmt.keyword === "yang-version")?.argument ?? "1.1",
    namespace: statements.find((stmt) => stmt.keyword === "namespace")?.argument ?? "",
    prefix: statements.find((stmt) => stmt.keyword === "prefix")?.argument ?? "",
    organization: String(moduleState.organization ?? ""),
    contact: String(moduleState.contact ?? ""),
    description: moduleDescription,
    typedefs,
    identities: serializeIdentities(moduleState.identities),
    import_prefixes: moduleState.import_prefixes ?? {},
    extensions: moduleState.extensions ?? {},
    extension_runtime: moduleState.extension_runtime ?? {},
    features: features instanceof Set ? new Set(features) : /* @__PURE__ */ new Set(),
    feature_if_features: featureIfFeatures && typeof featureIfFeatures === "object" ? { ...featureIfFeatures } : {},
    statements
  };
}
var YangParser = class {
  expandUses;
  includePath;
  moduleCache = /* @__PURE__ */ new Map();
  tokenizer = new YangTokenizer();
  parsers = new StatementParsers({
    importResolver: (moduleName2, _localPrefix, revisionDate, context, tokens) => this.resolveImport(moduleName2, revisionDate, context, tokens)
  });
  constructor(options = {}) {
    this.expandUses = options.expand_uses ?? true;
    this.includePath = (options.include_path ?? []).map((p) => resolve(p));
  }
  /** Resolve `import` like Python `YangParser._resolve_submodule_path` (revision file, then basename, then last `name@*.yang`). */
  resolveImportedModulePath(moduleBasename, revisionDate, sourceDir) {
    const trimmedRev = revisionDate?.trim();
    const candidates = [];
    if (trimmedRev) {
      candidates.push(`${moduleBasename}@${trimmedRev}.yang`);
    }
    candidates.push(`${moduleBasename}.yang`);
    const dirs = [sourceDir, ...this.includePath];
    for (const dir of dirs) {
      for (const c of candidates) {
        const p = resolve(dir, c);
        if (existsSync(p)) {
          return p;
        }
      }
      let matches = [];
      try {
        matches = readdirSync(dir).filter((f) => f.startsWith(`${moduleBasename}@`) && f.endsWith(".yang"));
      } catch {
        matches = [];
      }
      if (matches.length > 0) {
        matches.sort();
        return resolve(dir, matches[matches.length - 1]);
      }
    }
    throw new YangSemanticError(
      `Could not find imported module '${moduleBasename}' (tried ${candidates.join(", ")}) under ${dirs.join(", ")}`
    );
  }
  resolveImport(moduleName2, revisionDate, context, _tokens) {
    const sourcePath = context.module.__source_path;
    if (!sourcePath) {
      throw new YangSemanticError(
        "import requires a filesystem location: use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const filePath = this.resolveImportedModulePath(moduleName2, revisionDate, dirname(sourcePath));
    const imported = this.parseFile(filePath);
    return imported.data;
  }
  parseTokenStream(stream, source) {
    const moduleState = {
      name: "",
      yang_version: "1.1",
      namespace: "",
      prefix: "",
      organization: "",
      contact: "",
      revisions: [],
      belongs_to_module: "",
      typedefs: {},
      identities: {},
      groupings: {},
      features: /* @__PURE__ */ new Set(),
      feature_if_features: {},
      import_prefixes: {},
      extensions: {},
      extension_runtime: {},
      __source_path: source.kind === "file" ? source.value : void 0,
      statements: []
    };
    const context = new ParserContext({ module: moduleState, current_parent: {} });
    const root = this.parsers.parseModule(stream, context);
    const data = buildModuleData(root, moduleState);
    const rawGroupings = moduleState.groupings ?? {};
    const serializedGroupings = {};
    for (const [key, val] of Object.entries(rawGroupings)) {
      if (!val || typeof val !== "object") {
        continue;
      }
      const g = val;
      const gname = g.name ?? key;
      serializedGroupings[key] = {
        __class__: "YangStatement",
        keyword: "grouping",
        name: gname,
        argument: gname,
        statements: (g.statements ?? []).map((ch) => this.parsers.serializeAstStatement(ch))
      };
    }
    if (Object.keys(serializedGroupings).length > 0) {
      data.groupings = serializedGroupings;
    }
    applyBuiltinExtensionInvocations(data);
    let mod = new YangModule(data, source);
    if (this.expandUses) {
      mod = expandUses(mod);
      validateSemantics(mod);
    }
    return mod;
  }
  parseString(content, sourceName = "<memory>") {
    const stream = this.tokenizer.tokenize(content, sourceName);
    const source = { kind: "string", value: content, name: sourceName };
    return this.parseTokenStream(stream, source);
  }
  parseFile(path) {
    const absolute = resolve(path);
    const cached = this.moduleCache.get(absolute);
    if (cached) {
      return cached;
    }
    const content = readFileSync(absolute, "utf-8");
    const stream = this.tokenizer.tokenize(content, absolute);
    const source = { kind: "file", value: absolute, name: absolute };
    const module = this.parseTokenStream(stream, source);
    this.moduleCache.set(absolute, module);
    return module;
  }
};

// src/parser/index.ts
var defaultParser = new YangParser();
function parseYangString(content) {
  return defaultParser.parseString(content);
}
function parseYangFile(path, options = {}) {
  if (options.includePath?.length || options.expandUses === false) {
    const parser = new YangParser({
      include_path: options.includePath,
      expand_uses: options.expandUses
    });
    return parser.parseFile(path);
  }
  return defaultParser.parseFile(path);
}

// src/validator/validator-extension.ts
var ValidatorExtension = /* @__PURE__ */ ((ValidatorExtension2) => {
  ValidatorExtension2["ANYDATA_VALIDATION"] = "anydata_validation";
  return ValidatorExtension2;
})(ValidatorExtension || {});

// src/validator/if-feature-eval.ts
function stripQuotes(prefix) {
  return String(prefix ?? "").replace(/^['"]|['"]$/g, "");
}
function moduleName(m) {
  return String(m.name ?? "");
}
function declaredFeatures(m) {
  const f = m.features;
  if (f instanceof Set) {
    return new Set(f);
  }
  if (Array.isArray(f)) {
    return new Set(f);
  }
  return /* @__PURE__ */ new Set();
}
function resolvePrefixedModule2(ctx, prefix) {
  const own = stripQuotes(ctx.prefix);
  if (prefix === own) {
    return ctx;
  }
  const imports = ctx.import_prefixes;
  const hit = imports?.[prefix];
  if (hit && typeof hit === "object") {
    return hit;
  }
  return void 0;
}
function reachableModuleData(root) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  const walk = (m) => {
    if (seen.has(m)) {
      return;
    }
    seen.add(m);
    out.push(m);
    const im = m.import_prefixes;
    if (!im) {
      return;
    }
    for (const v of Object.values(im)) {
      if (v && typeof v === "object") {
        walk(v);
      }
    }
  };
  walk(root);
  return out;
}
function featureIsSupported(ctxModule, enabledByModule, ref) {
  let mod;
  let fname;
  const idx = ref.indexOf(":");
  if (idx !== -1) {
    const pref = ref.slice(0, idx);
    fname = ref.slice(idx + 1);
    const resolved = resolvePrefixedModule2(ctxModule, pref);
    if (!resolved) {
      return false;
    }
    mod = resolved;
  } else {
    mod = ctxModule;
    fname = ref;
  }
  if (!declaredFeatures(mod).has(fname)) {
    return false;
  }
  const enabled = enabledByModule[moduleName(mod)];
  if (!enabled) {
    return false;
  }
  return enabled.has(fname);
}
function tokenize(expr) {
  const tokens = [];
  let i = 0;
  const n = expr.length;
  while (i < n) {
    const c = expr[i];
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if (c === "(" || c === ")") {
      tokens.push(c);
      i += 1;
      continue;
    }
    let j = i;
    while (j < n && !/\s/.test(expr[j]) && expr[j] !== "(" && expr[j] !== ")") {
      j += 1;
    }
    tokens.push(expr.slice(i, j));
    i = j;
  }
  return tokens;
}
var IfFeatureParser = class {
  constructor(toks, ctx, enabled) {
    this.toks = toks;
    this.ctx = ctx;
    this.enabled = enabled;
  }
  toks;
  ctx;
  enabled;
  i = 0;
  peek() {
    return this.toks[this.i];
  }
  eat(expected) {
    const t = this.peek();
    if (t === void 0) {
      throw new Error("unexpected end of expression");
    }
    if (expected !== void 0 && t !== expected) {
      throw new Error(`expected ${expected}, got ${t}`);
    }
    this.i += 1;
    return t;
  }
  parseExpr() {
    let left = this.parseTerm();
    while (this.peek() === "or") {
      this.eat("or");
      const right = this.parseExpr();
      left = left || right;
    }
    return left;
  }
  parseTerm() {
    let left = this.parseFactor();
    while (this.peek() === "and") {
      this.eat("and");
      const right = this.parseTerm();
      left = left && right;
    }
    return left;
  }
  parseFactor() {
    const t = this.peek();
    if (t === "not") {
      this.eat("not");
      return !this.parseFactor();
    }
    if (t === "(") {
      this.eat("(");
      const v = this.parseExpr();
      this.eat(")");
      return v;
    }
    if (t === void 0) {
      throw new Error("unexpected end of expression");
    }
    this.eat();
    return featureIsSupported(this.ctx, this.enabled, t);
  }
  atEnd() {
    return this.i >= this.toks.length;
  }
};
function evaluateIfFeatureExpression(expr, ctxModule, enabledByModule) {
  const trimmed = expr.trim();
  if (!trimmed) {
    return false;
  }
  try {
    const p = new IfFeatureParser(tokenize(trimmed), ctxModule, enabledByModule);
    const out = p.parseExpr();
    if (!p.atEnd()) {
      return false;
    }
    return out;
  } catch {
    return false;
  }
}
function stmtIfFeaturesSatisfied(ifFeatures, ctxModule, enabledByModule) {
  if (!ifFeatures || ifFeatures.length === 0) {
    return true;
  }
  return ifFeatures.every((e) => evaluateIfFeatureExpression(e, ctxModule, enabledByModule));
}
function normalizeOverride(override) {
  if (override == null) {
    return null;
  }
  if (override instanceof Map) {
    return new Map(override);
  }
  return new Map(Object.entries(override));
}
function prunePerFeatureIfFeatures(modules, enabled) {
  let changed = true;
  while (changed) {
    changed = false;
    const frozen = {};
    for (const [mn, s] of Object.entries(enabled)) {
      frozen[mn] = new Set(s);
    }
    for (const m of modules) {
      const mn = moduleName(m);
      const mutable = enabled[mn];
      if (!mutable) {
        continue;
      }
      const fif = m.feature_if_features;
      for (const fname of [...mutable]) {
        const reqs = fif?.[fname];
        if (!reqs?.length) {
          continue;
        }
        if (!stmtIfFeaturesSatisfied(reqs, m, frozen)) {
          mutable.delete(fname);
          changed = true;
        }
      }
    }
  }
  const out = {};
  for (const [k, v] of Object.entries(enabled)) {
    out[k] = new Set(v);
  }
  return out;
}
function buildEnabledFeaturesMap(root, override) {
  const modules = reachableModuleData(root);
  const ov = normalizeOverride(override);
  const enabled = {};
  for (const m of modules) {
    const mn = moduleName(m);
    const declared = declaredFeatures(m);
    if (ov === null || !ov.has(mn)) {
      enabled[mn] = new Set(declared);
    } else {
      enabled[mn] = new Set(ov.get(mn) ?? []);
    }
  }
  return prunePerFeatureIfFeatures(modules, enabled);
}

// src/identity-graph.ts
function ownPrefixStripped(mod) {
  return String(mod.prefix ?? "").replace(/^['"]|['"]$/g, "");
}
function getIdentities(mod) {
  const raw = mod.identities;
  if (!raw || typeof raw !== "object") {
    return {};
  }
  return raw;
}
function resolvePrefixedModuleData(importerData, prefix) {
  const own = ownPrefixStripped(importerData);
  if (prefix === own) {
    return importerData;
  }
  const imports = importerData.import_prefixes ?? {};
  const m = imports[prefix];
  return m && typeof m === "object" ? m : void 0;
}
function resolveIdentityQnamePair(importer, qname) {
  if (!qname.includes(":")) {
    return null;
  }
  const [pref, local] = qname.split(":", 2);
  const m = resolvePrefixedModuleData(importer.data, pref);
  if (!m || !(local in getIdentities(m))) {
    return null;
  }
  return { mod: m, local };
}
function resolveIdentityBaseRef(fromMod, base) {
  if (base.includes(":")) {
    const [pref, local] = base.split(":", 2);
    const m = resolvePrefixedModuleData(fromMod, pref);
    if (!m || !(local in getIdentities(m))) {
      return null;
    }
    return { mod: m, local };
  }
  if (base in getIdentities(fromMod)) {
    return { mod: fromMod, local: base };
  }
  return null;
}
function pairEquals(a, b) {
  return a.mod === b.mod && a.local === b.local;
}
function pairInPairs(p, pairs) {
  return pairs.some((x) => pairEquals(x, p));
}
var moduleSlot = /* @__PURE__ */ new WeakMap();
var nextModuleSlot = 1;
function moduleId(mod) {
  let id = moduleSlot.get(mod);
  if (id === void 0) {
    id = nextModuleSlot;
    nextModuleSlot += 1;
    moduleSlot.set(mod, id);
  }
  return id;
}
function pairKey(p) {
  return `${moduleId(p.mod)}:${p.local}`;
}
function identityAncestorClosure(startMod, startName) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  const stack = [{ mod: startMod, local: startName }];
  while (stack.length > 0) {
    const pair = stack.pop();
    const k = pairKey(pair);
    if (seen.has(k)) {
      continue;
    }
    seen.add(k);
    out.push(pair);
    const stmt = getIdentities(pair.mod)[pair.local];
    if (!stmt?.bases) {
      continue;
    }
    for (const b of stmt.bases) {
      const nxt = resolveIdentityBaseRef(pair.mod, b);
      if (nxt) {
        stack.push(nxt);
      }
    }
  }
  return out;
}
function isDerivedFromStrictQNames(importer, vQ, tQ) {
  const pv = resolveIdentityQnamePair(importer, vQ);
  const pt = resolveIdentityQnamePair(importer, tQ);
  if (!pv || !pt) {
    return false;
  }
  const closure = identityAncestorClosure(pv.mod, pv.local);
  return pairInPairs(pt, closure) && !pairEquals(pt, pv);
}
function isDerivedFromOrSelfQNames(importer, vQ, tQ) {
  const pv = resolveIdentityQnamePair(importer, vQ);
  const pt = resolveIdentityQnamePair(importer, tQ);
  if (!pv || !pt) {
    return false;
  }
  const closure = identityAncestorClosure(pv.mod, pv.local);
  return pairInPairs(pt, closure);
}

// src/xpath/evaluator.ts
function isNode(value) {
  return Boolean(value) && typeof value === "object" && "schema" in value && "parent" in value;
}
function isNodeSet(value) {
  return Array.isArray(value) && (value.length === 0 || isNode(value[0]));
}
function toYangBool(value) {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0 && !Number.isNaN(value);
  }
  if (typeof value === "string") {
    return value !== "";
  }
  return value !== null && value !== void 0;
}
function nodeSetValues(value) {
  if (Array.isArray(value)) {
    return value.map((item) => isNode(item) ? item.data : item);
  }
  if (isNode(value)) {
    return [value.data];
  }
  if (value === void 0 || value === null) {
    return [];
  }
  return [value];
}
function firstValue(value) {
  const values = nodeSetValues(value);
  return values[0];
}
function coercePair(left, right) {
  if (typeof left === "boolean" || typeof right === "boolean") {
    return [toYangBool(left), toYangBool(right)];
  }
  if (typeof left === "number" && typeof right === "number") {
    return [left, right];
  }
  const leftNum = Number(left);
  const rightNum = Number(right);
  if (!Number.isNaN(leftNum) && !Number.isNaN(rightNum)) {
    return [leftNum, rightNum];
  }
  return [String(left ?? "").trim(), String(right ?? "").trim()];
}
function compareEq(left, right) {
  const leftValues = nodeSetValues(left);
  const rightValues = Array.isArray(right) && !isNodeSet(right) ? right : nodeSetValues(right);
  if (leftValues.length === 0 || rightValues.length === 0) {
    return leftValues.length === 0 && rightValues.length === 0;
  }
  for (const leftValue of leftValues) {
    for (const rightValue of rightValues) {
      if (leftValue == null && rightValue == null) {
        return true;
      }
      if (leftValue == null || rightValue == null) {
        continue;
      }
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (cl === cr) {
        return true;
      }
    }
  }
  return false;
}
function compareLt(left, right) {
  for (const leftValue of nodeSetValues(left)) {
    for (const rightValue of nodeSetValues(right)) {
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (typeof cl === "number" && typeof cr === "number") {
        if (cl < cr) {
          return true;
        }
        continue;
      }
      if (`${cl}` < `${cr}`) {
        return true;
      }
    }
  }
  return false;
}
function compareGt(left, right) {
  for (const leftValue of nodeSetValues(left)) {
    for (const rightValue of nodeSetValues(right)) {
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (typeof cl === "number" && typeof cr === "number") {
        if (cl > cr) {
          return true;
        }
        continue;
      }
      if (`${cl}` > `${cr}`) {
        return true;
      }
    }
  }
  return false;
}
function getSchemaChildren(schema) {
  if (!schema || !Array.isArray(schema.statements)) {
    return [];
  }
  return schema.statements;
}
function findSchemaChild(schema, name) {
  for (const child of getSchemaChildren(schema)) {
    if (child?.name === name) {
      return child;
    }
  }
  return null;
}
function defaultValue(schema) {
  if (!schema || schema.keyword !== "leaf") {
    return void 0;
  }
  const raw = schema.data?.default;
  const typeName = schema.data?.type?.name;
  if (typeName === "boolean" && typeof raw === "string") {
    const lower = raw.toLowerCase();
    if (lower === "true") return true;
    if (lower === "false") return false;
  }
  return raw;
}
function stepNode(node, step) {
  const data = node.data;
  const schema = node.schema;
  if (Array.isArray(data) && (schema?.keyword === "list" || schema?.keyword === "leaf-list")) {
    const expanded = [];
    for (const item of data) {
      const entryNode = { data: item, schema, parent: node };
      expanded.push(...stepNode(entryNode, step));
    }
    return expanded;
  }
  const childSchema = findSchemaChild(schema, step);
  let value;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const asRecord3 = data;
    if (step in asRecord3) {
      value = asRecord3[step];
      if (value === null) {
        value = true;
      }
    } else {
      value = defaultValue(childSchema);
    }
  }
  if (value === void 0) {
    return [];
  }
  if (childSchema?.keyword === "list" || childSchema?.keyword === "leaf-list") {
    if (Array.isArray(value)) {
      return value.map((item) => ({ data: item, schema: childSchema, parent: node }));
    }
    return [{ data: value, schema: childSchema, parent: node }];
  }
  return [{ data: value, schema: childSchema, parent: node }];
}
var XPathEvaluator = class {
  eval(ast, context, node) {
    switch (ast.kind) {
      case "literal":
        return ast.value;
      case "path":
        return this.evalPath(ast, context, node);
      case "binary":
        return this.evalBinary(ast, context, node);
      case "function":
        return this.evalFunction(ast.name, ast.args, context, node);
      default:
        return null;
    }
  }
  evalPath(path, context, node) {
    let nodes = [path.isAbsolute ? context.root : node];
    for (const segment of path.segments) {
      if (segment.step === ".") {
      } else if (segment.step === "..") {
        nodes = nodes.map((entry) => entry.parent).filter((entry) => Boolean(entry));
      } else {
        const next = [];
        for (const entry of nodes) {
          next.push(...stepNode(entry, segment.step));
        }
        nodes = next;
      }
      if (segment.predicate) {
        const filtered = [];
        for (let index = 0; index < nodes.length; index += 1) {
          const candidate = nodes[index];
          const value = this.eval(segment.predicate, context, candidate);
          let keep = false;
          if (typeof value === "number" && Number.isFinite(value)) {
            keep = Math.trunc(value) === index + 1;
          } else {
            keep = toYangBool(value);
          }
          if (keep) {
            filtered.push(candidate);
          }
        }
        nodes = filtered;
      }
    }
    return nodes;
  }
  evalBinary(ast, context, node) {
    const op = ast.operator;
    if (op === "or") {
      const left2 = this.eval(ast.left, context, node);
      if (toYangBool(left2)) {
        return true;
      }
      return toYangBool(this.eval(ast.right, context, node));
    }
    if (op === "and") {
      const left2 = this.eval(ast.left, context, node);
      if (!toYangBool(left2)) {
        return false;
      }
      return toYangBool(this.eval(ast.right, context, node));
    }
    if (op === "/") {
      const left2 = this.eval(ast.left, context, node);
      const leftNodes = isNodeSet(left2) ? left2 : isNode(left2) ? [left2] : [];
      const results = [];
      for (const leftNode of leftNodes) {
        const right2 = this.eval(ast.right, context, leftNode);
        if (isNodeSet(right2)) {
          results.push(...right2);
        } else if (isNode(right2)) {
          results.push(right2);
        }
      }
      return results;
    }
    const left = this.eval(ast.left, context, node);
    const right = this.eval(ast.right, context, node);
    if (op === "=") {
      return compareEq(left, right);
    }
    if (op === "!=") {
      return !compareEq(left, right);
    }
    if (op === "<") {
      return compareLt(left, right);
    }
    if (op === ">") {
      return compareGt(left, right);
    }
    if (op === "<=") {
      return compareEq(left, right) || compareLt(left, right);
    }
    if (op === ">=") {
      return compareEq(left, right) || compareGt(left, right);
    }
    if (op === "+") {
      const sum = Number(firstValue(left)) + Number(firstValue(right));
      return Number.isNaN(sum) ? Number.NaN : sum;
    }
    if (op === "-") {
      const diff = Number(firstValue(left)) - Number(firstValue(right));
      return Number.isNaN(diff) ? Number.NaN : diff;
    }
    if (op === "*") {
      const product = Number(firstValue(left)) * Number(firstValue(right));
      return Number.isNaN(product) ? Number.NaN : product;
    }
    return null;
  }
  evalFunction(name, args, context, node) {
    const fn = name.toLowerCase();
    if (fn === "current") {
      return context.current;
    }
    if (fn === "not") {
      if (args.length !== 1) {
        return null;
      }
      return !toYangBool(this.eval(args[0], context, node));
    }
    if (fn === "true") {
      return true;
    }
    if (fn === "false") {
      return false;
    }
    if (fn === "count") {
      if (args.length !== 1) {
        return 0;
      }
      const value = this.eval(args[0], context, node);
      return isNodeSet(value) ? value.length : value == null ? 0 : 1;
    }
    if (fn === "string") {
      if (args.length !== 1) {
        return "";
      }
      const value = firstValue(this.eval(args[0], context, node));
      return value == null ? "" : String(value);
    }
    if (fn === "number") {
      if (args.length !== 1) {
        return Number.NaN;
      }
      const value = firstValue(this.eval(args[0], context, node));
      const numberValue = Number(value);
      return Number.isNaN(numberValue) ? Number.NaN : numberValue;
    }
    if (fn === "boolean") {
      if (args.length !== 1) {
        return false;
      }
      return toYangBool(this.eval(args[0], context, node));
    }
    if (fn === "string-length") {
      if (args.length !== 1) {
        return 0;
      }
      const value = firstValue(this.eval(args[0], context, node));
      return value == null ? 0 : String(value).length;
    }
    if (fn === "concat") {
      return args.map((arg) => String(firstValue(this.eval(arg, context, node)) ?? "")).join("");
    }
    if (fn === "translate") {
      if (args.length !== 3) {
        return "";
      }
      const source = String(firstValue(this.eval(args[0], context, node)) ?? "");
      const fromChars = String(firstValue(this.eval(args[1], context, node)) ?? "");
      const toChars = String(firstValue(this.eval(args[2], context, node)) ?? "");
      if (fromChars.length === 0) {
        return source;
      }
      const map = /* @__PURE__ */ new Map();
      for (let i = 0; i < fromChars.length; i += 1) {
        map.set(fromChars[i], i < toChars.length ? toChars[i] : null);
      }
      let out = "";
      for (const ch of source) {
        if (!map.has(ch)) {
          out += ch;
          continue;
        }
        const replacement = map.get(ch);
        if (replacement != null) {
          out += replacement;
        }
      }
      return out;
    }
    if (fn === "deref") {
      if (args.length !== 1) {
        return [];
      }
      const start = context.current ?? node;
      const raw = this.eval(args[0], context, start);
      const sourceNodes = isNodeSet(raw) ? raw : isNode(raw) ? [raw] : [];
      const results = [];
      for (const sourceNode of sourceNodes) {
        const typeShape = sourceNode.schema?.data?.type;
        if (!typeShape || typeShape.name !== "leafref") {
          continue;
        }
        const leafrefPath = typeShape.path;
        if (!leafrefPath || leafrefPath.kind !== "path") {
          continue;
        }
        const targets = this.evalPath(leafrefPath, context, sourceNode);
        for (const target of targets) {
          if (target.data === sourceNode.data) {
            results.push(target);
          }
        }
      }
      return results;
    }
    if (fn === "derived-from" || fn === "derived-from-or-self") {
      if (args.length !== 2) {
        return false;
      }
      const rootSchema = context.root?.schema;
      if (!(rootSchema instanceof YangModule)) {
        return false;
      }
      const importer = rootSchema;
      const start = context.current ?? node;
      let v1 = this.eval(args[0], context, start);
      if (isNodeSet(v1)) {
        if (v1.length === 0) {
          return false;
        }
        v1 = v1[0].data;
      } else if (isNode(v1)) {
        v1 = v1.data;
      } else {
        v1 = firstValue(v1);
      }
      if (typeof v1 !== "string") {
        return false;
      }
      const v2Raw = this.eval(args[1], context, start);
      const v2 = firstValue(v2Raw);
      if (typeof v2 !== "string") {
        return false;
      }
      if (fn === "derived-from") {
        return isDerivedFromStrictQNames(importer, v1, v2);
      }
      return isDerivedFromOrSelfQNames(importer, v1, v2);
    }
    return null;
  }
};

// src/validator/type-validation-debug.ts
function summarizeValue(value) {
  if (value === null) {
    return "null";
  }
  const t = typeof value;
  if (t === "undefined") {
    return "undefined";
  }
  if (typeof value === "string") {
    const s = value;
    if (s.length > 100) {
      return `string(len=${s.length}):${JSON.stringify(s.slice(0, 80))}\u2026`;
    }
    return JSON.stringify(s);
  }
  if (t === "number" || t === "boolean" || t === "bigint") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `Array(${value.length})`;
  }
  if (t === "object") {
    try {
      const j = JSON.stringify(value);
      return j.length > 160 ? `${j.slice(0, 160)}\u2026` : j;
    } catch {
      return "[object]";
    }
  }
  return String(value);
}
function traceTypeValidation(enabled, message, fields) {
  if (!enabled) {
    return;
  }
  console.debug(`[xYang:type-validation] ${message}`, fields);
}

// src/validator/type-checker.ts
var TypeChecker = class {
  constructor(module, options = {}) {
    this.module = module;
    this.typeValidationDebug = options.typeValidationDebug === true;
  }
  module;
  system = new TypeSystem();
  typeValidationDebug;
  /**
   * Follow a typedef chain to the underlying builtin type name (stops at unions or unknown).
   */
  resolveUnderlyingBuiltinName(typeName) {
    const seen = /* @__PURE__ */ new Set();
    let name = typeName;
    while (seen.size < 64) {
      const typedef = this.module.typedefs[name];
      if (!typedef?.type || typeof typedef.type.name !== "string") {
        return name;
      }
      if (typedef.type.name === "union" /* UNION */) {
        return name;
      }
      seen.add(name);
      const next = typedef.type.name;
      if (next === name) {
        return name;
      }
      name = next;
    }
    return name;
  }
  validate(value, typeName, constraint) {
    let via;
    let result;
    const typedef = this.module.typedefs[typeName];
    if (typedef?.type && typeof typedef.type.name === "string") {
      const typedefConstraint = new TypeConstraint(typedef.type);
      if (typedef.type.name === "union" /* UNION */) {
        via = "typedef-union";
        result = this.validateUnion(value, typedefConstraint);
      } else {
        via = "typedef";
        result = this.system.validate(value, typedef.type.name, typedefConstraint);
      }
    } else {
      const merged = new TypeConstraint(constraint);
      if (typeName === "union" /* UNION */ && (merged.types?.length ?? 0) > 0) {
        via = "inline-union";
        result = this.validateUnion(value, merged);
      } else {
        via = "direct";
        result = this.system.validate(value, typeName, merged);
      }
    }
    traceTypeValidation(this.typeValidationDebug, "TypeChecker.validate", {
      module: this.module.name ?? "(anonymous)",
      typeName,
      via,
      ok: result[0],
      reason: result[1],
      value: summarizeValue(value)
    });
    return result;
  }
  /** Union members may name typedefs; validate through this checker so typedefs resolve. */
  validateUnion(value, constraint) {
    traceTypeValidation(this.typeValidationDebug, "TypeChecker.validateUnion", {
      module: this.module.name ?? "(anonymous)",
      memberCount: constraint.types?.length ?? 0,
      value: summarizeValue(value)
    });
    for (const member of constraint.types ?? []) {
      const memberObj = member;
      const memberName = typeof memberObj.name === "string" ? memberObj.name : "string" /* STRING_KW */;
      const [ok] = this.validate(value, memberName, memberObj);
      if (ok) {
        return [true, null];
      }
    }
    return [false, "Value does not match any union member type"];
  }
};

// src/validator/document-validator.ts
var DocumentValidator = class {
  xpath = new XPathEvaluator();
  xpathCache = /* @__PURE__ */ new Map();
  rootCtx;
  enabledFeaturesOverride;
  contextStack = [];
  typeValidationDebug;
  constructor(module, options = {}) {
    this.enabledFeaturesOverride = options.enabledFeaturesByModule ?? null;
    this.typeValidationDebug = options.typeValidationDebug === true;
    const constraintChecks = options.constraintChecks ?? true;
    const leafTypeMode = options.leafTypeMode ?? (constraintChecks ? "full" : "none");
    const ifFeatureCtx = module.data;
    this.rootCtx = {
      module,
      typeChecker: new TypeChecker(module, { typeValidationDebug: this.typeValidationDebug }),
      constraintChecks,
      leafTypeMode,
      typeValidationDebug: this.typeValidationDebug,
      anydataValidation: void 0,
      ifFeatureCtx,
      enabledByModule: buildEnabledFeaturesMap(ifFeatureCtx, this.enabledFeaturesOverride)
    };
  }
  /** When true, this validator emits `console.debug` lines for leaf type checks. */
  setTypeValidationDebug(on) {
    this.typeValidationDebug = on;
    this.rootCtx.typeValidationDebug = on;
    this.rootCtx.typeChecker = new TypeChecker(this.rootCtx.module, {
      typeValidationDebug: this.typeValidationDebug
    });
  }
  get ctx() {
    const c = this.contextStack[this.contextStack.length - 1];
    if (!c) {
      throw new Error("DocumentValidator: internal error \u2014 no active validation context");
    }
    return c;
  }
  enableExtension(extension, config) {
    if (extension !== "anydata_validation" /* ANYDATA_VALIDATION */) {
      throw new Error(`unknown validator extension: ${String(extension)}`);
    }
    this.rootCtx.anydataValidation = parseAnydataExtensionConfig(config);
  }
  validate(data) {
    return this.validateWithContext(this.rootCtx, data);
  }
  /**
   * Validate instance data against one module’s top-level data nodes. Used for the root document
   * and, recursively, for each anydata payload shape without constructing a second DocumentValidator.
   */
  validateWithContext(ctx, data) {
    this.contextStack.push(ctx);
    try {
      const errors = [];
      const warnings = [];
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        return [false, ["Document must be an object"], warnings];
      }
      const root = data;
      const rootNode = { data: root, schema: ctx.module, parent: null };
      for (const stmt of ctx.module.statements) {
        if (!stmt.name) {
          continue;
        }
        const keyword = this.effectiveKeyword(stmt);
        if (![
          "container" /* CONTAINER */,
          "list" /* LIST */,
          "leaf" /* LEAF */,
          "leaf-list" /* LEAF_LIST */,
          "anydata" /* ANYDATA */,
          "anyxml" /* ANYXML */,
          "choice" /* CHOICE */
        ].includes(keyword)) {
          continue;
        }
        this.validateStatement(stmt, root[stmt.name], stmt.name, errors, rootNode, rootNode);
      }
      return [errors.length === 0, errors, warnings];
    } finally {
      this.contextStack.pop();
    }
  }
  validateStatement(stmt, value, path, errors, parentNode, rootNode) {
    const keyword = this.effectiveKeyword(stmt);
    const currentNode = { data: value, schema: stmt, parent: parentNode };
    if (keyword === "choice" /* CHOICE */) {
      this.validateChoice(stmt, parentNode.data, path, errors, parentNode, rootNode);
      return;
    }
    if (keyword === "case" /* CASE */) {
      if (!parentNode.data || typeof parentNode.data !== "object" || Array.isArray(parentNode.data)) {
        return;
      }
      const obj = parentNode.data;
      for (const child of stmt.statements) {
        if (!child.name) {
          continue;
        }
        this.validateStatement(child, obj[child.name], `${path}.${child.name}`, errors, parentNode, rootNode);
      }
      return;
    }
    const ifFeatures = stmt.data.if_features;
    const ifFeatureList = Array.isArray(ifFeatures) ? ifFeatures : [];
    if (!stmtIfFeaturesSatisfied(ifFeatureList, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
      if (value !== void 0) {
        errors.push(
          `${path}: Node '${stmt.name ?? "node"}' is present but its 'if-feature' condition is false \u2014 this node must not exist`
        );
      }
      return;
    }
    if (this.ctx.constraintChecks && !this.checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode)) {
      return;
    }
    if (keyword === "container" /* CONTAINER */) {
      if (value === void 0) {
        if (!stmt.data.presence) {
          this.validateMandatoryChildren(stmt, void 0, path, errors, currentNode, rootNode);
        }
        return;
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        errors.push(`${path}: container must be an object`);
        return;
      }
      const obj = value;
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      for (const child of stmt.statements) {
        const childKw = this.effectiveKeyword(child);
        if (childKw === "choice" /* CHOICE */) {
          this.validateChoice(child, obj, `${path}.${child.name ?? "choice"}`, errors, currentNode, rootNode);
          continue;
        }
        if (!child.name) {
          continue;
        }
        this.validateStatement(child, obj[child.name], `${path}.${child.name}`, errors, currentNode, rootNode);
      }
      if (this.ctx.constraintChecks) {
        this.rejectUnknownContainerKeys(stmt, obj, path, errors);
      }
      return;
    }
    if (keyword === "list" /* LIST */) {
      if (value === void 0) {
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(`${path}: list must be an array`);
        return;
      }
      const keyRaw = typeof stmt.data.key === "string" ? stmt.data.key.trim() : "";
      const keyNames = keyRaw.length > 0 ? keyRaw.split(/\s+/).map((k) => k.trim()).filter(Boolean) : [];
      if (this.ctx.constraintChecks && keyNames.length > 0 && this.checkListKeyUniqueness(value, keyNames, stmt.name ?? "list", path, errors)) {
        return;
      }
      for (let i = 0; i < value.length; i += 1) {
        const item = value[i];
        if (!item || typeof item !== "object" || Array.isArray(item)) {
          errors.push(`${path}[${i}]: list item must be an object`);
          continue;
        }
        const itemNode = { data: item, schema: stmt, parent: parentNode };
        if (this.ctx.constraintChecks) {
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
        const row = item;
        for (const child of stmt.statements) {
          const childKw = this.effectiveKeyword(child);
          if (childKw === "choice" /* CHOICE */) {
            this.validateChoice(child, row, `${path}[${i}].${child.name ?? "choice"}`, errors, itemNode, rootNode);
            continue;
          }
          if (!child.name) {
            continue;
          }
          this.validateStatement(child, row[child.name], `${path}[${i}].${child.name}`, errors, itemNode, rootNode);
        }
        if (this.ctx.constraintChecks) {
          this.rejectUnknownListItemKeys(stmt, row, `${path}[${i}]`, errors);
        }
      }
      return;
    }
    if (keyword === "leaf" /* LEAF */) {
      const mandatory = Boolean(stmt.data.mandatory);
      if (value === void 0) {
        if (mandatory) {
          errors.push(`${path}: mandatory leaf is missing`);
        }
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = stmt.data.type ?? {};
        const typeName = typeShape.name ?? "string";
        if (typeName === "leafref" /* LEAFREF */) {
          this.checkLeafref(value, typeShape, path, errors, currentNode, rootNode);
        } else if (typeName === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
          this.checkInstanceIdentifier(value, typeShape, path, errors, currentNode, rootNode);
        } else {
          const [ok, reason] = this.ctx.typeChecker.validate(value, typeName, typeShape);
          traceTypeValidation(this.ctx.typeValidationDebug, "DocumentValidator.leaf:full", {
            path,
            typeName,
            leafTypeMode: this.ctx.leafTypeMode,
            constraintChecks: this.ctx.constraintChecks,
            ok,
            reason,
            value: summarizeValue(value)
          });
          if (!ok) {
            errors.push(`${path}: ${reason ?? `invalid value for type ${typeName}`}`);
          }
        }
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      return;
    }
    if (keyword === "leaf-list" /* LEAF_LIST */) {
      if (value === void 0) {
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(`${path}: leaf-list must be an array`);
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = stmt.data.type ?? {};
        const typeName = typeShape.name ?? "string";
        for (let i = 0; i < value.length; i += 1) {
          const itemNode = { data: value[i], schema: stmt, parent: parentNode };
          if (typeName === "leafref" /* LEAFREF */) {
            this.checkLeafref(value[i], typeShape, `${path}[${i}]`, errors, itemNode, rootNode);
          } else if (typeName === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
            this.checkInstanceIdentifier(value[i], typeShape, `${path}[${i}]`, errors, itemNode, rootNode);
          } else {
            const [ok, reason] = this.ctx.typeChecker.validate(value[i], typeName, typeShape);
            traceTypeValidation(this.ctx.typeValidationDebug, "DocumentValidator.leaf-list:full", {
              path: `${path}[${i}]`,
              typeName,
              leafTypeMode: this.ctx.leafTypeMode,
              constraintChecks: this.ctx.constraintChecks,
              ok,
              reason,
              value: summarizeValue(value[i])
            });
            if (!ok) {
              errors.push(`${path}[${i}]: ${reason ?? `invalid value for type ${typeName}`}`);
            }
          }
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
      }
      return;
    }
    if (keyword === "anydata" /* ANYDATA */ || keyword === "anyxml" /* ANYXML */) {
      const mandatory = Boolean(stmt.data.mandatory);
      if (value === void 0) {
        if (mandatory) {
          errors.push(`${path}: mandatory ${keyword} is missing`);
        }
        return;
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      if (keyword === "anydata" /* ANYDATA */) {
        this.runAnydataSubtreeValidation(stmt, value, path, errors);
      }
    }
  }
  collectSchemaInstanceKeys(stmt, keys) {
    if (!stmt) {
      return;
    }
    const kw = this.effectiveKeyword(stmt);
    if (kw === "choice" /* CHOICE */) {
      for (const c of stmt.statements ?? []) {
        if (c.keyword !== "case" /* CASE */) {
          continue;
        }
        for (const br of c.statements ?? []) {
          this.collectSchemaInstanceKeys(br, keys);
        }
      }
      return;
    }
    if (kw === "list" /* LIST */) {
      if (stmt.name) {
        keys.add(stmt.name);
      }
      return;
    }
    if (kw === "container" /* CONTAINER */) {
      const ch = stmt.statements ?? [];
      const onlyChoice = ch.length === 1 && this.effectiveKeyword(ch[0]) === "choice" /* CHOICE */;
      if (!onlyChoice && stmt.name) {
        keys.add(stmt.name);
      }
      for (const c of ch) {
        this.collectSchemaInstanceKeys(c, keys);
      }
      return;
    }
    if (stmt.name) {
      keys.add(stmt.name);
    }
  }
  /**
   * Reject extra JSON keys under the meta-model `array` container (array element shape).
   * A general unknown-key pass breaks nested choice wrappers (e.g. `inner_wrap` around a choice).
   */
  rejectUnknownContainerKeys(stmt, obj, path, errors) {
    if (stmt.data.presence) {
      return;
    }
    if (stmt.name !== "array") {
      return;
    }
    const children = stmt.statements ?? [];
    if (children.length !== 1 || this.effectiveKeyword(children[0]) !== "choice" /* CHOICE */) {
      return;
    }
    const allowed = /* @__PURE__ */ new Set();
    this.collectSchemaInstanceKeys(children[0], allowed);
    if (allowed.size === 0) {
      return;
    }
    for (const key of Object.keys(obj)) {
      if (!allowed.has(key)) {
        errors.push(`${path}: Unknown field '${key}'`);
      }
    }
  }
  rejectUnknownListItemKeys(stmt, row, path, errors) {
    const allowed = this.collectDirectChildKeys(stmt);
    if (allowed.size === 0) {
      return;
    }
    for (const key of Object.keys(row)) {
      if (!allowed.has(key)) {
        errors.push(`${path}: Unknown field '${key}'`);
      }
    }
  }
  collectDirectChildKeys(parent) {
    const keys = /* @__PURE__ */ new Set();
    const walk = (stmt) => {
      const kw = this.effectiveKeyword(stmt);
      if (kw === "choice" /* CHOICE */ || kw === "case" /* CASE */) {
        for (const child of stmt.statements ?? []) {
          walk(child);
        }
        return;
      }
      if (stmt.name) {
        keys.add(stmt.name);
      }
    };
    for (const child of parent.statements ?? []) {
      walk(child);
    }
    return keys;
  }
  validateChoice(choice, parentValue, path, errors, parentNode, rootNode) {
    if (!parentValue || typeof parentValue !== "object" || Array.isArray(parentValue)) {
      if (choice.data.mandatory === true) {
        errors.push(`${path}: mandatory choice has no active case`);
      }
      return;
    }
    const obj = parentValue;
    const choiceIfs = Array.isArray(choice.data.if_features) ? choice.data.if_features : [];
    const choiceActive = stmtIfFeaturesSatisfied(choiceIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule);
    if (!choiceActive && this.choiceHasBranchData(choice, obj)) {
      errors.push(
        `${path}: Choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false \u2014 this branch must not exist`
      );
      return;
    }
    if (!choiceActive) {
      return;
    }
    if (this.ctx.constraintChecks && !this.checkWhen(choice, this.choiceHasBranchData(choice, obj) ? true : void 0, path, errors, parentNode, rootNode, parentNode)) {
      return;
    }
    const cases = choice.statements.filter((child) => child.keyword === "case" /* CASE */);
    const activeCases = [];
    let hadBlockedCaseWithData = false;
    for (const c of cases) {
      if (!this.caseHasAnyData(c, obj)) {
        continue;
      }
      const caseIfs = Array.isArray(c.data.if_features) ? c.data.if_features : [];
      if (!stmtIfFeaturesSatisfied(caseIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
        errors.push(
          `${path}: Case '${c.name ?? "case"}' of choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false \u2014 this branch must not exist`
        );
        return;
      }
      if (this.ctx.constraintChecks && !this.checkWhen(c, true, `${path}.${c.name ?? "case"}`, errors, parentNode, rootNode, parentNode)) {
        hadBlockedCaseWithData = true;
        continue;
      }
      activeCases.push(c);
    }
    if (activeCases.length > 1) {
      const names = activeCases.map((c) => c.name ?? "<unnamed>").join(", ");
      errors.push(`${path}: choice '${choice.name ?? "choice"}' allows only one case, but multiple are active: ${names}`);
      return;
    }
    const active = activeCases[0];
    if (!active) {
      if (hadBlockedCaseWithData) {
        return;
      }
      if (choice.data.mandatory === true) {
        errors.push(`${path}: mandatory choice has no active case`);
      }
      return;
    }
    for (const child of active.statements) {
      if (!child.name) {
        continue;
      }
      this.validateStatement(child, obj[child.name], `${path}.${child.name}`, errors, parentNode, rootNode);
    }
  }
  choiceHasBranchData(choice, obj) {
    const cases = choice.statements.filter((child) => child.keyword === "case" /* CASE */);
    return cases.some((c) => this.caseHasAnyData(c, obj));
  }
  caseHasAnyData(caseStmt, obj) {
    return caseStmt.statements.some((child) => this.statementHasMatchingData(child, obj));
  }
  statementHasMatchingData(stmt, obj) {
    const keyword = this.effectiveKeyword(stmt);
    if ([
      "leaf" /* LEAF */,
      "leaf-list" /* LEAF_LIST */,
      "container" /* CONTAINER */,
      "list" /* LIST */,
      "anydata" /* ANYDATA */,
      "anyxml" /* ANYXML */
    ].includes(keyword)) {
      return Boolean(stmt.name && obj[stmt.name] !== void 0);
    }
    if (keyword === "choice" /* CHOICE */) {
      return this.choiceHasBranchData(stmt, obj);
    }
    if (keyword === "case" /* CASE */) {
      return this.caseHasAnyData(stmt, obj);
    }
    return false;
  }
  effectiveKeyword(stmt) {
    const raw = stmt.keyword ?? "";
    if (raw.includes(":")) {
      const kind = stmt.data.data_node_kind;
      if (kind === "container" /* CONTAINER */ || kind === "list" /* LIST */) {
        return kind;
      }
    }
    return raw;
  }
  /**
   * RFC 7950: list instance keys must be unique within the list.
   * @returns true if a duplicate was found (caller should skip per-entry validation).
   */
  checkListKeyUniqueness(val, keyNames, listName, pathStr, errors) {
    if (keyNames.length === 0) {
      return false;
    }
    const seenKeys = /* @__PURE__ */ new Map();
    for (let i = 0; i < val.length; i += 1) {
      const entry = val[i];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const row = entry;
      const keyTuple = keyNames.map((k) => row[k]);
      const keyStr = JSON.stringify(keyTuple);
      if (seenKeys.has(keyStr)) {
        const firstIdx = seenKeys.get(keyStr);
        const keyDisplay = keyNames.map((k) => `${k}='${String(row[k])}'`).join(", ");
        errors.push(
          `${pathStr}: Duplicate key in list '${listName}': ${keyDisplay} (entries at index ${firstIdx} and ${i})`
        );
        return true;
      }
      seenKeys.set(keyStr, i);
    }
    return false;
  }
  /**
   * RFC 7950 instance-identifier: string path; when require-instance is true, path must be absolute
   * and resolve to at least one node in the instance (same idea as Python DocumentValidator).
   */
  leafrefPathAst(typeShape) {
    const rawPath = typeShape.path;
    if (typeof rawPath === "string" && rawPath.trim().length > 0) {
      try {
        return parseXPathPath(rawPath.trim());
      } catch {
        return null;
      }
    }
    if (rawPath && typeof rawPath === "object" && !Array.isArray(rawPath) && rawPath.kind === "path") {
      return rawPath;
    }
    return null;
  }
  checkLeafref(value, typeShape, path, errors, leafContextNode, rootNode) {
    const requireInstance = typeShape.require_instance !== false;
    const ast = this.leafrefPathAst(typeShape);
    if (!ast || ast.kind !== "path") {
      if (requireInstance) {
        errors.push(`${path}: leafref has no path`);
      }
      return;
    }
    try {
      const context = { current: leafContextNode, root: rootNode };
      const result = this.xpath.eval(ast, context, leafContextNode);
      const nodes = Array.isArray(result) ? result : [];
      const allowed = /* @__PURE__ */ new Set();
      for (const n of nodes) {
        if (!n || typeof n !== "object" || !("data" in n)) {
          continue;
        }
        const v = n.data;
        if (v !== void 0 && v !== null && (typeof v === "string" || typeof v === "number" || typeof v === "boolean")) {
          allowed.add(String(v));
        }
      }
      if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
        errors.push(`${path}: leafref value must be a string, number, or boolean`);
        return;
      }
      const s = String(value);
      if (requireInstance && !allowed.has(s)) {
        errors.push(
          `${path}: leafref: value '${s}' does not reference an existing instance (require-instance is true)`
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(`${path}: leafref: error evaluating path (${msg})`);
    }
  }
  checkInstanceIdentifier(value, typeShape, path, errors, currentNode, rootNode) {
    if (typeof value !== "string") {
      errors.push(`${path}: instance-identifier value must be a string, got ${typeof value}`);
      return;
    }
    const requireInstance = typeShape.require_instance !== false;
    if (!requireInstance) {
      return;
    }
    const s = value.trim();
    if (!s) {
      errors.push(`${path}: instance-identifier path must not be empty when require-instance is true`);
      return;
    }
    let ast;
    try {
      ast = parseXPath(s);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(`${path}: instance-identifier: invalid path expression (${msg})`);
      return;
    }
    if (ast.kind !== "path") {
      errors.push(`${path}: instance-identifier: value must be a path expression (e.g. /top/leaf)`);
      return;
    }
    if (!ast.isAbsolute) {
      errors.push(`${path}: instance-identifier: only absolute paths are supported (path must start with '/')`);
      return;
    }
    const context = { current: currentNode, root: rootNode };
    try {
      const nodes = this.xpath.evalPath(ast, context, rootNode);
      if (nodes.length === 0) {
        errors.push(`${path}: instance-identifier: no instance at path ${JSON.stringify(value)} (require-instance is true)`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(`${path}: instance-identifier: invalid path expression (${msg})`);
    }
  }
  checkMust(stmt, currentNode, rootNode, path, errors) {
    const mustStatements = stmt.statements.filter((child) => child.keyword === "must" && typeof child.argument === "string");
    for (const mustStmt of mustStatements) {
      const expression = mustStmt.argument;
      let ast = this.xpathCache.get(expression);
      if (!ast) {
        try {
          ast = parseXPath(expression);
          this.xpathCache.set(expression, ast);
        } catch {
          errors.push(`${path}: Error evaluating must expression on '${stmt.name ?? "node"}'`);
          continue;
        }
      }
      try {
        const context = { current: currentNode, root: rootNode };
        const result = this.xpath.eval(ast, context, currentNode);
        const ok = this.xpathBoolean(result);
        if (!ok) {
          const errorMessage = typeof mustStmt.data.error_message === "string" && mustStmt.data.error_message.trim().length > 0 ? mustStmt.data.error_message : `must constraint not satisfied on '${stmt.name ?? "node"}'`;
          errors.push(`${path}: ${errorMessage}`);
        }
      } catch {
        errors.push(`${path}: Error evaluating must expression on '${stmt.name ?? "node"}'`);
      }
    }
  }
  checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode) {
    const whenShape = stmt.data.when;
    const expression = typeof whenShape?.expression === "string" ? whenShape.expression : void 0;
    if (!expression || expression.trim().length === 0) {
      return true;
    }
    let ast = this.xpathCache.get(expression);
    if (!ast) {
      try {
        ast = parseXPath(expression);
        this.xpathCache.set(expression, ast);
      } catch {
        errors.push(`${path}: Error evaluating when expression on '${stmt.name ?? "node"}'`);
        return false;
      }
    }
    try {
      const evaluateWithParentContext = whenShape?.evaluate_with_parent_context === true;
      const evalNode = evaluateWithParentContext ? parentNode : currentNode;
      const context = { current: evalNode, root: rootNode };
      const result = this.xpath.eval(ast, context, evalNode);
      const active = this.xpathBoolean(result);
      if (!active) {
        if (value !== void 0) {
          errors.push(`${path}: node is not allowed by when condition`);
        }
        return false;
      }
      return true;
    } catch {
      errors.push(`${path}: Error evaluating when expression on '${stmt.name ?? "node"}'`);
      return false;
    }
  }
  xpathBoolean(value) {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0 && !Number.isNaN(value);
    }
    if (typeof value === "string") {
      return value.length > 0;
    }
    return value !== null && value !== void 0;
  }
  validateMandatoryChildren(stmt, parentValue, path, errors, parentNode, rootNode) {
    const obj = parentValue && typeof parentValue === "object" && !Array.isArray(parentValue) ? parentValue : void 0;
    for (const child of stmt.statements) {
      const childKeyword = child.keyword ?? "";
      if (!["leaf" /* LEAF */, "anydata" /* ANYDATA */, "anyxml" /* ANYXML */].includes(childKeyword) || !child.name) {
        continue;
      }
      const cIf = Array.isArray(child.data.if_features) ? child.data.if_features : [];
      if (!stmtIfFeaturesSatisfied(cIf, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
        continue;
      }
      if (!child.data.mandatory) {
        continue;
      }
      const childValue = obj?.[child.name];
      const childNode = { data: childValue, schema: child, parent: parentNode };
      if (this.ctx.constraintChecks && !this.checkWhen(child, childValue, `${path}.${child.name}`, errors, childNode, rootNode, parentNode)) {
        continue;
      }
      if (!obj || obj[child.name] === void 0) {
        errors.push(`${path}.${child.name}: mandatory ${childKeyword} is missing`);
      }
    }
  }
  anydataModuleMap(modules) {
    const map = {};
    for (const mod of modules) {
      const n = mod.name;
      if (n) {
        map[n] = mod;
      }
    }
    return map;
  }
  /**
   * RFC 7951 qualified members under `anydata` (draft-ietf-netmod-yang-anydata-validation §4–§5).
   * Nested validation uses anydata-complete (full constraints) vs anydata-candidate (no constraint checks).
   */
  runAnydataSubtreeValidation(stmt, value, anydataPath, errors) {
    if (!this.ctx.anydataValidation || !value || typeof value !== "object" || Array.isArray(value)) {
      return;
    }
    const mode = this.ctx.anydataValidation.mode;
    const modules = this.ctx.anydataValidation.modules;
    const moduleMap = this.anydataModuleMap(modules);
    const obj = value;
    for (const [jsonKey, childVal] of Object.entries(obj)) {
      const { statementName, moduleName: moduleName2 } = resolveQualifiedTopLevel(jsonKey, moduleMap);
      if (!statementName || !moduleName2) {
        errors.push(
          `${anydataPath}.${jsonKey}: Unknown anydata member '${jsonKey}': no matching module:identifier in the provided modules`
        );
        continue;
      }
      const mod = moduleMap[moduleName2];
      const top = mod?.findStatement(statementName);
      if (!top) {
        errors.push(`${anydataPath}.${jsonKey}: Unknown anydata member '${jsonKey}'`);
        continue;
      }
      if (top.keyword === "leaf" /* LEAF */) {
        errors.push(
          `${anydataPath}.${jsonKey}: anydata member '${jsonKey}' maps to a leaf; nested subtree validation expects a container or list`
        );
        continue;
      }
      const fragment = { [statementName]: childVal };
      const payloadIfCtx = mod.data;
      const payloadCtx = {
        module: mod,
        typeChecker: new TypeChecker(mod, { typeValidationDebug: this.rootCtx.typeValidationDebug }),
        constraintChecks: mode === "complete" /* COMPLETE */,
        leafTypeMode: mode === "complete" /* COMPLETE */ ? "full" : "none",
        typeValidationDebug: this.rootCtx.typeValidationDebug,
        anydataValidation: void 0,
        ifFeatureCtx: payloadIfCtx,
        enabledByModule: buildEnabledFeaturesMap(payloadIfCtx, this.enabledFeaturesOverride)
      };
      const [ok, innerErrors] = this.validateWithContext(payloadCtx, fragment);
      if (!ok) {
        for (const error of innerErrors) {
          errors.push(`${anydataPath}.${jsonKey}: ${error}`);
        }
      }
    }
  }
};

// src/validator/yang-validator.ts
var YangValidator = class {
  constructor(module, options = {}) {
    this.module = module;
    this.documentValidator = new DocumentValidator(module, {
      enabledFeaturesByModule: options.enabledFeaturesByModule ?? null,
      typeValidationDebug: options.typeValidationDebug
    });
  }
  module;
  documentValidator;
  /**
   * Toggle `console.debug` tracing for leaf type checks performed by this validator only.
   */
  setTypeValidationDebug(on) {
    this.documentValidator.setTypeValidationDebug(on);
    return this;
  }
  enableExtension(extension, config) {
    this.documentValidator.enableExtension(extension, config);
  }
  enable_extension(extension, config) {
    this.enableExtension(extension, config);
  }
  validate(data) {
    const [isValid, errors, warnings] = this.documentValidator.validate(data);
    return { isValid, errors, warnings };
  }
};

// src/json/default-values.ts
var YANG_INT_TYPES = /* @__PURE__ */ new Set([
  "int8",
  "int16",
  "int32",
  "int64",
  "uint8",
  "uint16",
  "uint32",
  "uint64"
]);
function tryIntLiteral(value) {
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^-?\d+$/.test(trimmed)) {
      return Number.parseInt(trimmed, 10);
    }
  }
  return null;
}
function coerceDefaultValue(value, typeName) {
  if (value === void 0 || value === null || typeName === void 0) {
    return value;
  }
  if (typeName === "boolean") {
    if (value === true || value === "true") {
      return true;
    }
    if (value === false || value === "false") {
      return false;
    }
  }
  if (YANG_INT_TYPES.has(typeName)) {
    if (typeof value === "number" && Number.isInteger(value)) {
      return value;
    }
    const parsed = tryIntLiteral(value);
    if (parsed !== null) {
      return parsed;
    }
  }
  if (typeName === "decimal64" || typeName === "number") {
    if (typeof value === "number") {
      return value;
    }
    const n = Number(value);
    if (!Number.isNaN(n)) {
      return n;
    }
  }
  return value;
}
function jsonSchemaDefaultValue(defaultValue2, options = {}) {
  if (defaultValue2 === void 0 || defaultValue2 === null) {
    return defaultValue2;
  }
  const { yangTypeName = null, jsonSchemaType = null } = options;
  const typeName = yangTypeName ?? jsonSchemaType;
  if (typeName === "boolean" || jsonSchemaType === "boolean") {
    if (defaultValue2 === true || typeof defaultValue2 === "string" && defaultValue2.toLowerCase() === "true") {
      return true;
    }
    if (defaultValue2 === false || typeof defaultValue2 === "string" && defaultValue2.toLowerCase() === "false") {
      return false;
    }
  }
  if (yangTypeName === "union") {
    const numeric = tryIntLiteral(defaultValue2);
    if (numeric !== null) {
      return numeric;
    }
    return defaultValue2;
  }
  let coerceType = yangTypeName ?? void 0;
  if (jsonSchemaType === "integer" && (coerceType === void 0 || coerceType === "integer")) {
    coerceType = "int32";
  }
  if (jsonSchemaType === "number" && coerceType === void 0) {
    coerceType = "decimal64";
  }
  const coerced = coerceDefaultValue(defaultValue2, coerceType ?? void 0);
  if (coerced !== defaultValue2) {
    return coerced;
  }
  if (jsonSchemaType === "integer") {
    const numeric = tryIntLiteral(defaultValue2);
    if (numeric !== null) {
      return numeric;
    }
  }
  return defaultValue2;
}
function yangDefaultFromJsonSchema(defaultValue2, schemaType, yangTypeFromXyang) {
  if (defaultValue2 === void 0) {
    return void 0;
  }
  const xyType = yangTypeFromXyang ?? schemaType;
  if (xyType === "boolean" || schemaType === "boolean") {
    if (typeof defaultValue2 === "boolean") {
      return defaultValue2 ? "true" : "false";
    }
    if (typeof defaultValue2 === "string") {
      return defaultValue2.toLowerCase();
    }
  }
  if (schemaType === "integer" && typeof defaultValue2 === "number") {
    return String(Math.trunc(defaultValue2));
  }
  if (typeof defaultValue2 === "boolean") {
    return defaultValue2 ? "true" : "false";
  }
  if (typeof defaultValue2 === "number" && Number.isInteger(defaultValue2)) {
    return String(Math.trunc(defaultValue2));
  }
  return defaultValue2;
}

// src/json/schema-keys.ts
var YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
};
var XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs"
};

// src/json/type-constants.ts
var JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";
var JSON_TYPE_STRING = "string";
var JSON_TYPE_INTEGER = "integer";
var JSON_TYPE_NUMBER = "number";
var JSON_TYPE_BOOLEAN = "boolean";
var JSON_TYPE_OBJECT = "object";
var JSON_TYPE_ARRAY = "array";
var JSON_TYPE_NULL = "null";
var JSON_TYPE_FREE_FORM = [
  JSON_TYPE_STRING,
  JSON_TYPE_NUMBER,
  JSON_TYPE_BOOLEAN,
  JSON_TYPE_OBJECT,
  JSON_TYPE_ARRAY,
  JSON_TYPE_NULL
];
function fractionDigitsFromMultipleOf(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value >= 1) {
    return void 0;
  }
  let n = 0;
  let t = value;
  while (t < 1 && n < 18) {
    t *= 10;
    n += 1;
  }
  return t === 1 ? n : void 0;
}
function leafTypeToSchema(typeShape) {
  const typeName = typeShape.name ?? "string" /* STRING_KW */;
  if (typeName === "string" /* STRING_KW */) {
    const out = { type: JSON_TYPE_STRING };
    const rawPatterns = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
    const specs = rawPatterns.filter((x) => Boolean(x) && typeof x === "object" && !Array.isArray(x)).map((x) => ({
      pattern: typeof x.pattern === "string" ? x.pattern : "",
      invert_match: x.invert_match === true,
      error_message: typeof x.error_message === "string" ? x.error_message : void 0,
      error_app_tag: typeof x.error_app_tag === "string" ? x.error_app_tag : void 0
    })).filter((x) => x.pattern.length > 0);
    const anchored = (p) => p.startsWith("^") && p.endsWith("$") ? p : `^${p}$`;
    if (specs.length === 1 && !specs[0].invert_match) {
      out.pattern = anchored(specs[0].pattern);
    } else if (specs.length > 0) {
      out.allOf = specs.map(
        (spec) => spec.invert_match ? { not: { type: JSON_TYPE_STRING, pattern: anchored(spec.pattern) } } : { pattern: anchored(spec.pattern) }
      );
    }
    if (specs.length > 0) {
      const entries = specs.map((spec) => ({
        pattern: spec.pattern,
        "invert-match": spec.invert_match,
        ...spec.error_message ? { "pattern-error-message": spec.error_message } : {},
        ...spec.error_app_tag ? { "pattern-error-app-tag": spec.error_app_tag } : {}
      }));
      const xYang = { "string-patterns": entries };
      const last = entries[entries.length - 1];
      if (typeof last["pattern-error-message"] === "string") {
        xYang["pattern-error-message"] = last["pattern-error-message"];
      }
      if (typeof last["pattern-error-app-tag"] === "string") {
        xYang["pattern-error-app-tag"] = last["pattern-error-app-tag"];
      }
      out["x-yang"] = xYang;
    }
    if (typeof typeShape.length === "string") {
      const [rawMin, rawMax] = typeShape.length.split("..");
      const min = Number.parseInt((rawMin ?? "").trim(), 10);
      const maxRaw = (rawMax ?? "").trim().toLowerCase();
      const max = Number.parseInt((rawMax ?? "").trim(), 10);
      if (!Number.isNaN(min)) {
        out.minLength = min;
      }
      if (!Number.isNaN(max) && maxRaw !== "max") {
        out.maxLength = max;
      }
    }
    return out;
  }
  if (typeName in YANG_INTEGER_BOUNDS) {
    const out = { type: JSON_TYPE_INTEGER };
    const rangeStr = typeof typeShape.range === "string" ? typeShape.range : void 0;
    const { minimum, maximum } = jsonIntegerBoundsForBuiltin(typeName, rangeStr);
    if (minimum !== void 0) {
      out.minimum = minimum;
    }
    if (maximum !== void 0) {
      out.maximum = maximum;
    }
    return out;
  }
  if (["decimal64" /* DECIMAL64 */, JSON_TYPE_NUMBER].includes(typeName)) {
    const out = { type: JSON_TYPE_NUMBER };
    if (typeof typeShape.fraction_digits === "number" && typeShape.fraction_digits > 0) {
      out.multipleOf = 10 ** -typeShape.fraction_digits;
    }
    if (typeof typeShape.range === "string") {
      const [rawMin, rawMax] = typeShape.range.split("..");
      const minRaw = (rawMin ?? "").trim();
      const maxRaw = (rawMax ?? "").trim();
      const min = Number.parseFloat(minRaw);
      const max = Number.parseFloat(maxRaw);
      if (!Number.isNaN(min) && minRaw.toLowerCase() !== "min") {
        out.minimum = min;
      }
      if (!Number.isNaN(max) && maxRaw.toLowerCase() !== "max") {
        out.maximum = max;
      }
    }
    return out;
  }
  if (typeName === "boolean" /* BOOLEAN */) {
    return { type: JSON_TYPE_BOOLEAN };
  }
  if (typeName === "binary" /* BINARY */) {
    return { type: JSON_TYPE_STRING, contentEncoding: "base64" };
  }
  if (typeName === "empty" /* EMPTY */) {
    return { type: JSON_TYPE_OBJECT, maxProperties: 0 };
  }
  if (typeName === "enumeration" /* ENUMERATION */) {
    const enums = Array.isArray(typeShape.enums) ? typeShape.enums.filter((value) => typeof value === "string") : [];
    return enums.length > 0 ? { type: JSON_TYPE_STRING, enum: enums } : { type: JSON_TYPE_STRING };
  }
  if (typeName === "leafref" /* LEAFREF */ || typeName === "identityref" /* IDENTITYREF */ || typeName === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
    return { type: JSON_TYPE_STRING };
  }
  if (typeName === "union" /* UNION */) {
    const members = Array.isArray(typeShape.types) ? typeShape.types : [];
    return {
      oneOf: members.map((member) => leafTypeToSchema(member))
    };
  }
  return { type: JSON_TYPE_FREE_FORM };
}
function schemaTypeToYangType(schema) {
  const type = schema.type;
  if (type === JSON_TYPE_STRING) {
    return "string" /* STRING_KW */;
  }
  if (type === JSON_TYPE_INTEGER) {
    const { name } = yangIntegerFromJsonBounds(schema.minimum, schema.maximum);
    return name;
  }
  if (type === JSON_TYPE_NUMBER) {
    return "decimal64" /* DECIMAL64 */;
  }
  if (type === JSON_TYPE_BOOLEAN) {
    return "boolean" /* BOOLEAN */;
  }
  return "string" /* STRING_KW */;
}
function decimal64FractionDigitsFromSchema(schema) {
  return fractionDigitsFromMultipleOf(schema.multipleOf);
}

// src/json/generator.ts
function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function isSchemaDataNode(stmt) {
  return [
    "container" /* CONTAINER */,
    "list" /* LIST */,
    "leaf" /* LEAF */,
    "leaf-list" /* LEAF_LIST */,
    "choice" /* CHOICE */,
    "case" /* CASE */,
    "anydata" /* ANYDATA */,
    "anyxml" /* ANYXML */
  ].includes(stmt.keyword ?? "");
}
function pathHasPredicate(path) {
  if (typeof path === "string") {
    return path.includes("[");
  }
  const shape = asRecord(path);
  if (shape.kind !== "path") {
    return false;
  }
  const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
  return segmentsRaw.some((seg) => {
    const s = asRecord(seg);
    return s.predicate !== void 0 && s.predicate !== null;
  });
}
function pathText(path) {
  if (typeof path === "string") {
    return path;
  }
  const shape = asRecord(path);
  if (shape.kind !== "path") {
    return "";
  }
  const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
  const segments = segmentsRaw.map((seg) => asRecord(seg).step).filter((step) => typeof step === "string" && step.length > 0);
  if (segments.length === 0) {
    return "";
  }
  const absolute = shape.isAbsolute === true;
  return `${absolute ? "/" : ""}${segments.join("/")}`;
}
function mustToXYang(stmt) {
  const out = [];
  for (const child of stmt.statements) {
    if (child.keyword !== "must" /* MUST */ || typeof child.argument !== "string") {
      continue;
    }
    out.push({
      must: child.argument,
      "error-message": typeof child.data.error_message === "string" ? child.data.error_message : "",
      description: typeof child.data.description === "string" ? child.data.description : ""
    });
  }
  return out;
}
function explicitConfig(stmt) {
  const cfg = stmt.data.config;
  return typeof cfg === "boolean" ? cfg : void 0;
}
function withStatementMeta(stmt, meta) {
  const out = { ...meta };
  const config = explicitConfig(stmt);
  if (config !== void 0) {
    out[XYANG_KEYS.config] = config;
  }
  const ifFeatures = Array.isArray(stmt.data.if_features) ? stmt.data.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
  if (ifFeatures.length > 0) {
    out["if-features"] = ifFeatures;
  }
  const whenShape = asRecord(stmt.data.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut = { condition: whenExpression };
    const wd = typeof whenShape.description === "string" && whenShape.description.trim().length > 0 ? whenShape.description.trim() : "";
    if (wd.length > 0) {
      whenOut.description = wd;
    }
    out.when = whenOut;
  }
  const presenceRaw = stmt.data.presence;
  if (typeof presenceRaw === "string" && presenceRaw.trim().length > 0) {
    out.presence = presenceRaw;
  }
  const must = mustToXYang(stmt);
  if (must.length > 0) {
    out.must = must;
  }
  return out;
}
function resolveAbsoluteLeafTypePath(module, path) {
  if (pathHasPredicate(path)) {
    return void 0;
  }
  let segments;
  if (typeof path === "string") {
    if (!path.startsWith("/")) {
      return void 0;
    }
    segments = path.split("/").map((x) => x.trim()).filter(Boolean);
  } else {
    const shape = asRecord(path);
    if (shape.kind !== "path" || shape.isAbsolute !== true) {
      return void 0;
    }
    const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
    segments = segmentsRaw.map((seg) => asRecord(seg).step).filter((step) => typeof step === "string" && step.length > 0);
  }
  if (segments.length === 0) {
    return void 0;
  }
  let level = module.statements;
  let current;
  for (const seg of segments) {
    const name = seg.includes(":") ? seg.split(":")[1] : seg;
    current = level.find((stmt) => stmt.name === name);
    if (!current) {
      return void 0;
    }
    level = current.statements;
  }
  if (current?.keyword !== "leaf" /* LEAF */) {
    return void 0;
  }
  return asRecord(current.data.type);
}
function typedefRefOrInline(typeShape, typedefNames) {
  const typeName = typeof typeShape.name === "string" ? typeShape.name : "";
  if (typedefNames.has(typeName)) {
    return { $ref: `#/$defs/${typeName}` };
  }
  return leafTypeToSchema(typeShape);
}
function partitionChoiceSiblings(children) {
  const choices = children.filter((c) => c.keyword === "choice" /* CHOICE */);
  const others = children.filter((c) => c.keyword !== "choice" /* CHOICE */);
  if (choices.length === 1) {
    return { others, soleChoice: choices[0] };
  }
  return { others: children, soleChoice: void 0 };
}
function mergeOneOfBranchesWithBase(oneOf, baseProps, baseRequired) {
  const merged = [];
  const baseReqUnique = [...new Set(baseRequired)];
  for (const branch of oneOf) {
    if (branch.type === JSON_TYPE_OBJECT && branch.maxProperties === 0) {
      if (Object.keys(baseProps).length > 0 || baseReqUnique.length > 0) {
        merged.push({
          type: JSON_TYPE_OBJECT,
          properties: { ...baseProps },
          required: [...baseReqUnique],
          additionalProperties: false
        });
      } else {
        merged.push({ ...branch });
      }
      continue;
    }
    const bp = asRecord(branch.properties);
    const br = Array.isArray(branch.required) ? branch.required.filter((x) => typeof x === "string") : [];
    const mergedBranch = {
      type: JSON_TYPE_OBJECT,
      properties: { ...baseProps, ...bp },
      required: [.../* @__PURE__ */ new Set([...baseRequired, ...br])].sort(),
      additionalProperties: false
    };
    const bDesc = branch.description;
    if (typeof bDesc === "string" && bDesc.length > 0) {
      mergedBranch.description = bDesc;
    }
    const bXy = branch[YANG_SCHEMA_KEYS.xYang];
    if (bXy && typeof bXy === "object" && !Array.isArray(bXy) && Object.keys(bXy).length > 0) {
      mergedBranch[YANG_SCHEMA_KEYS.xYang] = { ...bXy };
    }
    merged.push(mergedBranch);
  }
  return merged;
}
function choiceMetaForXYang(choice) {
  const meta = {
    name: choice.name ?? "",
    description: typeof choice.data.description === "string" ? choice.data.description : "",
    mandatory: choice.data.mandatory === true
  };
  const ifFeatures = Array.isArray(choice.data.if_features) ? choice.data.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
  if (ifFeatures.length > 0) {
    meta["if-features"] = ifFeatures;
  }
  return meta;
}
function buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames) {
  const properties = {};
  const required = [];
  for (const child of others) {
    if (!child.name || !isSchemaDataNode(child)) {
      continue;
    }
    properties[child.name] = statementToSchema(child, module, typedefNames);
    if (["leaf" /* LEAF */, "anydata" /* ANYDATA */, "anyxml" /* ANYXML */].includes(child.keyword ?? "") && child.data.mandatory === true) {
      required.push(child.name);
    }
  }
  const choiceShape = buildChoiceOneOf(soleChoice, module, typedefNames);
  const oneOfArr = choiceShape?.oneOf ?? [];
  if (Object.keys(properties).length === 0 && required.length === 0) {
    return { type: JSON_TYPE_OBJECT, oneOf: oneOfArr };
  }
  return {
    type: JSON_TYPE_OBJECT,
    oneOf: mergeOneOfBranchesWithBase(oneOfArr, properties, required)
  };
}
function ioBlockToSchema(stmt, module, typedefNames, ioType) {
  const body = buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
  return {
    ...body,
    description: typeof stmt.data.description === "string" ? stmt.data.description : "",
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: ioType })
  };
}
function rpcToJson(stmt, module, typedefNames) {
  const out = {
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: "rpc" /* RPC */ })
  };
  const inp = stmt.findStatement("input");
  if (inp?.keyword === "input" /* INPUT */) {
    out.input = ioBlockToSchema(inp, module, typedefNames, "input" /* INPUT */);
  }
  const outp = stmt.findStatement("output");
  if (outp?.keyword === "output" /* OUTPUT */) {
    out.output = ioBlockToSchema(outp, module, typedefNames, "output" /* OUTPUT */);
  }
  return out;
}
function buildMultiChildObjectSchema(statements, module, typedefNames) {
  const properties = {};
  const required = [];
  for (const child of statements) {
    if (child.keyword === "choice" /* CHOICE */) {
      if (!child.name) {
        continue;
      }
      properties[child.name] = statementToSchema(child, module, typedefNames);
      continue;
    }
    if (!child.name || !isSchemaDataNode(child)) {
      continue;
    }
    properties[child.name] = statementToSchema(child, module, typedefNames);
    if (["leaf" /* LEAF */, "anydata" /* ANYDATA */, "anyxml" /* ANYXML */].includes(child.keyword ?? "") && child.data.mandatory === true) {
      required.push(child.name);
    }
  }
  const out = {
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false
  };
  if (required.length > 0) {
    out.required = required;
  }
  return out;
}
function buildChoiceOneOf(choice, module, typedefNames) {
  const branches = [];
  const cases = choice.statements.filter((stmt) => stmt.keyword === "case" /* CASE */);
  const mandatory = choice.data.mandatory === true;
  if (!mandatory) {
    branches.push({ type: JSON_TYPE_OBJECT, maxProperties: 0 });
  }
  for (const c of cases) {
    const properties = {};
    const required = [];
    for (const child of c.statements) {
      if (!child.name || !isSchemaDataNode(child)) {
        continue;
      }
      properties[child.name] = statementToSchema(child, module, typedefNames);
      required.push(child.name);
    }
    if (Object.keys(properties).length === 0) {
      continue;
    }
    const branch = {
      type: JSON_TYPE_OBJECT,
      description: typeof c.data.description === "string" ? c.data.description : "",
      properties,
      additionalProperties: false,
      required,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(c, { name: c.name ?? "case" })
    };
    branches.push(branch);
  }
  if (branches.length === 0) {
    return void 0;
  }
  return {
    oneOf: branches
  };
}
function statementToSchema(stmt, module, typedefNames) {
  const keyword = stmt.keyword ?? "";
  if (keyword === "choice" /* CHOICE */) {
    const oneOfShape = buildChoiceOneOf(stmt, module, typedefNames);
    const xyChoice = {
      type: "choice",
      mandatory: stmt.data.mandatory === true
    };
    const choiceConfig = explicitConfig(stmt);
    if (choiceConfig !== void 0) {
      xyChoice[XYANG_KEYS.config] = choiceConfig;
    }
    const ifFeatures = Array.isArray(stmt.data.if_features) ? stmt.data.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
    if (ifFeatures.length > 0) {
      xyChoice["if-features"] = ifFeatures;
    }
    const out = {
      type: JSON_TYPE_OBJECT,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: xyChoice
    };
    if (oneOfShape?.oneOf) {
      out.oneOf = oneOfShape.oneOf;
    }
    return out;
  }
  if (keyword === "container" /* CONTAINER */) {
    const { others, soleChoice } = partitionChoiceSiblings(stmt.statements);
    const xYang = withStatementMeta(stmt, { type: keyword });
    if (soleChoice) {
      xYang.choice = choiceMetaForXYang(soleChoice);
    }
    const body = soleChoice ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames) : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out = {
      ...body,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: xYang
    };
    return out;
  }
  if (keyword === "list" /* LIST */) {
    const { others, soleChoice } = partitionChoiceSiblings(stmt.statements);
    const listXY = withStatementMeta(stmt, {
      type: keyword,
      key: typeof stmt.data.key === "string" ? stmt.data.key : void 0
    });
    if (soleChoice) {
      listXY.choice = choiceMetaForXYang(soleChoice);
    }
    const itemSchema = soleChoice ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames) : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: listXY
    };
    if (typeof stmt.data.min_elements === "number") {
      out.minItems = stmt.data.min_elements;
    }
    if (typeof stmt.data.max_elements === "number") {
      out.maxItems = stmt.data.max_elements;
    }
    return out;
  }
  if (keyword === "leaf-list" /* LEAF_LIST */) {
    const typeShape = asRecord(stmt.data.type);
    const itemSchema = typedefRefOrInline(typeShape, typedefNames);
    const typeName = typeShape.name ?? "string" /* STRING_KW */;
    const out = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    if (typeName === "leafref" /* LEAFREF */) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: "leafref" /* LEAFREF */,
        path: pathText(typeShape.path),
        "require-instance": typeShape.require_instance !== false
      };
      out.items = itemsXYang;
    }
    if (typeName === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: "instance-identifier" /* INSTANCE_IDENTIFIER */,
        "require-instance": typeShape.require_instance !== false
      };
      out.items = itemsXYang;
    }
    if (typeof stmt.data.min_elements === "number") {
      out.minItems = stmt.data.min_elements;
    }
    if (typeof stmt.data.max_elements === "number") {
      out.maxItems = stmt.data.max_elements;
    }
    const llDefaults = stmt.data.defaults;
    if (Array.isArray(llDefaults) && llDefaults.length > 0) {
      out.default = llDefaults;
    }
    return out;
  }
  if (keyword === "leaf" /* LEAF */) {
    const typeShape = asRecord(stmt.data.type);
    const typeName = typeShape.name ?? "string" /* STRING_KW */;
    let leafSchema = typedefRefOrInline(typeShape, typedefNames);
    if (typeName === "leafref" /* LEAFREF */) {
      const targetType = resolveAbsoluteLeafTypePath(module, typeShape.path);
      leafSchema = targetType ? typedefRefOrInline(targetType, typedefNames) : leafTypeToSchema({ name: "string" /* STRING_KW */ });
    }
    const xYang = withStatementMeta(stmt, {
      type: keyword
    });
    if (stmt.data.mandatory === true) {
      xYang.mandatory = true;
    }
    if (typeName === "leafref" /* LEAFREF */) {
      xYang.type = "leafref" /* LEAFREF */;
      xYang.path = pathText(typeShape.path);
      xYang["require-instance"] = typeShape.require_instance !== false;
    }
    if (typeName === "identityref" /* IDENTITYREF */) {
      xYang.type = "identityref" /* IDENTITYREF */;
      const bases = Array.isArray(typeShape.identityref_bases) ? typeShape.identityref_bases.filter((x) => typeof x === "string") : [];
      if (bases.length > 0) {
        xYang.bases = bases;
      }
    }
    if (typeName === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
      xYang.type = "instance-identifier" /* INSTANCE_IDENTIFIER */;
      xYang["require-instance"] = typeShape.require_instance !== false;
    }
    const schemaXy = asRecord(leafSchema[YANG_SCHEMA_KEYS.xYang]);
    const out = {
      ...leafSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: { ...xYang, ...schemaXy }
    };
    if (stmt.data.default !== void 0) {
      const schemaType = typeof out.type === "string" ? out.type : null;
      out.default = jsonSchemaDefaultValue(stmt.data.default, {
        yangTypeName: typeName,
        jsonSchemaType: schemaType
      });
    }
    return out;
  }
  if (keyword === "anydata" /* ANYDATA */ || keyword === "anyxml" /* ANYXML */) {
    const out = {
      type: JSON_TYPE_FREE_FORM,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    return out;
  }
  return {
    type: JSON_TYPE_FREE_FORM
  };
}
function typedefToSchema(module) {
  const out = {};
  const typedefs = module.typedefs;
  const names = new Set(Object.keys(typedefs));
  for (const [name, entry] of Object.entries(typedefs)) {
    const typeShape = asRecord(entry.type);
    const schema = typedefRefOrInline(typeShape, names);
    const def = {
      ...schema,
      description: typeof entry.description === "string" ? entry.description : ""
    };
    const schemaXy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
    const typedefXy = {};
    const rawPatList = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
    const lastPat = rawPatList.length > 0 ? rawPatList[rawPatList.length - 1] : null;
    if (lastPat && typeof lastPat.error_message === "string" && lastPat.error_message.length > 0) {
      typedefXy["pattern-error-message"] = lastPat.error_message;
    }
    if (lastPat && typeof lastPat.error_app_tag === "string" && lastPat.error_app_tag.length > 0) {
      typedefXy["pattern-error-app-tag"] = lastPat.error_app_tag;
    }
    if (Object.keys(schemaXy).length > 0 || Object.keys(typedefXy).length > 0) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...schemaXy, ...typedefXy };
    }
    out[name] = def;
  }
  return out;
}
function identityToSchema(module) {
  const raw = module.identities;
  const identityNames = Object.keys(raw);
  if (identityNames.length === 0) {
    return {};
  }
  const childrenByBase = {};
  for (const [identityName, info] of Object.entries(raw)) {
    const bases = Array.isArray(info?.bases) ? info.bases.filter((x) => typeof x === "string") : [];
    for (const base of bases) {
      if (!childrenByBase[base]) {
        childrenByBase[base] = [];
      }
      childrenByBase[base].push(identityName);
    }
  }
  const descendants = (name) => {
    const out = /* @__PURE__ */ new Set([name]);
    const stack = [...childrenByBase[name] ?? []];
    while (stack.length > 0) {
      const next = stack.pop();
      if (out.has(next)) {
        continue;
      }
      out.add(next);
      stack.push(...childrenByBase[next] ?? []);
    }
    return [...out].sort();
  };
  const defs = {};
  for (const [identityName, info] of Object.entries(raw)) {
    const bases = Array.isArray(info?.bases) ? info.bases.filter((x) => typeof x === "string") : [];
    defs[identityName] = {
      type: "string",
      enum: descendants(identityName),
      [YANG_SCHEMA_KEYS.xYang]: {
        type: "identity" /* IDENTITY */,
        ...bases.length > 0 ? { bases } : {}
      }
    };
  }
  return defs;
}
function generateJsonSchema(module) {
  const effectiveModule = expandUses(module);
  const properties = {};
  const required = [];
  const typedefNames = new Set(Object.keys(effectiveModule.typedefs));
  for (const stmt of effectiveModule.statements) {
    if (!stmt.name) {
      continue;
    }
    if (![
      "container" /* CONTAINER */,
      "list" /* LIST */,
      "leaf" /* LEAF */,
      "leaf-list" /* LEAF_LIST */,
      "anydata" /* ANYDATA */,
      "anyxml" /* ANYXML */
    ].includes(stmt.keyword ?? "")) {
      continue;
    }
    properties[stmt.name] = statementToSchema(stmt, effectiveModule, typedefNames);
    if (["leaf" /* LEAF */, "anydata" /* ANYDATA */, "anyxml" /* ANYXML */].includes(stmt.keyword ?? "") && stmt.data.mandatory === true) {
      required.push(stmt.name);
    }
  }
  const rootXYang = {
    module: effectiveModule.name,
    "yang-version": effectiveModule.yangVersion ?? "1.1",
    namespace: effectiveModule.namespace,
    prefix: effectiveModule.prefix,
    organization: effectiveModule.organization ?? "",
    contact: effectiveModule.contact ?? ""
  };
  const rpcs = {};
  for (const stmt of effectiveModule.statements) {
    if (stmt.keyword === "rpc" /* RPC */ && stmt.name) {
      rpcs[stmt.name] = rpcToJson(stmt, effectiveModule, typedefNames);
    }
  }
  if (Object.keys(rpcs).length > 0) {
    rootXYang[XYANG_KEYS.rpcs] = rpcs;
  }
  const schema = {
    $schema: JSON_SCHEMA_DRAFT_2020_12,
    $id: effectiveModule.namespace ? effectiveModule.namespace : effectiveModule.name ? `urn:${effectiveModule.name}` : "urn:module",
    description: effectiveModule.description ?? "",
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false,
    [YANG_SCHEMA_KEYS.xYang]: rootXYang
  };
  if (required.length > 0) {
    schema.required = required;
  }
  const defs = {
    ...typedefToSchema(effectiveModule),
    ...identityToSchema(effectiveModule)
  };
  if (Object.keys(defs).length > 0) {
    schema.$defs = defs;
  }
  return schema;
}

// src/json/parser.ts
function asRecord2(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function setConfigFromXyang(stmt, xyang) {
  if (XYANG_KEYS.config in xyang && typeof xyang[XYANG_KEYS.config] === "boolean") {
    stmt.config = xyang[XYANG_KEYS.config];
  }
}
function resolveSchema(schema, defs) {
  const ref = schema.$ref;
  if (typeof ref === "string" && ref.startsWith("#/$defs/")) {
    const name = ref.slice("#/$defs/".length);
    const d = defs[name];
    if (d && typeof d === "object") {
      return resolveSchema(d, defs);
    }
  }
  return schema;
}
function resolveSchemaWithOverlay(schema, defs) {
  const base = resolveSchema(schema, defs);
  const baseXy = asRecord2(base[YANG_SCHEMA_KEYS.xYang]);
  const overlayXy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  return {
    ...base,
    ...schema,
    [YANG_SCHEMA_KEYS.xYang]: { ...baseXy, ...overlayXy }
  };
}
function refToTypedefName(ref) {
  if (typeof ref !== "string" || !ref.startsWith("#/$defs/")) {
    return void 0;
  }
  const name = ref.slice("#/$defs/".length);
  return name.trim().length > 0 ? name : void 0;
}
function whenFromXyang(xy) {
  const w = xy.when;
  if (!w || typeof w !== "object") {
    return void 0;
  }
  const o = asRecord2(w);
  const expression = typeof o.condition === "string" ? o.condition : "";
  if (!expression.trim()) {
    return void 0;
  }
  return {
    expression,
    description: typeof o.description === "string" ? o.description : "",
    evaluate_with_parent_context: Boolean(o.evaluate_with_parent_context)
  };
}
function mustStatementsFromXyang(xy) {
  const raw = xy.must;
  if (!Array.isArray(raw)) {
    return [];
  }
  const out = [];
  for (const item of raw) {
    const e = asRecord2(item);
    const expr = typeof e.must === "string" ? e.must : "";
    if (!expr.trim()) {
      continue;
    }
    out.push({
      __class__: "YangStatement",
      keyword: "must",
      name: expr,
      argument: expr,
      error_message: typeof e["error-message"] === "string" ? e["error-message"] : "",
      statements: []
    });
  }
  return out;
}
function applyStatementMetaFromXyang(stmt, xy) {
  const when = whenFromXyang(xy);
  if (when) {
    stmt.when = when;
  }
  setConfigFromXyang(stmt, xy);
  if (Array.isArray(xy["if-features"])) {
    stmt.if_features = xy["if-features"].filter((x) => typeof x === "string");
  }
}
function typeShapeFromJsonLeaf(schema, xy) {
  if (xy.type === "leafref" /* LEAFREF */) {
    const path = typeof xy.path === "string" ? xy.path : "";
    if (path) {
      parseXPathPath(path);
    }
    return {
      name: "leafref" /* LEAFREF */,
      path,
      require_instance: xy["require-instance"] !== false
    };
  }
  if (xy.type === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
    return {
      name: "instance-identifier" /* INSTANCE_IDENTIFIER */,
      require_instance: xy["require-instance"] !== false
    };
  }
  if (xy.type === "identityref" /* IDENTITYREF */) {
    const bases = Array.isArray(xy.bases) ? xy.bases.filter((x) => typeof x === "string") : [];
    return { name: "identityref" /* IDENTITYREF */, identityref_bases: bases };
  }
  const typedefRef = refToTypedefName(schema.$ref);
  if (typedefRef) {
    return { name: typedefRef };
  }
  if (schema.type === JSON_TYPE_OBJECT && schema.maxProperties === 0) {
    return { name: "empty" /* EMPTY */ };
  }
  const hasStringEnum = schema.type === JSON_TYPE_STRING && Array.isArray(schema.enum);
  const shape = {};
  if (schema.type === JSON_TYPE_INTEGER) {
    const inferred = yangIntegerFromJsonBounds(schema.minimum, schema.maximum);
    shape.name = inferred.name;
    if (inferred.range) {
      shape.range = inferred.range;
    }
  } else {
    shape.name = hasStringEnum ? "enumeration" /* ENUMERATION */ : schemaTypeToYangType(schema);
  }
  const name = shape.name;
  if (name === "decimal64" /* DECIMAL64 */) {
    const fd = decimal64FractionDigitsFromSchema(schema);
    if (typeof fd === "number") {
      shape.fraction_digits = fd;
    }
  }
  if (typeof schema.minLength === "number" || typeof schema.maxLength === "number") {
    const min = typeof schema.minLength === "number" ? `${schema.minLength}` : "min";
    const max = typeof schema.maxLength === "number" ? `${schema.maxLength}` : "max";
    shape.length = `${min}..${max}`;
  }
  if (schema.type !== JSON_TYPE_INTEGER && (typeof schema.minimum === "number" || typeof schema.maximum === "number")) {
    const minNum = typeof schema.minimum === "number" ? schema.minimum : void 0;
    const maxNum = typeof schema.maximum === "number" ? schema.maximum : void 0;
    const decimalContext = minNum !== void 0 && !Number.isInteger(minNum) || maxNum !== void 0 && !Number.isInteger(maxNum);
    const fmt = (n) => {
      if (decimalContext && Number.isInteger(n)) {
        return `${n}.0`;
      }
      return `${n}`;
    };
    const min = minNum !== void 0 ? fmt(minNum) : "min";
    const max = maxNum !== void 0 ? fmt(maxNum) : "max";
    shape.range = `${min}..${max}`;
  }
  const rawPatternEntries = Array.isArray(xy["string-patterns"]) ? xy["string-patterns"] : [];
  const parsedPatternEntries = rawPatternEntries.filter((x) => Boolean(x) && typeof x === "object" && !Array.isArray(x)).map((x) => ({
    pattern: typeof x.pattern === "string" ? x.pattern : "",
    invert_match: x["invert-match"] === true,
    error_message: typeof x["pattern-error-message"] === "string" ? x["pattern-error-message"] : void 0,
    error_app_tag: typeof x["pattern-error-app-tag"] === "string" ? x["pattern-error-app-tag"] : void 0
  })).filter((x) => x.pattern.length > 0);
  let patternList = [];
  if (parsedPatternEntries.length > 0) {
    patternList = parsedPatternEntries;
  } else if (Array.isArray(schema.allOf)) {
    const fallbackEntries = schema.allOf.filter((x) => Boolean(x) && typeof x === "object" && !Array.isArray(x)).map((entry) => {
      if (typeof entry.pattern === "string") {
        return { pattern: entry.pattern, invert_match: false };
      }
      const notObj = asRecord2(entry.not);
      if (typeof notObj.pattern === "string") {
        return { pattern: notObj.pattern, invert_match: true };
      }
      return null;
    }).filter((x) => Boolean(x)).map((x) => {
      const p = x.pattern.startsWith("^") && x.pattern.endsWith("$") ? x.pattern.slice(1, -1) : x.pattern;
      return { pattern: p, invert_match: x.invert_match };
    });
    if (fallbackEntries.length > 0) {
      patternList = fallbackEntries;
    }
  } else if (name === "string" /* STRING_KW */ && typeof schema.pattern === "string") {
    let p = schema.pattern;
    if (p.startsWith("^") && p.endsWith("$")) {
      p = p.slice(1, -1);
    }
    patternList = [{ pattern: p, invert_match: false }];
  }
  const pem = typeof xy["pattern-error-message"] === "string" && xy["pattern-error-message"].length > 0 ? xy["pattern-error-message"] : void 0;
  const pet = typeof xy["pattern-error-app-tag"] === "string" && xy["pattern-error-app-tag"].length > 0 ? xy["pattern-error-app-tag"] : void 0;
  if (patternList.length > 0) {
    const last = patternList[patternList.length - 1];
    if (pem !== void 0 && last.error_message === void 0) {
      last.error_message = pem;
    }
    if (pet !== void 0 && last.error_app_tag === void 0) {
      last.error_app_tag = pet;
    }
    shape.patterns = patternList;
  }
  const unionItems = Array.isArray(schema.oneOf) ? schema.oneOf : Array.isArray(schema.anyOf) ? schema.anyOf : [];
  if (unionItems.length > 0) {
    const types = unionItems.filter((entry) => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry)).map((entry) => typeShapeFromJsonLeaf(entry, asRecord2(entry[YANG_SCHEMA_KEYS.xYang])));
    if (types.length > 0) {
      return { name: "union" /* UNION */, types };
    }
  }
  if (hasStringEnum) {
    const enumValues = Array.isArray(schema.enum) ? schema.enum : [];
    shape.enums = enumValues.filter((x) => typeof x === "string");
  }
  return shape;
}
function parseLeaf(name, schema, defs) {
  const resolved = resolveSchemaWithOverlay(schema, defs);
  const xy = asRecord2(resolved[YANG_SCHEMA_KEYS.xYang]);
  const typeShape = typeShapeFromJsonLeaf(resolved, xy);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out = {
    __class__: "YangStatement",
    keyword: "leaf" /* LEAF */,
    name,
    argument: name,
    type: typeShape,
    statements: musts
  };
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  if (typeof resolved.description === "string" && resolved.description.length > 0) {
    out.description = resolved.description;
  }
  if (resolved.default !== void 0) {
    const schemaType = typeof resolved.type === "string" ? resolved.type : void 0;
    const xyType = typeof xy.type === "string" ? xy.type : void 0;
    out.default = yangDefaultFromJsonSchema(resolved.default, schemaType, xyType);
  }
  if (when) {
    out.when = when;
  }
  if (Array.isArray(xy["if-features"])) {
    const feats = xy["if-features"].filter((x) => typeof x === "string" && x.trim().length > 0);
    if (feats.length > 0) {
      out.if_features = feats;
    }
  }
  setConfigFromXyang(out, xy);
  return out;
}
function extractChoiceBranches(schema) {
  const branches = [];
  if (Array.isArray(schema.oneOf)) {
    for (const item of schema.oneOf) {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        branches.push(item);
      }
    }
  }
  if (Array.isArray(schema.allOf)) {
    for (const entry of schema.allOf) {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const obj = entry;
      if (!Array.isArray(obj.oneOf)) {
        continue;
      }
      if (Object.keys(obj).some((k) => k !== "oneOf")) {
        continue;
      }
      for (const item of obj.oneOf) {
        if (item && typeof item === "object" && !Array.isArray(item)) {
          branches.push(item);
        }
      }
    }
  }
  return branches;
}
function splitChoiceCommonProperties(branches) {
  const input = Array.isArray(branches) ? branches : [];
  const nonEmpty = input.filter(
    (b) => !(b.type === JSON_TYPE_OBJECT && b.maxProperties === 0)
  );
  if (nonEmpty.length === 0) {
    return { commonProps: {}, strippedBranches: input };
  }
  const propMaps = nonEmpty.map((b) => asRecord2(b.properties));
  const keySets = propMaps.map((p) => new Set(Object.keys(p)));
  const intersection = new Set(keySets[0]);
  for (let i = 1; i < keySets.length; i += 1) {
    for (const k of [...intersection]) {
      if (!keySets[i].has(k)) {
        intersection.delete(k);
      }
    }
  }
  const commonProps = {};
  for (const key of intersection) {
    const first = propMaps[0][key];
    if (!first || typeof first !== "object" || Array.isArray(first)) {
      continue;
    }
    const firstJson = JSON.stringify(first);
    const sameAcross = propMaps.every((p) => JSON.stringify(p[key]) === firstJson);
    if (sameAcross) {
      commonProps[key] = first;
    }
  }
  if (Object.keys(commonProps).length === 0) {
    return { commonProps, strippedBranches: input };
  }
  const strippedBranches = input.map((b) => {
    const props = asRecord2(b.properties);
    const nextProps = {};
    for (const [k, v] of Object.entries(props)) {
      if (!(k in commonProps)) {
        nextProps[k] = v;
      }
    }
    const next = { ...b, properties: nextProps };
    if (Array.isArray(b.required)) {
      next.required = b.required.filter((x) => typeof x === "string" && !(x in commonProps));
    }
    return next;
  });
  return { commonProps, strippedBranches };
}
function parseChoice(name, schema, defs) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const choiceName = typeof xy.name === "string" && xy.name.length > 0 ? xy.name : name;
  const choiceStmt = {
    __class__: "YangStatement",
    keyword: "choice" /* CHOICE */,
    name: choiceName,
    argument: choiceName,
    mandatory: xy.mandatory === true,
    statements: []
  };
  if (Array.isArray(xy["if-features"])) {
    const feats = xy["if-features"].filter((x) => typeof x === "string" && x.trim().length > 0);
    if (feats.length > 0) {
      choiceStmt.if_features = feats;
    }
  }
  if (typeof xy.description === "string" && xy.description.length > 0) {
    choiceStmt.description = xy.description;
  } else if (typeof schema.description === "string" && schema.description.length > 0) {
    choiceStmt.description = schema.description;
  }
  setConfigFromXyang(choiceStmt, xy);
  let caseIndex = 0;
  for (const branchRaw of extractChoiceBranches(schema)) {
    const branch = asRecord2(branchRaw);
    if (branch.type === JSON_TYPE_OBJECT && branch.maxProperties === 0) {
      continue;
    }
    caseIndex += 1;
    const branchXy = asRecord2(branch[YANG_SCHEMA_KEYS.xYang]);
    const caseName = typeof branchXy.name === "string" && branchXy.name.length > 0 ? branchXy.name : `case-${caseIndex}`;
    const caseStmt = {
      __class__: "YangStatement",
      keyword: "case" /* CASE */,
      name: caseName,
      argument: caseName,
      statements: []
    };
    if (Array.isArray(branchXy["if-features"])) {
      const feats = branchXy["if-features"].filter(
        (x) => typeof x === "string" && x.trim().length > 0
      );
      if (feats.length > 0) {
        caseStmt.if_features = feats;
      }
    }
    if (typeof branchXy.description === "string" && branchXy.description.length > 0) {
      caseStmt.description = branchXy.description;
    } else if (typeof branch.description === "string" && branch.description.length > 0) {
      caseStmt.description = branch.description;
    }
    const branchProps = asRecord2(branch.properties);
    for (const [childName, childSchema] of Object.entries(branchProps)) {
      if (!childSchema || typeof childSchema !== "object") {
        continue;
      }
      const childStmt = jsonSchemaPropertyToStatement(childName, childSchema, defs);
      if (!childStmt) {
        continue;
      }
      caseStmt.statements.push(childStmt);
    }
    if (caseStmt.statements.length > 0) {
      choiceStmt.statements.push(caseStmt);
    }
  }
  return choiceStmt;
}
function parseAnydataOrAnyxml(name, schema, keyword) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out = {
    __class__: "YangStatement",
    keyword,
    name,
    argument: name,
    statements: musts
  };
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  return out;
}
function parseContainer(name, schema, defs) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const props = asRecord2(schema.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children = [...musts];
  for (const [childName, childSchema] of Object.entries(props)) {
    if (!childSchema || typeof childSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(childName, childSchema, defs);
    if (stmt) {
      children.push(stmt);
    }
  }
  const hasExplicitChoiceChildren = children.some((s) => s.keyword === "choice" /* CHOICE */);
  const out = {
    __class__: "YangStatement",
    keyword: "container" /* CONTAINER */,
    name,
    argument: name,
    statements: children
  };
  const reqList = Array.isArray(schema.required) ? schema.required.filter((x) => typeof x === "string") : [];
  for (const ch of children) {
    if (typeof ch.name === "string" && reqList.includes(ch.name)) {
      ch.mandatory = true;
    }
  }
  if (typeof xy.presence === "string" && xy.presence.length > 0) {
    out.presence = xy.presence;
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  setConfigFromXyang(out, xy);
  const choice = xy.choice;
  if (!hasExplicitChoiceChildren && choice && typeof choice === "object") {
    const ch = asRecord2(choice);
    const branches = extractChoiceBranches(schema);
    const { commonProps, strippedBranches } = splitChoiceCommonProperties(branches);
    for (const [commonName, commonSchema] of Object.entries(commonProps)) {
      const commonStmt = jsonSchemaPropertyToStatement(commonName, commonSchema, defs);
      if (commonStmt) {
        children.push(commonStmt);
      }
    }
    const choiceSchema = {
      type: JSON_TYPE_OBJECT,
      oneOf: strippedBranches,
      [YANG_SCHEMA_KEYS.xYang]: {
        name: typeof ch.name === "string" && ch.name.length > 0 ? ch.name : "choice",
        mandatory: ch.mandatory === true,
        ...Array.isArray(ch["if-features"]) ? { "if-features": ch["if-features"] } : {},
        ...typeof ch.description === "string" && ch.description.length > 0 ? { description: ch.description } : {}
      }
    };
    const choiceStmt = parseChoice(
      choiceSchema[YANG_SCHEMA_KEYS.xYang].name,
      choiceSchema,
      defs
    );
    if (choiceStmt.statements.length > 0) {
      children.push(choiceStmt);
    }
  }
  if (Array.isArray(schema.allOf)) {
    out.allOf = schema.allOf;
  }
  return out;
}
function parseList(name, schema, defs) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = asRecord2(schema.items);
  const resolvedItems = resolveSchema(items, defs);
  const itemProps = asRecord2(resolvedItems.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children = [...musts];
  for (const [childName, childSchema] of Object.entries(itemProps)) {
    if (!childSchema || typeof childSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(childName, childSchema, defs);
    if (stmt) {
      children.push(stmt);
    }
  }
  const out = {
    __class__: "YangStatement",
    keyword: "list" /* LIST */,
    name,
    argument: name,
    statements: children,
    key: typeof xy.key === "string" ? xy.key : void 0,
    min_elements: typeof schema.minItems === "number" ? schema.minItems : typeof xy["min-elements"] === "number" ? xy["min-elements"] : void 0,
    max_elements: typeof schema.maxItems === "number" ? schema.maxItems : typeof xy["max-elements"] === "number" ? xy["max-elements"] : void 0
  };
  const itemReq = Array.isArray(resolvedItems.required) ? resolvedItems.required.filter((x) => typeof x === "string") : [];
  for (const ch of children) {
    if (typeof ch.name === "string" && itemReq.includes(ch.name)) {
      ch.mandatory = true;
    }
  }
  const itemXy = asRecord2(resolvedItems[YANG_SCHEMA_KEYS.xYang]);
  const itemChoice = itemXy.choice;
  if (itemChoice && typeof itemChoice === "object") {
    const ch = asRecord2(itemChoice);
    const branches = extractChoiceBranches(resolvedItems);
    const { commonProps, strippedBranches } = splitChoiceCommonProperties(branches);
    for (const [commonName, commonSchema] of Object.entries(commonProps)) {
      const commonStmt = jsonSchemaPropertyToStatement(commonName, commonSchema, defs);
      if (commonStmt) {
        children.push(commonStmt);
      }
    }
    const choiceSchema = {
      type: JSON_TYPE_OBJECT,
      oneOf: strippedBranches,
      [YANG_SCHEMA_KEYS.xYang]: {
        name: typeof ch.name === "string" && ch.name.length > 0 ? ch.name : "choice",
        mandatory: ch.mandatory === true,
        ...Array.isArray(ch["if-features"]) ? { "if-features": ch["if-features"] } : {},
        ...typeof ch.description === "string" && ch.description.length > 0 ? { description: ch.description } : {}
      }
    };
    const choiceStmt = parseChoice(
      choiceSchema[YANG_SCHEMA_KEYS.xYang].name,
      choiceSchema,
      defs
    );
    if (choiceStmt.statements.length > 0) {
      children.push(choiceStmt);
    }
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  setConfigFromXyang(out, xy);
  return out;
}
function parseLeafList(name, schema, defs) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = resolveSchema(asRecord2(schema.items), defs);
  const itemXy = asRecord2(items[YANG_SCHEMA_KEYS.xYang]);
  const mergedXy = { ...xy, ...itemXy };
  const typeShape = typeShapeFromJsonLeaf(items, mergedXy);
  const out = {
    __class__: "YangStatement",
    keyword: "leaf-list" /* LEAF_LIST */,
    name,
    argument: name,
    type: typeShape,
    statements: mustStatementsFromXyang(xy)
  };
  if (typeof schema.minItems === "number") {
    out.min_elements = schema.minItems;
  } else if (typeof xy["min-elements"] === "number") {
    out.min_elements = xy["min-elements"];
  }
  if (typeof schema.maxItems === "number") {
    out.max_elements = schema.maxItems;
  } else if (typeof xy["max-elements"] === "number") {
    out.max_elements = xy["max-elements"];
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (schema.default !== void 0) {
    if (Array.isArray(schema.default)) {
      out.defaults = schema.default.filter((x) => x !== void 0);
    } else {
      out.defaults = [schema.default];
    }
  }
  setConfigFromXyang(out, xy);
  return out;
}
function parseIoBlock(schema, defs, ioType) {
  const xy = asRecord2(schema[YANG_SCHEMA_KEYS.xYang]);
  const parsed = parseContainer(ioType, schema, defs);
  parsed.keyword = ioType;
  parsed.name = ioType;
  parsed.argument = ioType;
  applyStatementMetaFromXyang(parsed, xy);
  if (typeof schema.description === "string" && schema.description.length > 0) {
    parsed.description = schema.description;
  }
  return parsed;
}
function parseRpc(name, rpcValue, defs) {
  const xy = asRecord2(rpcValue[YANG_SCHEMA_KEYS.xYang]);
  if (xy.type !== "rpc" /* RPC */) {
    return null;
  }
  const statements = [...mustStatementsFromXyang(xy)];
  for (const ioKey of ["input" /* INPUT */, "output" /* OUTPUT */]) {
    const block = rpcValue[ioKey];
    if (block && typeof block === "object") {
      statements.push(parseIoBlock(block, defs, ioKey));
    }
  }
  const out = {
    __class__: "YangStatement",
    keyword: "rpc" /* RPC */,
    name,
    argument: name,
    statements
  };
  applyStatementMetaFromXyang(out, xy);
  return out;
}
function jsonSchemaPropertyToStatement(name, schema, defs) {
  const resolved = resolveSchemaWithOverlay(schema, defs);
  const xy = asRecord2(resolved[YANG_SCHEMA_KEYS.xYang]);
  const xyType = typeof xy.type === "string" ? xy.type : "";
  if (xyType === "container" /* CONTAINER */ && resolved.type === JSON_TYPE_OBJECT) {
    return parseContainer(name, resolved, defs);
  }
  if (xyType === "list" /* LIST */ && resolved.type === JSON_TYPE_ARRAY) {
    return parseList(name, resolved, defs);
  }
  if (xyType === "leaf-list" /* LEAF_LIST */ && resolved.type === JSON_TYPE_ARRAY) {
    return parseLeafList(name, resolved, defs);
  }
  if (xyType === "choice" /* CHOICE */) {
    return parseChoice(name, resolved, defs);
  }
  if (xyType === "leaf" /* LEAF */) {
    return parseLeaf(name, resolved, defs);
  }
  if (xyType === "leafref" /* LEAFREF */ || xyType === "identityref" /* IDENTITYREF */ || xyType === "instance-identifier" /* INSTANCE_IDENTIFIER */) {
    return parseLeaf(name, resolved, defs);
  }
  if (xyType === "anydata" /* ANYDATA */) {
    return parseAnydataOrAnyxml(name, resolved, "anydata" /* ANYDATA */);
  }
  if (xyType === "anyxml" /* ANYXML */) {
    return parseAnydataOrAnyxml(name, resolved, "anyxml" /* ANYXML */);
  }
  if (resolved.type === JSON_TYPE_OBJECT && Object.keys(xy).length > 0) {
    return parseContainer(name, resolved, defs);
  }
  return null;
}
function parseJsonSchema(source) {
  const root = typeof source === "string" ? JSON.parse(source) : { ...source };
  const rootXy = asRecord2(root[YANG_SCHEMA_KEYS.xYang]);
  const moduleName2 = typeof rootXy.module === "string" ? rootXy.module : typeof root.title === "string" ? root.title : "";
  const namespace = typeof rootXy.namespace === "string" ? rootXy.namespace : "";
  const prefix = typeof rootXy.prefix === "string" ? rootXy.prefix : "";
  const defsRaw = root.$defs;
  const defs = defsRaw && typeof defsRaw === "object" && !Array.isArray(defsRaw) ? defsRaw : {};
  const properties = asRecord2(root.properties);
  const statements = [];
  for (const [propName, propSchema] of Object.entries(properties)) {
    if (!propSchema || typeof propSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(propName, propSchema, defs);
    if (stmt) {
      statements.push(stmt);
    }
  }
  const rootRequired = Array.isArray(root.required) ? root.required.filter((x) => typeof x === "string") : [];
  for (const stmt of statements) {
    if (typeof stmt.name === "string" && rootRequired.includes(stmt.name)) {
      stmt.mandatory = true;
    }
  }
  const rpcsRaw = rootXy[XYANG_KEYS.rpcs];
  if (rpcsRaw && typeof rpcsRaw === "object" && !Array.isArray(rpcsRaw)) {
    for (const [rpcName, rpcVal] of Object.entries(rpcsRaw)) {
      if (!rpcVal || typeof rpcVal !== "object") {
        continue;
      }
      const rpcStmt = parseRpc(String(rpcName), rpcVal, defs);
      if (rpcStmt) {
        statements.push(rpcStmt);
      }
    }
  }
  const typedefs = {};
  const identities = {};
  for (const [defName, defSchema] of Object.entries(defs)) {
    if (!defSchema || typeof defSchema !== "object") {
      continue;
    }
    const d = defSchema;
    const dxy = asRecord2(d[YANG_SCHEMA_KEYS.xYang]);
    if (dxy.type === "identity" /* IDENTITY */) {
      const bases = Array.isArray(dxy.bases) ? dxy.bases.filter((x) => typeof x === "string") : [];
      identities[defName] = { bases };
      continue;
    }
    typedefs[defName] = {
      name: defName,
      type: typeShapeFromJsonLeaf(d, dxy),
      statements: []
    };
  }
  const data = {
    __class__: "YangModule",
    name: moduleName2,
    yang_version: "1.1",
    namespace,
    prefix,
    typedefs,
    identities,
    import_prefixes: {},
    extensions: {},
    extension_runtime: {},
    statements
  };
  const modSource = { kind: "string", value: typeof source === "string" ? source : JSON.stringify(source), name: "<json-schema>" };
  return new YangModule(data, modSource);
}

export {
  YangStatement,
  YangModule,
  parseAnydataExtensionConfig,
  YangParser,
  parseYangString,
  parseYangFile,
  ValidatorExtension,
  reachableModuleData,
  evaluateIfFeatureExpression,
  stmtIfFeaturesSatisfied,
  buildEnabledFeaturesMap,
  YangValidator,
  generateJsonSchema,
  parseJsonSchema
};
//# sourceMappingURL=chunk-FNPPHT3N.js.map