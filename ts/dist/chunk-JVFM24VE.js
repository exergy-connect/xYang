#!/usr/bin/env node

// src/core/errors.ts
var YangError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "YangError";
  }
};
var YangSyntaxError = class extends SyntaxError {
  messageText;
  line_num;
  line;
  context_lines;
  filename;
  constructor(message, options = {}) {
    const { line_num, line, context_lines = [], filename } = options;
    const parts = [];
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
        rendered += `${marker}${String(ctxLineNum).padStart(4, " ")} | ${ctxLine}
`;
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
  formatHeadline() {
    const parts = [];
    if (this.filename) {
      parts.push(`${this.filename}:`);
    }
    if (this.line_num !== void 0) {
      parts.push(`${this.line_num}:`);
    }
    parts.push(this.messageText);
    return parts.join(" ");
  }
  toString() {
    return this.formatHeadline();
  }
};
var YangSemanticError = class extends YangError {
  constructor(message) {
    super(message);
    this.name = "YangSemanticError";
  }
};
var YangRefineTargetNotFoundError = class extends YangSemanticError {
  target_path;
  constructor(target_path) {
    super(`Refine target path matches no node in the used grouping: '${target_path}'`);
    this.name = "YangRefineTargetNotFoundError";
    this.target_path = target_path;
  }
};
var YangCircularUsesError = class extends YangSemanticError {
  prefix_chain;
  repeated;
  constructor(prefix_chain, repeated) {
    const cycle = [...prefix_chain, repeated].join(" -> ");
    super(
      `Circular uses chain: groupings are expanded at compile-time and this cycle would not terminate (${cycle}). Restructure groupings to break the cycle.`
    );
    this.name = "YangCircularUsesError";
    this.prefix_chain = [...prefix_chain];
    this.repeated = repeated;
  }
};
var XPathSyntaxError = class extends Error {
  messageText;
  position;
  expression;
  constructor(message, options = {}) {
    const { position, expression, context_before = 10, context_after = 10 } = options;
    if (expression !== void 0 && position !== void 0) {
      const start = Math.max(0, position - context_before);
      const end = Math.min(expression.length, position + context_after);
      const context = expression.slice(start, end);
      const pointerPos = position - start;
      const parts = [message, `
Expression: ${context}`, `           ${" ".repeat(pointerPos)}^`];
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
  toString() {
    return this.messageText;
  }
};

// src/parser/parser-context.ts
var PUNCTUATION = /* @__PURE__ */ new Set([
  "{" /* LBRACE */,
  "}" /* RBRACE */,
  ";" /* SEMICOLON */,
  ":" /* COLON */,
  "=" /* EQUALS */,
  "+" /* PLUS */,
  "/" /* SLASH */
]);
function diagnosticSourceLines(content) {
  if (!content) {
    return [];
  }
  return content.split("\n").map((segment) => segment.replace(/\r$/, ""));
}
function classifyKind(type) {
  if (type === "STRING" /* STRING */) {
    return "string";
  }
  if (type === "INTEGER" /* INTEGER */ || type === "DOTTED_NUMBER" /* DOTTED_NUMBER */) {
    return "number";
  }
  if (PUNCTUATION.has(type)) {
    return "symbol";
  }
  return "identifier";
}
var LEXICAL_TOKEN_TYPES = /* @__PURE__ */ new Set([
  "{" /* LBRACE */,
  "}" /* RBRACE */,
  ";" /* SEMICOLON */,
  ":" /* COLON */,
  "=" /* EQUALS */,
  "+" /* PLUS */,
  "/" /* SLASH */,
  "STRING" /* STRING */,
  "IDENTIFIER" /* IDENTIFIER */,
  "INTEGER" /* INTEGER */,
  "DOTTED_NUMBER" /* DOTTED_NUMBER */
]);
function makeYangToken(type, value, line_num, char_pos) {
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
var TokenStream = class {
  token_list;
  tokens;
  positions;
  filename;
  index;
  source;
  diagnostic_lines;
  constructor(token_list, source, filename) {
    this.token_list = token_list;
    this.tokens = token_list.map((t) => t.value);
    this.positions = token_list.map((t) => [t.line_num, t.char_pos]);
    this.source = source;
    this.filename = filename;
    this.index = 0;
  }
  peek_token() {
    return this.token_list[this.index];
  }
  peek(offset = 0) {
    return this.token_list[this.index + offset]?.value;
  }
  consume(expected) {
    if (this.index >= this.tokens.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tokenVal = this.tokens[this.index];
    if (expected !== void 0 && tokenVal !== expected) {
      throw this._make_error(`Expected '${expected}', got '${tokenVal}'`);
    }
    this.index += 1;
    return tokenVal;
  }
  consume_if(expected) {
    if (this.peek() === expected) {
      this.consume();
      return true;
    }
    return false;
  }
  peek_type() {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    return this.token_list[this.index].type;
  }
  peek_type_at(offset = 0) {
    return this.token_list[this.index + offset]?.type;
  }
  consume_type(expected) {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    if (typeof expected === "string" && !LEXICAL_TOKEN_TYPES.has(expected)) {
      if (tok.type !== "IDENTIFIER" /* IDENTIFIER */ || tok.value !== expected) {
        throw this._make_error(`Expected '${expected}', got '${tok.value}'`);
      }
    } else if (tok.type !== expected) {
      throw this._make_error(`Expected ${expected}, got ${tok.type} ('${tok.value}')`);
    }
    this.index += 1;
    return tok.value;
  }
  consume_if_type(expected) {
    if (this.index >= this.token_list.length) {
      return false;
    }
    const tok = this.token_list[this.index];
    if (typeof expected === "string" && !LEXICAL_TOKEN_TYPES.has(expected)) {
      if (tok.type !== "IDENTIFIER" /* IDENTIFIER */ || tok.value !== expected) {
        return false;
      }
    } else if (tok.type !== expected) {
      return false;
    }
    this.consume_type(expected);
    return true;
  }
  consume_oneof(allowed_types) {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    for (const allowed of allowed_types) {
      if (typeof allowed === "string") {
        if (!LEXICAL_TOKEN_TYPES.has(allowed)) {
          if (tok.type === "IDENTIFIER" /* IDENTIFIER */ && tok.value === allowed) {
            this.index += 1;
            return [tok.value, allowed];
          }
        } else if (tok.type === allowed) {
          this.index += 1;
          return [tok.value, allowed];
        }
      } else if (tok.type === allowed) {
        this.index += 1;
        return [tok.value, allowed];
      }
    }
    throw this._make_error(
      `Expected one of (${allowed_types.join(", ")}), got ${tok.type} ('${tok.value}')`
    );
  }
  has_more() {
    return this.index < this.tokens.length;
  }
  // Compatibility for prior TS parser helpers.
  hasMore() {
    return this.has_more();
  }
  /** Throw {@link YangSyntaxError} at the current token position. */
  syntaxError(message) {
    throw this._make_error(message);
  }
  position() {
    if (this.index < this.positions.length) {
      return this.positions[this.index];
    }
    if (this.positions.length > 0) {
      return this.positions[this.positions.length - 1];
    }
    return [1, 0];
  }
  diagnostic_lines_once() {
    if (!this.diagnostic_lines) {
      this.diagnostic_lines = diagnosticSourceLines(this.source);
    }
    return this.diagnostic_lines;
  }
  _make_error(message, context_lines = 3) {
    const [line_num] = this.position();
    const lines = this.diagnostic_lines_once();
    const context = [];
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
};
var ParserContext = class _ParserContext {
  module;
  current_parent;
  source_dir;
  constructor(init) {
    this.module = init.module;
    this.current_parent = init.current_parent;
    this.source_dir = init.source_dir;
  }
  push_parent(parent) {
    return new _ParserContext({
      module: this.module,
      current_parent: parent,
      source_dir: this.source_dir
    });
  }
};

// src/json/integer-bounds.ts
var YANG_INTEGER_BOUNDS = {
  int8: [-128, 127],
  int16: [-32768, 32767],
  int32: [-2147483648, 2147483647],
  int64: [-9223372036854776e3, 9223372036854776e3],
  uint8: [0, 255],
  uint16: [0, 65535],
  uint32: [0, 4294967295],
  // JSON numbers are IEEE doubles; uint64 max is representable exactly.
  uint64: [0, 18446744073709552e3]
};
var YANG_INTEGER_BUILTIN_NAMES = new Set(Object.keys(YANG_INTEGER_BOUNDS));
function parseRange(rangeStr) {
  const parts = rangeStr.split("..");
  const out = {};
  const rawLo = (parts[0] ?? "").trim();
  const rawHi = (parts[1] ?? "").trim();
  if (rawLo && rawLo.toLowerCase() !== "min") {
    const lo = Number.parseInt(rawLo, 10);
    if (!Number.isNaN(lo)) {
      out.lo = lo;
    }
  }
  if (rawHi && rawHi.toLowerCase() !== "max") {
    const hi = Number.parseInt(rawHi, 10);
    if (!Number.isNaN(hi)) {
      out.hi = hi;
    }
  }
  return out;
}
function jsonIntegerBoundsForBuiltin(yangType, rangeStr) {
  const bounds = YANG_INTEGER_BOUNDS[yangType];
  if (!bounds) {
    return {};
  }
  if (!rangeStr) {
    return { minimum: bounds[0], maximum: bounds[1] };
  }
  const { lo, hi } = parseRange(rangeStr);
  const parts = rangeStr.split("..");
  const loS = (parts[0] ?? "").trim();
  const hiS = (parts[1] ?? "").trim();
  const out = {};
  if (loS.toLowerCase() === "min") {
    out.minimum = bounds[0];
  } else if (lo !== void 0) {
    out.minimum = lo;
  }
  if (rangeStr.includes("..") && hiS.toLowerCase() === "max") {
    out.maximum = bounds[1];
  } else if (hi !== void 0) {
    out.maximum = hi;
  }
  return out;
}
function coerceInt(value) {
  if (value === null || value === void 0) {
    return void 0;
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  return void 0;
}
function narrowestIntegerBuiltin(lo, hi) {
  const order = lo !== void 0 && lo < 0 ? ["int8", "int16", "int32", "int64"] : ["uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64"];
  const effectiveLo = lo ?? YANG_INTEGER_BOUNDS[order[0]][0];
  const effectiveHi = hi ?? YANG_INTEGER_BOUNDS[order[order.length - 1]][1];
  for (const name of order) {
    const [blo, bhi] = YANG_INTEGER_BOUNDS[name];
    if (effectiveLo >= blo && effectiveHi <= bhi) {
      return name;
    }
  }
  return "int64" /* INT64 */;
}
function yangIntegerFromJsonBounds(minVal, maxVal) {
  const lo = coerceInt(minVal);
  const hi = coerceInt(maxVal);
  if (lo === void 0 && hi === void 0) {
    return { name: "integer" };
  }
  if (lo === 0 && hi !== void 0) {
    for (const name2 of ["int8", "int16", "int32", "int64"]) {
      if (hi === YANG_INTEGER_BOUNDS[name2][1]) {
        return { name: name2, range: "0..max" };
      }
    }
  }
  if (lo !== void 0 && hi !== void 0) {
    for (const [name2, [blo, bhi]] of Object.entries(YANG_INTEGER_BOUNDS)) {
      if (lo === blo && hi === bhi) {
        return { name: name2 };
      }
    }
  }
  let range;
  if (lo !== void 0 || hi !== void 0) {
    const minPart = lo !== void 0 ? String(lo) : "min";
    const maxPart = hi !== void 0 ? String(hi) : "max";
    range = `${minPart}..${maxPart}`;
  }
  const name = narrowestIntegerBuiltin(lo, hi);
  const canonical = YANG_INTEGER_BOUNDS[name];
  if (range && canonical && lo === canonical[0] && hi === canonical[1]) {
    return { name };
  }
  return range ? { name, range } : { name };
}

// src/types.ts
var TypeConstraint = class {
  patterns;
  length;
  range;
  fraction_digits;
  enums;
  bits;
  types;
  constructor(input = {}) {
    Object.assign(this, input);
  }
};
function patternEntryViolationMessage(p, defaultMsg) {
  const msg = typeof p.error_message === "string" && p.error_message.trim().length > 0 ? p.error_message : defaultMsg;
  const tag = typeof p.error_app_tag === "string" ? p.error_app_tag.trim() : "";
  return tag.length > 0 ? `${msg} (error-app-tag: ${tag})` : msg;
}
function parseRangeText(raw) {
  const parseBound = (text, kind) => {
    const t = text.trim().toLowerCase();
    if (t === "min") {
      return Number.NEGATIVE_INFINITY;
    }
    if (t === "max") {
      return Number.POSITIVE_INFINITY;
    }
    const n = Number(t);
    if (Number.isNaN(n)) {
      return kind === "min" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
    }
    return n;
  };
  return raw.split("|").map((part) => part.trim()).filter(Boolean).map((part) => {
    const [minRaw, maxRaw] = part.split("..").map((x) => x.trim());
    if (!maxRaw) {
      const n = parseBound(minRaw, "min");
      return { min: n, max: n };
    }
    return { min: parseBound(minRaw, "min"), max: parseBound(maxRaw, "max") };
  });
}
function matchesRange(value, raw) {
  for (const band of parseRangeText(raw)) {
    if (value >= band.min && value <= band.max) {
      return true;
    }
  }
  return false;
}
function integerLike(value) {
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+$/.test(value)) {
    return Number.parseInt(value, 10);
  }
  return null;
}
function decimalLike(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return null;
}
function validateIntegerBuiltin(typeName, value, range) {
  const bounds = YANG_INTEGER_BOUNDS[typeName];
  if (!bounds) {
    return [false, `Unsupported integer type '${typeName}'`];
  }
  const n = integerLike(value);
  if (n === null) {
    return [false, `Expected ${typeName}`];
  }
  if (range) {
    if (!matchesRange(n, range)) {
      return [false, `Integer ${n} does not match ${range}`];
    }
    return [true, null];
  }
  const [lo, hi] = bounds;
  if (n < lo) {
    return [false, `Value ${n} is less than minimum ${lo}`];
  }
  if (n > hi) {
    return [false, `Value ${n} exceeds maximum ${hi}`];
  }
  return [true, null];
}
function validateBinary(value, length) {
  if (typeof value !== "string") {
    return [false, "Expected base64 string"];
  }
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) {
    return [false, "Expected valid base64 string"];
  }
  try {
    const bytes = Buffer.from(value, "base64");
    if (length && !matchesRange(bytes.length, length)) {
      return [false, `Binary length ${bytes.length} does not match ${length}`];
    }
  } catch {
    return [false, "Expected valid base64 string"];
  }
  return [true, null];
}
function validateBits(value, bits) {
  if (typeof value !== "string") {
    return [false, "Bits values must be string tokens"];
  }
  const allowed = new Set(bits.map((bit) => bit.name));
  if (value.trim() === "") {
    return [true, null];
  }
  const seen = /* @__PURE__ */ new Set();
  for (const token of value.trim().split(/\s+/)) {
    if (!allowed.has(token)) {
      return [false, `Unknown bit token '${token}'`];
    }
    if (seen.has(token)) {
      return [false, `Duplicate bit token '${token}'`];
    }
    seen.add(token);
  }
  return [true, null];
}
var TypeSystem = class {
  validate(value, typeName, constraint) {
    const c = constraint ?? new TypeConstraint();
    const normalizedType = typeName.trim();
    if (normalizedType === "union" /* UNION */) {
      for (const member of c.types ?? []) {
        const memberName = typeof member.name === "string" ? member.name : "string" /* STRING_KW */;
        const [ok] = this.validate(value, memberName, new TypeConstraint(member));
        if (ok) {
          return [true, null];
        }
      }
      return [false, "Value does not match any union member type"];
    }
    if (normalizedType === "enumeration" /* ENUMERATION */) {
      if (typeof value !== "string") {
        return [false, "Expected enumeration value (string)"];
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [false, `Value '${value}' is not in enum`];
      }
      return [true, null];
    }
    if (normalizedType === "string" /* STRING_KW */) {
      if (typeof value !== "string") {
        return [false, "Expected string"];
      }
      if (c.length && !matchesRange(value.length, c.length)) {
        return [false, `String length ${value.length} does not match ${c.length}`];
      }
      const patterns = Array.isArray(c.patterns) ? c.patterns : [];
      if (patterns.length > 0) {
        for (const p of patterns) {
          if (typeof p?.pattern !== "string" || p.pattern.length === 0) {
            continue;
          }
          const matched = new RegExp(`^(?:${p.pattern})$`).test(value);
          const invert = p.invert_match === true;
          if (!invert && !matched || invert && matched) {
            const defaultMsg = invert ? `String matches forbidden pattern ${p.pattern} (invert-match)` : `String does not match pattern ${p.pattern}`;
            return [false, patternEntryViolationMessage(p, defaultMsg)];
          }
        }
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [false, `Value '${value}' is not in enum`];
      }
      return [true, null];
    }
    if (normalizedType === "boolean" /* BOOLEAN */) {
      if (typeof value === "boolean") {
        return [true, null];
      }
      if (value === "true" /* TRUE */ || value === "false" /* FALSE */) {
        return [true, null];
      }
      return [false, "Expected boolean"];
    }
    if (normalizedType === "empty" /* EMPTY */) {
      if (value === null) {
        return [true, null];
      }
      return [false, "Expected empty (null)"];
    }
    if (normalizedType in YANG_INTEGER_BOUNDS) {
      return validateIntegerBuiltin(normalizedType, value, c.range);
    }
    if (normalizedType === "binary" /* BINARY */) {
      return validateBinary(value, c.length);
    }
    if (normalizedType === "bits" /* BITS */) {
      return validateBits(value, c.bits ?? []);
    }
    if (normalizedType === "decimal64" /* DECIMAL64 */ || normalizedType === "number") {
      const n = decimalLike(value);
      if (n === null) {
        return [false, "Expected number"];
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Number ${n} does not match ${c.range}`];
      }
      if (typeof c.fraction_digits === "number") {
        const decimals = `${n}`.split(".")[1]?.length ?? 0;
        if (decimals > c.fraction_digits) {
          return [false, `Too many fraction digits (${decimals} > ${c.fraction_digits})`];
        }
      }
      return [true, null];
    }
    if (normalizedType === "int64" /* INT64 */ || normalizedType === "integer") {
      const n = integerLike(value);
      if (n === null) {
        return [false, "Expected integer"];
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [false, `Integer ${n} does not match ${c.range}`];
      }
      return [true, null];
    }
    if (typeof value === "string") {
      return [true, null];
    }
    return [false, `Unsupported type '${normalizedType}'`];
  }
};

export {
  YangSyntaxError,
  YangSemanticError,
  YangRefineTargetNotFoundError,
  YangCircularUsesError,
  XPathSyntaxError,
  makeYangToken,
  TokenStream,
  ParserContext,
  YANG_INTEGER_BOUNDS,
  jsonIntegerBoundsForBuiltin,
  yangIntegerFromJsonBounds,
  TypeConstraint,
  TypeSystem
};
//# sourceMappingURL=chunk-JVFM24VE.js.map