import { YangModule, YangStatement } from "../core/model";
import { hasTokenType, YangTokenType } from "../parser/parser-context";
import { modulePrefixResolver } from "../core/ast";
import { bindXPathPrefixes, parseXPath, parseXPathPath, xpathPrefixes } from "../xpath/parser";
import { XPathAstNode } from "../xpath/ast";
import { XPathContext, XPathEvaluator, XPathNode, XPathSchema } from "../xpath/evaluator";
import { remapPointer, resolveQualifiedTopLevel, resolveStructureInstance } from "../encoding";
import {
  AnydataValidationConfig,
  AnydataValidationConfigInput,
  AnydataValidationMode,
  parseAnydataExtensionConfig
} from "../ext/anydata_validation";
import { ValidatorExtension } from "./validator-extension";
import { lexical } from "./operation";
import type { OperationTarget } from "./operation";
import { resolveTypedef, TypeChecker } from "./type-checker";
import { summarizeValue, traceTypeValidation } from "./type-validation-debug";
import { buildEnabledFeaturesMap, ModuleData, stmtIfFeaturesSatisfied } from "./if-feature-eval";

export type ValidationSeverity = "error" | "warning";

/**
 * Structured validation issue. `path` is a JSON Pointer into the instance, or into the server data
 * context of an rpc or action when `document` is `"context"`.
 */
export type ValidationIssue = {
  document?: "context";
  code: string;
  path: string;
  message: string;
  expression?: string;
  severity: ValidationSeverity;
};

export type DetailedValidationResult = {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
};

type InternalIssue = ValidationIssue & { pathLabel: string };

/** Inputs of one rpc or action validation (see `YangValidator`). */
export type OperationInput = {
  target: OperationTarget;
  operation: YangStatement;
  parentCopies: YangStatement[];
  params: Record<string, unknown>;
  rootData: Record<string, unknown>;
  wrapper: string | null;
};

function missingParent(target: OperationTarget, detail: string): InternalIssue {
  return {
    document: "context",
    code: "action-parent",
    path: "",
    message: `${target.label} is invoked on an instance that is not in the context: ${detail}`,
    severity: "error",
    pathLabel: "context"
  };
}

/**
 * Message-to-code table previously stored in tests/cases/error-codes.json.
 * Type-checker issues already carry a code. This table is for other messages. Order matters.
 */
const MESSAGE_CODES: Array<[string, RegExp]> = [
  ["unknown-field", /Unknown field '/],
  ["if-feature", /'if-feature' condition is false/],
  ["when", /'when' (condition )?evaluates to false|not allowed by when condition/],
  ["mandatory-choice", /[Mm]andatory choice .*has no active case/],
  ["mandatory", /^Mandatory (leaf|anydata|anyxml) '|^mandatory (leaf|anydata|anyxml) is missing/],
  ["min-elements", /requires at least \d+$/],
  ["max-elements", /allows at most \d+$/],
  ["duplicate-key", /^Duplicate key in list '/],
  ["unique", /^Unique constraint violated/],
  ["xpath-unknown-function", /xpath-unknown-function: unknown XPath function/],
  ["xpath-error", /^Error evaluating (must|when) expression/],
  ["must", /^must constraint not satisfied on '/],
  ["leafref", /^[Ll]eafref/],
  ["instance-identifier", /^instance-identifier/],
  ["identityref", /^identityref value/],
  ["union", /does not match any union member type/],
  ["length", /^String length \d+|^binary decoded length|^Binary length/],
  ["pattern", /does not match pattern|matches forbidden pattern/],
  ["fraction-digits", /fraction digits/],
  ["range", /is less than minimum|exceeds maximum|^(Integer|Number) \S+ does not match /],
  ["enum", /is not in enum|is not one of|^Expected enumeration value/],
  ["bits", /[Bb]it token|bit '|[Bb]its value/],
  ["type", /^Expected |is not a valid |should have no value|must be an? (object|array|string)|base64/]
];

function codeForMessage(message: string): string | undefined {
  return MESSAGE_CODES.find(([, rx]) => rx.test(message))?.[0];
}

/** TS display path (`top.items[0].v`) -> JSON Pointer (`/top/items/0/v`). Root is `""`. */
function pointerFromLabel(path: string): string {
  return path
    .split(".")
    .filter(Boolean)
    .map((segment) => "/" + segment.replace(/\[(\d+)\]/g, "/$1"))
    .join("");
}

function joinPointer(base: string, token: string): string {
  return `${base}/${token.replace(/~/g, "~0").replace(/\//g, "~1")}`;
}

function issue(pathLabel: string, code: string, message: string, expression?: string, path?: string): InternalIssue {
  const item: InternalIssue = {
    code,
    path: path ?? pointerFromLabel(pathLabel),
    message,
    severity: "error",
    pathLabel
  };
  if (expression) {
    item.expression = expression;
  }
  return item;
}

function formatIssue(item: InternalIssue): string {
  return item.pathLabel ? `${item.pathLabel}: ${item.message}` : item.message;
}

function toPublicIssue(item: InternalIssue): ValidationIssue {
  const pub: ValidationIssue = {
    ...(item.document ? { document: item.document } : {}),
    code: item.code,
    path: item.path,
    message: item.message,
    severity: item.severity
  };
  if (item.expression) {
    pub.expression = item.expression;
  }
  return pub;
}

export type EnabledFeaturesByModule = Record<string, ReadonlySet<string>>;

export type LeafTypeMode = "full" | "none";

/** Per-document validation context (host module or an anydata payload shape module). */
export type ValidationContext = {
  module: YangModule;
  typeChecker: TypeChecker;
  constraintChecks: boolean;
  leafTypeMode: LeafTypeMode;
  typeValidationDebug: boolean;
  anydataValidation: AnydataValidationConfig | undefined;
  ifFeatureCtx: ModuleData;
  enabledByModule: Readonly<Record<string, ReadonlySet<string>>>;
};

export class DocumentValidator {
  private readonly xpath = new XPathEvaluator();
  private readonly xpathCache = new Map<string, XPathAstNode>();
  private readonly rootCtx: ValidationContext;
  private readonly enabledFeaturesOverride: EnabledFeaturesByModule | null;
  private readonly contextStack: ValidationContext[] = [];
  private typeValidationDebug: boolean;

  constructor(
    module: YangModule,
    options: {
      constraintChecks?: boolean;
      leafTypeMode?: LeafTypeMode;
      enabledFeaturesByModule?: EnabledFeaturesByModule | null;
      typeValidationDebug?: boolean;
    } = {}
  ) {
    this.enabledFeaturesOverride = options.enabledFeaturesByModule ?? null;
    this.typeValidationDebug = options.typeValidationDebug === true;
    const constraintChecks = options.constraintChecks ?? true;
    const leafTypeMode = options.leafTypeMode ?? (constraintChecks ? "full" : "none");
    const ifFeatureCtx = module;
    this.rootCtx = {
      module,
      typeChecker: new TypeChecker(module, { typeValidationDebug: this.typeValidationDebug }),
      constraintChecks,
      leafTypeMode,
      typeValidationDebug: this.typeValidationDebug,
      anydataValidation: undefined,
      ifFeatureCtx,
      enabledByModule: buildEnabledFeaturesMap(ifFeatureCtx, this.enabledFeaturesOverride)
    };
  }

  /** When true, this validator emits `console.debug` lines for leaf type checks. */
  setTypeValidationDebug(on: boolean): void {
    this.typeValidationDebug = on;
    this.rootCtx.typeValidationDebug = on;
    this.rootCtx.typeChecker = new TypeChecker(this.rootCtx.module, {
      typeValidationDebug: this.typeValidationDebug
    });
  }

  private get ctx(): ValidationContext {
    const c = this.contextStack[this.contextStack.length - 1];
    if (!c) {
      throw new Error("DocumentValidator: internal error — no active validation context");
    }
    return c;
  }

  enableExtension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void {
    if (extension !== ValidatorExtension.ANYDATA_VALIDATION) {
      throw new Error(`unknown validator extension: ${String(extension)}`);
    }
    this.rootCtx.anydataValidation = parseAnydataExtensionConfig(config);
  }

  validate(data: unknown): [boolean, string[], string[]] {
    const collected = this.collect(this.rootCtx, data);
    return [collected.errors.length === 0, collected.errors.map(formatIssue), collected.warnings.map(formatIssue)];
  }

  validateDetailed(data: unknown): DetailedValidationResult {
    const collected = this.collect(this.rootCtx, data);
    return {
      valid: collected.errors.length === 0,
      errors: collected.errors.map(toPublicIssue),
      warnings: collected.warnings.map(toPublicIssue)
    };
  }

  /**
   * Validate instance data against one module’s top-level data nodes. Used for the root document
   * and, recursively, for each anydata payload shape without constructing a second DocumentValidator.
   */
  private validateWithContext(ctx: ValidationContext, data: unknown): [boolean, string[], string[]] {
    const collected = this.collect(ctx, data);
    return [collected.errors.length === 0, collected.errors.map(formatIssue), collected.warnings.map(formatIssue)];
  }

  /**
   * Validate the parameters of one rpc `input` or `output` (RFC 7950 §7.14). This validator's
   * module is the accessible module of RFC 7950 §6.4.1 (see `accessibleModule`). `params` is the
   * parameter object without the RFC 8040 wrapper, `rootData` the accessible tree's root object
   * (server data plus the operation node) and `operation` the operation node.
   */
  validateOperationDetailed(input: OperationInput): DetailedValidationResult {
    const errors = this.collectOperation(input);
    return { valid: errors.length === 0, errors: errors.map(toPublicIssue), warnings: [] };
  }

  /** Same as `validateOperationDetailed`, as `[isValid, errors, warnings]` display strings. */
  validateOperationText(input: OperationInput): [boolean, string[], string[]] {
    const errors = this.collectOperation(input);
    return [errors.length === 0, errors.map(formatIssue), []];
  }

  /**
   * Validate the parameters of one rpc or action `input` or `output` (RFC 7950 §7.14, §7.15). This
   * validator's module is the accessible module of RFC 7950 §6.4.1 and `parentCopies` are its copies
   * of `target.parents` (see `accessibleModule`). `rootData` is the canonical server data, already
   * validated, which this call may extend (it is the caller's private copy).
   */
  private collectOperation(input: OperationInput): InternalIssue[] {
    const { target, operation, parentCopies, params, rootData, wrapper } = input;
    const ctx = this.rootCtx;
    const active = (stmt: YangStatement): boolean =>
      stmtIfFeaturesSatisfied(Array.isArray(stmt.if_features) ? (stmt.if_features as string[]) : [], ctx.ifFeatureCtx, ctx.enabledByModule);
    for (const step of target.parents) {
      for (const stmt of [...step.wrappers, step.stmt]) {
        if (!active(stmt)) {
          throw new Error(`${target.label} is not available: '${stmt.name}' has a false 'if-feature' condition`);
        }
      }
    }
    if (!active(target.operation)) {
      throw new Error(`${target.label} is not available: its 'if-feature' condition is false`);
    }
    this.contextStack.push(ctx);
    try {
      const errors: InternalIssue[] = [];
      const rootNode: XPathNode = { data: rootData, schema: ctx.module as unknown as XPathSchema, parent: null };
      let holder: Record<string, unknown> = rootData;
      let holderNode = rootNode;
      for (let index = 0; index < target.parents.length; index += 1) {
        const step = target.parents[index]!;
        const copied = parentCopies[index]!;
        const value = holder[this.instanceKeys(step.stmt)[0]!];
        if (step.stmt.keyword === "list") {
          const keyNames = (step.stmt.key ?? "").split(/\s+/).filter(Boolean);
          const keyMembers = keyNames.map((name) => {
            const leaf = step.stmt.statements.find((child) => child.name === name);
            return leaf ? this.instanceKeys(leaf)[0]! : name;
          });
          const row = (Array.isArray(value) ? value : []).find(
            (entry): entry is Record<string, unknown> =>
              Boolean(entry) &&
              typeof entry === "object" &&
              keyMembers.every((member, k) => member in (entry as Record<string, unknown>) && lexical((entry as Record<string, unknown>)[member]) === step.keys![k])
          );
          if (!row) {
            return [missingParent(target, `no '${step.stmt.name}' entry with key ${step.keys!.join(", ")}`)];
          }
          holder = row;
        } else {
          let container = value as Record<string, unknown> | undefined;
          if (container === undefined) {
            if (step.stmt.presence) {
              return [missingParent(target, `presence container '${step.stmt.name}' is absent`)];
            }
            // RFC 7950 §7.5.1: a non-presence container exists implicitly.
            container = {};
            holder[this.instanceKeys(step.stmt)[0]!] = container;
          }
          holder = container;
        }
        holderNode = { data: holder, schema: copied as unknown as XPathSchema, parent: holderNode };
      }
      holder[this.instanceKeys(operation)[0]!] = params;
      const opNode: XPathNode = { data: params, schema: operation as unknown as XPathSchema, parent: holderNode };
      if (ctx.constraintChecks) {
        this.checkMust(operation, opNode, rootNode, "", errors);
      }
      for (const child of operation.statements) {
        if (this.effectiveKeyword(child) === YangTokenType.CHOICE) {
          this.validateChoice(child, params, "", errors, opNode, rootNode);
          continue;
        }
        if (!child.name) {
          continue;
        }
        this.validateStatement(child, this.instanceValue(params, child), this.childPath("", child), errors, opNode, rootNode);
      }
      if (ctx.constraintChecks) {
        this.rejectUnknownContainerKeys(operation, params, "", errors);
      }
      for (const item of errors) {
        if (this.pointerMap) {
          item.path = remapPointer(item.path, this.pointerMap);
        }
        if (wrapper !== null) {
          item.path = joinPointer("", wrapper) + item.path;
          item.pathLabel = item.pathLabel ? `${wrapper}.${item.pathLabel}` : wrapper;
        }
      }
      return errors;
    } finally {
      this.contextStack.pop();
    }
  }

  private pointerMap: Map<string, string> | null = null;

  /** Map canonical walker pointers back to the input JSON as written. */
  setPointerMap(pointerMap: Map<string, string> | null): void {
    this.pointerMap = pointerMap;
  }

  private collect(
    ctx: ValidationContext,
    data: unknown
  ): { errors: InternalIssue[]; warnings: InternalIssue[] } {
    this.contextStack.push(ctx);
    try {
      const errors: InternalIssue[] = [];
      const warnings: InternalIssue[] = [];

      if (!data || typeof data !== "object" || Array.isArray(data)) {
        errors.push(issue("", "type", "Document must be an object"));
        return { errors, warnings };
      }

      const root = data as Record<string, unknown>;
      const rootNode: XPathNode = { data: root, schema: ctx.module as unknown as XPathSchema, parent: null };
      const nested = resolveStructureInstance(root, ctx.module);
      if (nested && nested.schema.data_node_kind !== "container") {
        const saved = nested.schema.data_node_kind;
        nested.schema.data_node_kind = "container";
        try {
          this.validateStatement(
            nested.schema,
            nested.inner,
            this.childPath("", nested.schema),
            errors,
            rootNode,
            rootNode
          );
        } finally {
          nested.schema.data_node_kind = saved;
        }
        if (this.pointerMap) {
          for (const item of [...errors, ...warnings]) {
            item.path = remapPointer(item.path, this.pointerMap);
          }
        }
        return { errors, warnings };
      }
      for (const stmt of ctx.module.statements) {
        if (!stmt.name) {
          continue;
        }
        const keyword = this.effectiveKeyword(stmt);
        if (
          !hasTokenType(keyword, [
            YangTokenType.CONTAINER,
            YangTokenType.LIST,
            YangTokenType.LEAF,
            YangTokenType.LEAF_LIST,
            YangTokenType.ANYDATA,
            YangTokenType.ANYXML,
            YangTokenType.CHOICE
          ])
        ) {
          continue;
        }
        this.validateStatement(stmt, this.instanceValue(root, stmt), this.childPath("", stmt), errors, rootNode, rootNode);
      }

      if (ctx.constraintChecks) {
        this.rejectUnknownListItemKeys(ctx.module, root, "", errors);
      }
      if (this.pointerMap) {
        for (const item of [...errors, ...warnings]) {
          item.path = remapPointer(item.path, this.pointerMap);
        }
      }
      return { errors, warnings };
    } finally {
      this.contextStack.pop();
    }
  }

  private validateStatement(
    stmt: YangStatement,
    value: unknown,
    path: string,
    errors: InternalIssue[],
    parentNode: XPathNode,
    rootNode: XPathNode
  ): void {
    const keyword = this.effectiveKeyword(stmt);
    const currentNode: XPathNode = { data: value, schema: stmt as unknown as XPathSchema, parent: parentNode };

    if (keyword === YangTokenType.CHOICE) {
      this.validateChoice(stmt, parentNode.data, path, errors, parentNode, rootNode);
      return;
    }

    if (keyword === YangTokenType.CASE) {
      if (!parentNode.data || typeof parentNode.data !== "object" || Array.isArray(parentNode.data)) {
        return;
      }
      const obj = parentNode.data as Record<string, unknown>;
      for (const child of stmt.statements) {
        if (!child.name) {
          continue;
        }
        this.validateStatement(child, this.instanceValue(obj, child), this.childPath(path, child), errors, parentNode, rootNode);
      }
      return;
    }

    const ifFeatures = stmt.if_features;
    const ifFeatureList = Array.isArray(ifFeatures) ? (ifFeatures as string[]) : [];
    if (!stmtIfFeaturesSatisfied(ifFeatureList, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
      if (value !== undefined) {
        errors.push(
          issue(
            path,
            "if-feature",
            `Node '${stmt.name ?? "node"}' is present but its 'if-feature' condition is false — this node must not exist`
          )
        );
      }
      return;
    }

    if (this.ctx.constraintChecks && !this.checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode)) {
      return;
    }

    if (keyword === YangTokenType.CONTAINER) {
      if (value === undefined && stmt.presence) {
        return;
      }
      if (value !== undefined && (!value || typeof value !== "object" || Array.isArray(value))) {
        errors.push(issue(path, "type", "container must be an object"));
        return;
      }
      // RFC 7950 §7.5.1: an absent non-presence container exists implicitly, so mandatory
      // and min-elements below it still apply. Its own `must` is not evaluated.
      const absent = value === undefined;
      const obj = (value ?? {}) as Record<string, unknown>;
      if (absent) {
        currentNode.data = obj;
      } else if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      for (const child of stmt.statements) {
        const childKw = this.effectiveKeyword(child);
        if (childKw === YangTokenType.CHOICE) {
          this.validateChoice(child, obj, path, errors, currentNode, rootNode);
          continue;
        }
        if (!child.name) {
          continue;
        }
        this.validateStatement(child, this.instanceValue(obj, child), this.childPath(path, child), errors, currentNode, rootNode);
      }
      if (this.ctx.constraintChecks) {
        this.rejectUnknownContainerKeys(stmt, obj, path, errors);
      }
      return;
    }

    if (keyword === YangTokenType.LIST) {
      if (value === undefined) {
        this.checkElementCount(stmt, 0, path, errors);
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(issue(path, "type", "list must be an array"));
        return;
      }
      this.checkElementCount(stmt, value.length, path, errors);
      const keyRaw = typeof stmt.key === "string" ? stmt.key.trim() : "";
      const keyNames = keyRaw.length > 0 ? keyRaw.split(/\s+/).map((k) => k.trim()).filter(Boolean) : [];
      if (this.ctx.constraintChecks && keyNames.length > 0) {
        this.checkListKeyUniqueness(value, keyNames, stmt.name ?? "list", path, errors);
      }
      if (this.ctx.constraintChecks) {
        this.checkListUnique(stmt, value, path, errors);
      }
      for (let i = 0; i < value.length; i += 1) {
        const item = value[i];
        if (!item || typeof item !== "object" || Array.isArray(item)) {
          errors.push(issue(`${path}[${i}]`, "type", "list item must be an object"));
          continue;
        }
        const itemNode: XPathNode = { data: item, schema: stmt as unknown as XPathSchema, parent: parentNode };
        if (this.ctx.constraintChecks) {
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
        const row = item as Record<string, unknown>;
        for (const child of stmt.statements) {
          const childKw = this.effectiveKeyword(child);
          if (childKw === YangTokenType.CHOICE) {
            this.validateChoice(child, row, `${path}[${i}]`, errors, itemNode, rootNode);
            continue;
          }
          if (!child.name) {
            continue;
          }
          this.validateStatement(child, this.instanceValue(row, child), this.childPath(`${path}[${i}]`, child), errors, itemNode, rootNode);
        }
        if (this.ctx.constraintChecks) {
          this.rejectUnknownListItemKeys(stmt, row, `${path}[${i}]`, errors);
        }
      }
      return;
    }

    if (keyword === YangTokenType.LEAF) {
      const mandatory = Boolean(stmt.mandatory);
      if (value === undefined) {
        if (mandatory) {
          errors.push(issue(path, "mandatory", "mandatory leaf is missing"));
        }
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = (stmt.type as Record<string, unknown> | undefined) ?? {};
        const typeName = (typeShape.name as string | undefined) ?? "string";
        const effective = this.effectiveType(typeShape);
        if (effective.name === YangTokenType.LEAFREF) {
          this.checkLeafref(value, effective, path, errors, currentNode, rootNode);
        } else if (effective.name === YangTokenType.INSTANCE_IDENTIFIER) {
          this.checkInstanceIdentifier(value, effective, path, errors, currentNode, rootNode);
        } else {
          const typeIssues = this.ctx.typeChecker.validate(value, typeName, typeShape);
          if (this.ctx.typeValidationDebug) {
            traceTypeValidation(true, "DocumentValidator.leaf:full", {
              path,
              typeName,
              leafTypeMode: this.ctx.leafTypeMode,
              constraintChecks: this.ctx.constraintChecks,
              ok: typeIssues.length === 0,
              reason: typeIssues.length === 0 ? null : typeIssues.map(([, message]) => message).join("; "),
              value: summarizeValue(value)
            });
          }
          for (const [code, message] of typeIssues) {
            errors.push(issue(path, code, message));
          }
        }
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      return;
    }

    if (keyword === YangTokenType.LEAF_LIST) {
      if (value === undefined) {
        this.checkElementCount(stmt, 0, path, errors);
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(issue(path, "type", "leaf-list must be an array"));
        return;
      }
      this.checkElementCount(stmt, value.length, path, errors);
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = (stmt.type as Record<string, unknown> | undefined) ?? {};
        const typeName = (typeShape.name as string | undefined) ?? "string";
        const effective = this.effectiveType(typeShape);
        for (let i = 0; i < value.length; i += 1) {
          const itemNode: XPathNode = { data: value[i], schema: stmt as unknown as XPathSchema, parent: parentNode };
          if (effective.name === YangTokenType.LEAFREF) {
            this.checkLeafref(value[i], effective, `${path}[${i}]`, errors, itemNode, rootNode);
          } else if (effective.name === YangTokenType.INSTANCE_IDENTIFIER) {
            this.checkInstanceIdentifier(value[i], effective, `${path}[${i}]`, errors, itemNode, rootNode);
          } else {
            const typeIssues = this.ctx.typeChecker.validate(value[i], typeName, typeShape);
            if (this.ctx.typeValidationDebug) {
              traceTypeValidation(true, "DocumentValidator.leaf-list:full", {
                path: `${path}[${i}]`,
                typeName,
                leafTypeMode: this.ctx.leafTypeMode,
                constraintChecks: this.ctx.constraintChecks,
                ok: typeIssues.length === 0,
                reason: typeIssues.length === 0 ? null : typeIssues.map(([, message]) => message).join("; "),
                value: summarizeValue(value[i])
              });
            }
            for (const [code, message] of typeIssues) {
              errors.push(issue(`${path}[${i}]`, code, message));
            }
          }
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
      }
      return;
    }

    if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
      const mandatory = Boolean(stmt.mandatory);
      if (value === undefined) {
        if (mandatory) {
          errors.push(issue(path, "mandatory", `mandatory ${keyword} is missing`));
        }
        return;
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      if (keyword === YangTokenType.ANYDATA) {
        this.runAnydataSubtreeValidation(stmt, value, path, errors);
      }
    }
  }

  /** min-elements / max-elements for a list or leaf-list. An absent one has count 0 (RFC 7950 §7.7.5). */
  private checkElementCount(stmt: YangStatement, count: number, path: string, errors: InternalIssue[]): void {
    const name = stmt.name ?? "node";
    const min = stmt.min_elements;
    const max = stmt.max_elements;
    if (typeof min === "number" && count < min) {
      errors.push(issue(path, "min-elements", `'${name}' has ${count} element(s) but requires at least ${min}`));
    }
    if (typeof max === "number" && count > max) {
      errors.push(issue(path, "max-elements", `'${name}' has ${count} element(s) but allows at most ${max}`));
    }
  }

  private rejectUnknownContainerKeys(stmt: YangStatement, obj: Record<string, unknown>, path: string, errors: InternalIssue[]): void {
    this.rejectUnknownListItemKeys(stmt, obj, path, errors);
  }

  private rejectUnknownListItemKeys(stmt: YangStatement | YangModule, row: Record<string, unknown>, path: string, errors: InternalIssue[]): void {
    const allowed = this.collectDirectChildKeys(stmt);
    for (const key of Object.keys(row)) {
      if (!allowed.has(key)) {
        errors.push(issue(path ? `${path}.${key}` : key, "unknown-field", `Unknown field '${key}'`, undefined, joinPointer(pointerFromLabel(path), key)));
      }
    }
  }

  private collectDirectChildKeys(parent: YangStatement | YangModule): Set<string> {
    const keys = new Set<string>();
    const walk = (stmt: YangStatement): void => {
      const kw = this.effectiveKeyword(stmt);
      if (kw === YangTokenType.CHOICE || kw === YangTokenType.CASE) {
        for (const child of stmt.statements ?? []) {
          walk(child);
        }
        return;
      }
      if (stmt.name && hasTokenType(kw, [
        YangTokenType.CONTAINER, YangTokenType.LIST, YangTokenType.LEAF,
        YangTokenType.LEAF_LIST, YangTokenType.ANYDATA, YangTokenType.ANYXML
      ])) {
        for (const key of this.instanceKeys(stmt)) {
          keys.add(key);
        }
      }
    };
    for (const child of parent.statements ?? []) {
      walk(child);
    }
    return keys;
  }

  private validateChoice(
    choice: YangStatement,
    parentValue: unknown,
    path: string,
    errors: InternalIssue[],
    parentNode: XPathNode,
    rootNode: XPathNode
  ): void {
    if (!parentValue || typeof parentValue !== "object" || Array.isArray(parentValue)) {
      if (choice.mandatory === true) {
        errors.push(issue(path, "mandatory-choice", "mandatory choice has no active case"));
      }
      return;
    }
    const obj = parentValue as Record<string, unknown>;

    const choiceIfs = Array.isArray(choice.if_features) ? (choice.if_features as string[]) : [];
    const choiceActive = stmtIfFeaturesSatisfied(choiceIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule);
    if (!choiceActive && this.choiceHasBranchData(choice, obj)) {
      errors.push(
        issue(
          path,
          "if-feature",
          `Choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false — this branch must not exist`
        )
      );
      return;
    }
    if (!choiceActive) {
      return;
    }

    // For choice/case, evaluate "when" in parent context (branch applicability).
    if (
      this.ctx.constraintChecks &&
      !this.checkWhen(choice, this.choiceHasBranchData(choice, obj) ? true : undefined, path, errors, parentNode, rootNode, parentNode)
    ) {
      return;
    }

    const cases = choice.statements.filter((child) => child.keyword === YangTokenType.CASE);
    const activeCases: YangStatement[] = [];
    let hadBlockedCaseWithData = false;

    for (const c of cases) {
      if (!this.caseHasAnyData(c, obj)) {
        continue;
      }
      const caseIfs = Array.isArray(c.if_features) ? (c.if_features as string[]) : [];
      if (!stmtIfFeaturesSatisfied(caseIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
        errors.push(
          issue(
            path,
            "if-feature",
            `Case '${c.name ?? "case"}' of choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false — this branch must not exist`
          )
        );
        return;
      }
      if (this.ctx.constraintChecks && !this.checkWhen(c, true, path, errors, parentNode, rootNode, parentNode)) {
        // case has data but when is false: checkWhen already produced an error
        hadBlockedCaseWithData = true;
        continue;
      }
      activeCases.push(c);
    }

    if (activeCases.length > 1) {
      const names = activeCases.map((c) => c.name ?? "<unnamed>").join(", ");
      errors.push(
        issue(
          path,
          "choice-multiple-cases",
          `choice '${choice.name ?? "choice"}' allows only one case, but multiple are active: ${names}`
        )
      );
      return;
    }

    const active = activeCases[0];
    if (!active) {
      if (hadBlockedCaseWithData) {
        return;
      }
      if (choice.mandatory === true) {
        errors.push(issue(path, "mandatory-choice", "mandatory choice has no active case"));
      }
      return;
    }

    for (const child of active.statements) {
      if (!child.name) {
        continue;
      }
      this.validateStatement(child, this.instanceValue(obj, child), this.childPath(path, child), errors, parentNode, rootNode);
    }
  }

  private choiceHasBranchData(choice: YangStatement, obj: Record<string, unknown>): boolean {
    const cases = choice.statements.filter((child) => child.keyword === YangTokenType.CASE);
    return cases.some((c) => this.caseHasAnyData(c, obj));
  }

  private caseHasAnyData(caseStmt: YangStatement, obj: Record<string, unknown>): boolean {
    return caseStmt.statements.some((child) => this.statementHasMatchingData(child, obj));
  }

  private statementHasMatchingData(stmt: YangStatement, obj: Record<string, unknown>): boolean {
    const keyword = this.effectiveKeyword(stmt);
    if (
      hasTokenType(keyword, [
        YangTokenType.LEAF,
        YangTokenType.LEAF_LIST,
        YangTokenType.CONTAINER,
        YangTokenType.LIST,
        YangTokenType.ANYDATA,
        YangTokenType.ANYXML
      ])
    ) {
      return this.instanceKeys(stmt).some((key) => obj[key] !== undefined);
    }
    if (keyword === YangTokenType.CHOICE) {
      return this.choiceHasBranchData(stmt, obj);
    }
    if (keyword === YangTokenType.CASE) {
      return this.caseHasAnyData(stmt, obj);
    }
    return false;
  }

  /** RFC 7951 member name: local, or ``module:local`` when the node is defined in another module. */
  private instanceKeys(stmt: YangStatement): string[] {
    const local = stmt.name;
    if (!local) {
      return [];
    }
    const parent = this.ctx.module.name ?? "";
    const defined =
      typeof stmt.defining_module === "string" && stmt.defining_module
        ? stmt.defining_module
        : parent;
    if (!parent || defined === parent) {
      return [local];
    }
    return [`${defined}:${local}`];
  }

  private instanceValue(obj: Record<string, unknown>, stmt: YangStatement): unknown {
    for (const key of this.instanceKeys(stmt)) {
      if (Object.prototype.hasOwnProperty.call(obj, key)) {
        return obj[key];
      }
    }
    return undefined;
  }

  /** Display path of a child. `choice` and `case` are not data nodes, so they keep the parent path. */
  private childPath(path: string, child: YangStatement): string {
    const kw = this.effectiveKeyword(child);
    if (kw === YangTokenType.CHOICE || kw === YangTokenType.CASE) {
      return path;
    }
    const member = this.instanceKeys(child)[0] ?? child.name ?? "";
    return path ? `${path}.${member}` : member;
  }

  private effectiveKeyword(stmt: YangStatement): string {
    const raw = stmt.keyword ?? "";
    // Python models notification as a container for instance data (RFC 7951 anydata payloads).
    if (raw === YangTokenType.NOTIFICATION) {
      return YangTokenType.CONTAINER;
    }
    if (raw.includes(":")) {
      const kind = stmt.data_node_kind;
      if (kind === YangTokenType.CONTAINER || kind === YangTokenType.LIST) {
        return kind;
      }
    }
    return raw;
  }

  /**
   * RFC 7950: list instance keys must be unique within the list.
   * Reports the first duplicate only. @returns true if a duplicate was found.
   */
  private checkListKeyUniqueness(
    val: unknown[],
    keyNames: string[],
    listName: string,
    pathStr: string,
    errors: InternalIssue[]
  ): boolean {
    if (keyNames.length === 0) {
      return false;
    }
    const seenKeys = new Map<string, number>();
    for (let i = 0; i < val.length; i += 1) {
      const entry = val[i];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const row = entry as Record<string, unknown>;
      const keyTuple = keyNames.map((k) => row[k]);
      const keyStr = JSON.stringify(keyTuple);
      if (seenKeys.has(keyStr)) {
        const firstIdx = seenKeys.get(keyStr)!;
        const keyDisplay = keyNames.map((k) => `${k}='${String(row[k])}'`).join(", ");
        errors.push(
          issue(
            pathStr,
            "duplicate-key",
            `Duplicate key in list '${listName}': ${keyDisplay} (entries at index ${firstIdx} and ${i})`
          )
        );
        return true;
      }
      seenKeys.set(keyStr, i);
    }
    return false;
  }

  /**
   * RFC 7950 §7.8.3: one error per `unique` set whose values repeat across entries.
   * Entries missing any leaf of the set are ignored.
   */
  private checkListUnique(stmt: YangStatement, val: unknown[], pathStr: string, errors: InternalIssue[]): void {
    const sets = Array.isArray(stmt.unique) ? (stmt.unique as string[][]) : [];
    const missing = Symbol("missing");
    const lookup = (entry: unknown, descPath: string): unknown => {
      let cur: unknown = entry;
      for (const seg of descPath.split("/")) {
        if (!cur || typeof cur !== "object" || Array.isArray(cur) || !Object.prototype.hasOwnProperty.call(cur, seg)) {
          return missing;
        }
        cur = (cur as Record<string, unknown>)[seg];
      }
      return cur;
    };
    for (const paths of sets) {
      const seen = new Map<string, number>();
      for (let i = 0; i < val.length; i += 1) {
        const values = paths.map((p) => lookup(val[i], p));
        if (values.includes(missing)) {
          continue;
        }
        const token = JSON.stringify(values);
        const first = seen.get(token);
        if (first !== undefined) {
          const shown = paths.map((p, j) => `${p}='${String(values[j])}'`).join(", ");
          errors.push(
            issue(
              pathStr,
              "unique",
              `Unique constraint violated in list '${stmt.name ?? "list"}': ${shown} (entries at index ${first} and ${i})`
            )
          );
          break;
        }
        seen.set(token, i);
      }
    }
  }

  /**
   * RFC 7950 instance-identifier: string path; when require-instance is true, path must be absolute
   * and resolve to at least one node in the instance (same idea as Python DocumentValidator).
   */
  /**
   * The type a leaf's `type` derives from, following typedefs where each `type` was written, so a
   * leafref or instance-identifier behind a typedef (local or imported) is checked like a direct one.
   */
  private effectiveType(typeShape: Record<string, unknown>): Record<string, unknown> {
    let current = typeShape;
    for (let depth = 0; depth < 64; depth += 1) {
      const typedef = resolveTypedef(this.ctx.module, current);
      if (!typedef?.type) {
        return current;
      }
      current = typedef.type;
    }
    return current;
  }

  private leafrefPathAst(typeShape: Record<string, unknown>): XPathAstNode | null {
    const rawPath = typeShape.path;
    if (typeof rawPath === "string" && rawPath.trim().length > 0) {
      const recorded = typeShape.xpath_prefixes as Record<string, string> | undefined;
      const text = rawPath.trim();
      const key = `path\u0000${text}\u0000${recorded ? JSON.stringify(recorded) : this.ctx.module.name ?? ""}`;
      const cached = this.xpathCache.get(key);
      if (cached) {
        return cached;
      }
      let ast: XPathAstNode;
      try {
        ast = parseXPathPath(text);
      } catch {
        return null;
      }
      if (xpathPrefixes(ast).size > 0) {
        bindXPathPrefixes(ast, recorded ? (prefix: string) => recorded[prefix] : modulePrefixResolver(this.ctx.module), text);
      }
      this.xpathCache.set(key, ast);
      return ast;
    }
    if (rawPath && typeof rawPath === "object" && !Array.isArray(rawPath) && (rawPath as { kind?: string }).kind === "path") {
      return rawPath as XPathAstNode;
    }
    return null;
  }

  private checkLeafref(
    value: unknown,
    typeShape: Record<string, unknown>,
    path: string,
    errors: InternalIssue[],
    leafContextNode: XPathNode,
    rootNode: XPathNode
  ): void {
    const requireInstance = typeShape.require_instance !== false;
    const ast = this.leafrefPathAst(typeShape);
    if (!ast || ast.kind !== "path") {
      if (requireInstance) {
        errors.push(issue(path, "leafref", "leafref has no path"));
      }
      return;
    }
    try {
      const context: XPathContext = { current: leafContextNode, root: rootNode };
      const result = this.xpath.eval(ast, context, leafContextNode);
      const nodes = Array.isArray(result) ? result : [];
      const allowed = new Set<string>();
      for (const n of nodes) {
        if (!n || typeof n !== "object" || !("data" in n)) {
          continue;
        }
        const v = (n as XPathNode).data;
        if (v !== undefined && v !== null && (typeof v === "string" || typeof v === "number" || typeof v === "boolean")) {
          allowed.add(String(v));
        }
      }
      if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
        errors.push(issue(path, "leafref", "leafref value must be a string, number, or boolean"));
        return;
      }
      const s = String(value);
      if (requireInstance && !allowed.has(s)) {
        errors.push(
          issue(path, "leafref", `leafref: value '${s}' does not reference an existing instance (require-instance is true)`)
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "leafref", `leafref: error evaluating path (${msg})`));
    }
  }

  private checkInstanceIdentifier(
    value: unknown,
    typeShape: Record<string, unknown>,
    path: string,
    errors: InternalIssue[],
    currentNode: XPathNode,
    rootNode: XPathNode
  ): void {
    if (typeof value !== "string") {
      errors.push(issue(path, "instance-identifier", `instance-identifier value must be a string, got ${typeof value}`));
      return;
    }
    const requireInstance = typeShape.require_instance !== false;
    if (!requireInstance) {
      return;
    }
    const s = value.trim();
    if (!s) {
      errors.push(issue(path, "instance-identifier", "instance-identifier path must not be empty when require-instance is true"));
      return;
    }
    let ast: XPathAstNode;
    try {
      ast = parseXPath(s);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "instance-identifier", `instance-identifier: invalid path expression (${msg})`));
      return;
    }
    if (ast.kind !== "path") {
      errors.push(issue(path, "instance-identifier", "instance-identifier: value must be a path expression (e.g. /top/leaf)"));
      return;
    }
    if (!ast.isAbsolute) {
      errors.push(
        issue(path, "instance-identifier", "instance-identifier: only absolute paths are supported (path must start with '/')")
      );
      return;
    }
    const context: XPathContext = { current: currentNode, root: rootNode };
    try {
      const nodes = this.xpath.evalPath(ast, context, rootNode);
      if (nodes.length === 0) {
        errors.push(
          issue(
            path,
            "instance-identifier",
            `instance-identifier: no instance at path ${JSON.stringify(value)} (require-instance is true)`
          )
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "instance-identifier", `instance-identifier: invalid path expression (${msg})`));
    }
  }

  /**
   * Parse a `must` / `when` expression once per distinct prefix binding. A statement with no
   * recorded binding binds against the root module's own prefix and imports.
   */
  private compileXPath(expression: string, recorded: Record<string, string> | undefined): XPathAstNode {
    const key = recorded ? `${expression}\u0000${JSON.stringify(recorded)}` : expression;
    const cached = this.xpathCache.get(key);
    if (cached) {
      return cached;
    }
    const ast = parseXPath(expression);
    if (xpathPrefixes(ast).size > 0) {
      const resolve = recorded ? (prefix: string) => recorded[prefix] : modulePrefixResolver(this.ctx.module);
      bindXPathPrefixes(ast, resolve, expression);
    }
    this.xpathCache.set(key, ast);
    return ast;
  }

  private checkMust(stmt: YangStatement, currentNode: XPathNode, rootNode: XPathNode, path: string, errors: InternalIssue[]): void {
    const mustStatements = stmt.statements.filter((child) => child.keyword === "must" && typeof child.argument === "string");

    for (const mustStmt of mustStatements) {
      const expression = mustStmt.argument as string;
      let ast: XPathAstNode | undefined;
      try {
        ast = this.compileXPath(expression, mustStmt.xpath_prefixes);
      } catch {
        ast = undefined;
      }
      if (!ast) {
        errors.push(
          issue(path, "xpath-error", `Error evaluating must expression on '${stmt.name ?? "node"}'`, expression)
        );
        continue;
      }
      try {
        const context: XPathContext = { current: currentNode, root: rootNode };
        const result = this.xpath.eval(ast, context, currentNode);
        const ok = this.xpathBoolean(result);
        if (!ok) {
          const errorMessage = typeof mustStmt.error_message === "string" && mustStmt.error_message.trim().length > 0
            ? mustStmt.error_message
            : `must constraint not satisfied on '${stmt.name ?? "node"}'`;
          errors.push(issue(path, "must", errorMessage, expression));
        }
      } catch {
        errors.push(issue(path, "xpath-error", `Error evaluating must expression on '${stmt.name ?? "node"}'`, expression));
      }
    }
  }

  private checkWhen(
    stmt: YangStatement,
    value: unknown,
    path: string,
    errors: InternalIssue[],
    currentNode: XPathNode,
    rootNode: XPathNode,
    parentNode: XPathNode
  ): boolean {
    const whenShape = stmt.when as Record<string, unknown> | undefined;
    const expression = typeof whenShape?.expression === "string" ? whenShape.expression : undefined;
    if (!expression || expression.trim().length === 0) {
      return true;
    }

    let ast: XPathAstNode | undefined;
    try {
      ast = this.compileXPath(expression, whenShape?.xpath_prefixes as Record<string, string> | undefined);
    } catch {
      ast = undefined;
    }
    if (!ast) {
      errors.push(issue(path, "xpath-error", `Error evaluating when expression on '${stmt.name ?? "node"}'`, expression));
      return false;
    }

    try {
      const evaluateWithParentContext = whenShape?.evaluate_with_parent_context === true;
      const evalNode = evaluateWithParentContext ? parentNode : currentNode;
      const context: XPathContext = { current: evalNode, root: rootNode };
      const result = this.xpath.eval(ast, context, evalNode);
      const active = this.xpathBoolean(result);
      if (!active) {
        if (value !== undefined) {
          errors.push(issue(path, "when", "node is not allowed by when condition", expression));
        }
        return false;
      }
      return true;
    } catch {
      errors.push(issue(path, "xpath-error", `Error evaluating when expression on '${stmt.name ?? "node"}'`, expression));
      return false;
    }
  }

  private xpathBoolean(value: unknown): boolean {
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
    return value !== null && value !== undefined;
  }

  private anydataModuleMap(modules: YangModule[]): Record<string, YangModule> {
    const map: Record<string, YangModule> = {};
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
  private runAnydataSubtreeValidation(
    stmt: YangStatement,
    value: unknown,
    anydataPath: string,
    errors: InternalIssue[]
  ): void {
    if (!this.ctx.anydataValidation || !value || typeof value !== "object" || Array.isArray(value)) {
      return;
    }
    const mode = this.ctx.anydataValidation.mode;
    const modules = this.ctx.anydataValidation.modules;
    const moduleMap = this.anydataModuleMap(modules);
    const obj = value as Record<string, unknown>;

    for (const [jsonKey, childVal] of Object.entries(obj)) {
      const { statementName, moduleName } = resolveQualifiedTopLevel(jsonKey, moduleMap);
      if (!statementName || !moduleName) {
        errors.push(
          issue(
            `${anydataPath}.${jsonKey}`,
            "unknown-field",
            `Unknown anydata member '${jsonKey}': no matching module:identifier in the provided modules`
          )
        );
        continue;
      }

      const mod = moduleMap[moduleName];
      const top = mod?.findStatement(statementName);
      if (!top) {
        errors.push(issue(`${anydataPath}.${jsonKey}`, "unknown-field", `Unknown anydata member '${jsonKey}'`));
        continue;
      }

      if (top.keyword === YangTokenType.LEAF) {
        errors.push(
          issue(
            `${anydataPath}.${jsonKey}`,
            "type",
            `anydata member '${jsonKey}' maps to a leaf; nested subtree validation expects a container or list`
          )
        );
        continue;
      }

      const fragment = { [statementName]: childVal };
      const payloadIfCtx = mod;
      const payloadCtx: ValidationContext = {
        module: mod,
        typeChecker: new TypeChecker(mod, { typeValidationDebug: this.rootCtx.typeValidationDebug }),
        constraintChecks: mode === AnydataValidationMode.COMPLETE,
        leafTypeMode: mode === AnydataValidationMode.COMPLETE ? "full" : "none",
        typeValidationDebug: this.rootCtx.typeValidationDebug,
        anydataValidation: undefined,
        ifFeatureCtx: payloadIfCtx,
        enabledByModule: buildEnabledFeaturesMap(payloadIfCtx, this.enabledFeaturesOverride)
      };
      const inner = this.collect(payloadCtx, fragment);
      for (const innerIssue of inner.errors) {
        // Prefix matches the previous string form: "<anydata>.<key>: <inner formatted error>".
        errors.push(issue(`${anydataPath}.${jsonKey}`, innerIssue.code, formatIssue(innerIssue)));
      }
    }
  }
}
