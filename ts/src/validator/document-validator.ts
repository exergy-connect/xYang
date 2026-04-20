import { YangModule, YangStatement } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { parseXPath } from "../xpath/parser";
import { XPathAstNode } from "../xpath/ast";
import { XPathContext, XPathEvaluator, XPathNode, XPathSchema } from "../xpath/evaluator";
import { resolveQualifiedTopLevel } from "../encoding";
import { AnydataValidationConfig, AnydataValidationMode } from "./anydata-validation";
import { ValidatorExtension } from "./validator-extension";
import { unsignedTypeCandidateViolation } from "../types";
import { TypeChecker } from "./type-checker";
import { buildEnabledFeaturesMap, ModuleData, stmtIfFeaturesSatisfied } from "./if-feature-eval";

export type EnabledFeaturesByModule = Record<string, ReadonlySet<string>>;

export type LeafTypeMode = "full" | "none" | "unsigned_non_negative";

/** Per-document validation context (host module or an anydata payload shape module). */
export type ValidationContext = {
  module: YangModule;
  typeChecker: TypeChecker;
  constraintChecks: boolean;
  leafTypeMode: LeafTypeMode;
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

  constructor(
    module: YangModule,
    options: {
      constraintChecks?: boolean;
      leafTypeMode?: LeafTypeMode;
      enabledFeaturesByModule?: EnabledFeaturesByModule | null;
    } = {}
  ) {
    this.enabledFeaturesOverride = options.enabledFeaturesByModule ?? null;
    const constraintChecks = options.constraintChecks ?? true;
    const leafTypeMode = options.leafTypeMode ?? (constraintChecks ? "full" : "none");
    const ifFeatureCtx = module.data as ModuleData;
    this.rootCtx = {
      module,
      typeChecker: new TypeChecker(module),
      constraintChecks,
      leafTypeMode,
      anydataValidation: undefined,
      ifFeatureCtx,
      enabledByModule: buildEnabledFeaturesMap(ifFeatureCtx, this.enabledFeaturesOverride)
    };
  }

  private get ctx(): ValidationContext {
    const c = this.contextStack[this.contextStack.length - 1];
    if (!c) {
      throw new Error("DocumentValidator: internal error — no active validation context");
    }
    return c;
  }

  enableExtension(extension: ValidatorExtension, config: Record<string, unknown>): void {
    if (extension !== ValidatorExtension.ANYDATA_VALIDATION) {
      throw new Error(`unknown validator extension: ${String(extension)}`);
    }
    this.rootCtx.anydataValidation = {
      modules: (config.modules as YangModule[]) ?? [],
      mode: (config.mode as AnydataValidationMode | undefined) ?? AnydataValidationMode.COMPLETE
    };
  }

  validate(data: unknown): [boolean, string[], string[]] {
    return this.validateWithContext(this.rootCtx, data);
  }

  /**
   * Validate instance data against one module’s top-level data nodes. Used for the root document
   * and, recursively, for each anydata payload shape without constructing a second DocumentValidator.
   */
  private validateWithContext(ctx: ValidationContext, data: unknown): [boolean, string[], string[]] {
    this.contextStack.push(ctx);
    try {
      const errors: string[] = [];
      const warnings: string[] = [];

      if (!data || typeof data !== "object" || Array.isArray(data)) {
        return [false, ["Document must be an object"], warnings];
      }

      const root = data as Record<string, unknown>;
      const rootNode: XPathNode = { data: root, schema: ctx.module as unknown as XPathSchema, parent: null };
      for (const stmt of ctx.module.statements) {
        if (!stmt.name) {
          continue;
        }
        const keyword = this.effectiveKeyword(stmt);
        if (
          ![
            YangTokenType.CONTAINER,
            YangTokenType.LIST,
            YangTokenType.LEAF,
            YangTokenType.LEAF_LIST,
            YangTokenType.ANYDATA,
            YangTokenType.ANYXML,
            YangTokenType.CHOICE
          ].includes(keyword as YangTokenType)
        ) {
          continue;
        }
        this.validateStatement(stmt, root[stmt.name], stmt.name, errors, rootNode, rootNode);
      }

      return [errors.length === 0, errors, warnings];
    } finally {
      this.contextStack.pop();
    }
  }

  private validateStatement(
    stmt: YangStatement,
    value: unknown,
    path: string,
    errors: string[],
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
        this.validateStatement(child, obj[child.name], `${path}.${child.name}`, errors, parentNode, rootNode);
      }
      return;
    }

    const ifFeatures = stmt.data.if_features;
    const ifFeatureList = Array.isArray(ifFeatures) ? (ifFeatures as string[]) : [];
    if (!stmtIfFeaturesSatisfied(ifFeatureList, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
      if (value !== undefined) {
        errors.push(
          `${path}: Node '${stmt.name ?? "node"}' is present but its 'if-feature' condition is false — this node must not exist`
        );
      }
      return;
    }

    if (this.ctx.constraintChecks && !this.checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode)) {
      return;
    }

    if (keyword === YangTokenType.CONTAINER) {
      if (value === undefined) {
        // `presence` containers that are absent have no instance subtree; do not require inner nodes.
        if (!stmt.data.presence) {
          this.validateMandatoryChildren(stmt, undefined, path, errors, currentNode, rootNode);
        }
        return;
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        errors.push(`${path}: container must be an object`);
        return;
      }
      const obj = value as Record<string, unknown>;
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      for (const child of stmt.statements) {
        const childKw = this.effectiveKeyword(child);
        if (childKw === YangTokenType.CHOICE) {
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

    if (keyword === YangTokenType.LIST) {
      if (value === undefined) {
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
        const itemNode: XPathNode = { data: item, schema: stmt as unknown as XPathSchema, parent: parentNode };
        if (this.ctx.constraintChecks) {
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
        const row = item as Record<string, unknown>;
        for (const child of stmt.statements) {
          const childKw = this.effectiveKeyword(child);
          if (childKw === YangTokenType.CHOICE) {
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

    if (keyword === YangTokenType.LEAF) {
      const mandatory = Boolean(stmt.data.mandatory);
      if (value === undefined) {
        if (mandatory) {
          errors.push(`${path}: mandatory leaf is missing`);
        }
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = (stmt.data.type as Record<string, unknown> | undefined) ?? {};
        const typeName = (typeShape.name as string | undefined) ?? "string";
        if (typeName === YangTokenType.LEAFREF) {
          this.checkLeafref(value, typeShape, path, errors, currentNode, rootNode);
        } else if (typeName === YangTokenType.INSTANCE_IDENTIFIER) {
          this.checkInstanceIdentifier(value, typeShape, path, errors, currentNode, rootNode);
        } else {
          const [ok, reason] = this.ctx.typeChecker.validate(value, typeName, typeShape);
          if (!ok) {
            errors.push(`${path}: ${reason ?? `invalid value for type ${typeName}`}`);
          }
        }
      } else if (this.ctx.leafTypeMode === "unsigned_non_negative") {
        const typeShape = (stmt.data.type as Record<string, unknown> | undefined) ?? {};
        const declared = (typeShape.name as string | undefined) ?? "string";
        const resolved = this.ctx.typeChecker.resolveUnderlyingBuiltinName(declared);
        const reason = unsignedTypeCandidateViolation(value, resolved);
        if (reason) {
          errors.push(`${path}: ${reason}`);
        }
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      return;
    }

    if (keyword === YangTokenType.LEAF_LIST) {
      if (value === undefined) {
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(`${path}: leaf-list must be an array`);
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = (stmt.data.type as Record<string, unknown> | undefined) ?? {};
        const typeName = (typeShape.name as string | undefined) ?? "string";
        for (let i = 0; i < value.length; i += 1) {
          const itemNode: XPathNode = { data: value[i], schema: stmt as unknown as XPathSchema, parent: parentNode };
          if (typeName === YangTokenType.LEAFREF) {
            this.checkLeafref(value[i], typeShape, `${path}[${i}]`, errors, itemNode, rootNode);
          } else if (typeName === YangTokenType.INSTANCE_IDENTIFIER) {
            this.checkInstanceIdentifier(value[i], typeShape, `${path}[${i}]`, errors, itemNode, rootNode);
          } else {
            const [ok, reason] = this.ctx.typeChecker.validate(value[i], typeName, typeShape);
            if (!ok) {
              errors.push(`${path}[${i}]: ${reason ?? `invalid value for type ${typeName}`}`);
            }
          }
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
      } else if (this.ctx.leafTypeMode === "unsigned_non_negative") {
        const typeShape = (stmt.data.type as Record<string, unknown> | undefined) ?? {};
        const declared = (typeShape.name as string | undefined) ?? "string";
        const resolved = this.ctx.typeChecker.resolveUnderlyingBuiltinName(declared);
        for (let i = 0; i < value.length; i += 1) {
          const reason = unsignedTypeCandidateViolation(value[i], resolved);
          if (reason) {
            errors.push(`${path}[${i}]: ${reason}`);
          }
        }
      }
    }

    if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
      const mandatory = Boolean(stmt.data.mandatory);
      if (value === undefined) {
        if (mandatory) {
          errors.push(`${path}: mandatory ${keyword} is missing`);
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

  private collectSchemaInstanceKeys(stmt: YangStatement | undefined, keys: Set<string>): void {
    if (!stmt) {
      return;
    }
    const kw = this.effectiveKeyword(stmt);
    if (kw === YangTokenType.CHOICE) {
      for (const c of stmt.statements ?? []) {
        if (c.keyword !== YangTokenType.CASE) {
          continue;
        }
        for (const br of c.statements ?? []) {
          this.collectSchemaInstanceKeys(br, keys);
        }
      }
      return;
    }
    if (kw === YangTokenType.LIST) {
      if (stmt.name) {
        keys.add(stmt.name);
      }
      return;
    }
    if (kw === YangTokenType.CONTAINER) {
      const ch = stmt.statements ?? [];
      const onlyChoice = ch.length === 1 && this.effectiveKeyword(ch[0]) === YangTokenType.CHOICE;
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
  private rejectUnknownContainerKeys(stmt: YangStatement, obj: Record<string, unknown>, path: string, errors: string[]): void {
    if (stmt.data.presence) {
      return;
    }
    if (stmt.name !== "array") {
      return;
    }
    const children = stmt.statements ?? [];
    if (children.length !== 1 || this.effectiveKeyword(children[0]) !== YangTokenType.CHOICE) {
      return;
    }
    const allowed = new Set<string>();
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

  private rejectUnknownListItemKeys(stmt: YangStatement, row: Record<string, unknown>, path: string, errors: string[]): void {
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

  private collectDirectChildKeys(parent: YangStatement): Set<string> {
    const keys = new Set<string>();
    const walk = (stmt: YangStatement): void => {
      const kw = this.effectiveKeyword(stmt);
      if (kw === YangTokenType.CHOICE || kw === YangTokenType.CASE) {
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

  private validateChoice(
    choice: YangStatement,
    parentValue: unknown,
    path: string,
    errors: string[],
    parentNode: XPathNode,
    rootNode: XPathNode
  ): void {
    if (!parentValue || typeof parentValue !== "object" || Array.isArray(parentValue)) {
      if (choice.data.mandatory === true) {
        errors.push(`${path}: mandatory choice has no active case`);
      }
      return;
    }
    const obj = parentValue as Record<string, unknown>;

    const choiceIfs = Array.isArray(choice.data.if_features) ? (choice.data.if_features as string[]) : [];
    const choiceActive = stmtIfFeaturesSatisfied(choiceIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule);
    if (!choiceActive && this.choiceHasBranchData(choice, obj)) {
      errors.push(
        `${path}: Choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false — this branch must not exist`
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
      const caseIfs = Array.isArray(c.data.if_features) ? (c.data.if_features as string[]) : [];
      if (!stmtIfFeaturesSatisfied(caseIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
        errors.push(
          `${path}: Case '${c.name ?? "case"}' of choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false — this branch must not exist`
        );
        return;
      }
      if (this.ctx.constraintChecks && !this.checkWhen(c, true, `${path}.${c.name ?? "case"}`, errors, parentNode, rootNode, parentNode)) {
        // case has data but when is false: checkWhen already produced an error
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
      [
        YangTokenType.LEAF,
        YangTokenType.LEAF_LIST,
        YangTokenType.CONTAINER,
        YangTokenType.LIST,
        YangTokenType.ANYDATA,
        YangTokenType.ANYXML
      ].includes(keyword as YangTokenType)
    ) {
      return Boolean(stmt.name && obj[stmt.name] !== undefined);
    }
    if (keyword === YangTokenType.CHOICE) {
      return this.choiceHasBranchData(stmt, obj);
    }
    if (keyword === YangTokenType.CASE) {
      return this.caseHasAnyData(stmt, obj);
    }
    return false;
  }

  private effectiveKeyword(stmt: YangStatement): string {
    const raw = stmt.keyword ?? "";
    if (raw.includes(":")) {
      const kind = stmt.data.data_node_kind;
      if (kind === YangTokenType.CONTAINER || kind === YangTokenType.LIST) {
        return kind;
      }
    }
    return raw;
  }

  /**
   * RFC 7950: list instance keys must be unique within the list.
   * @returns true if a duplicate was found (caller should skip per-entry validation).
   */
  private checkListKeyUniqueness(
    val: unknown[],
    keyNames: string[],
    listName: string,
    pathStr: string,
    errors: string[]
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
  private leafrefPathAst(typeShape: Record<string, unknown>): XPathAstNode | null {
    const rawPath = typeShape.path;
    if (typeof rawPath === "string" && rawPath.trim().length > 0) {
      try {
        return parseXPath(rawPath.trim());
      } catch {
        return null;
      }
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
    errors: string[],
    leafContextNode: XPathNode,
    rootNode: XPathNode
  ): void {
    const requireInstance = typeShape.require_instance !== false;
    const ast = this.leafrefPathAst(typeShape);
    if (!ast || ast.kind !== "path") {
      if (requireInstance) {
        errors.push(`${path}: leafref has no path`);
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

  private checkInstanceIdentifier(
    value: unknown,
    typeShape: Record<string, unknown>,
    path: string,
    errors: string[],
    currentNode: XPathNode,
    rootNode: XPathNode
  ): void {
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
    let ast: XPathAstNode;
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
    const context: XPathContext = { current: currentNode, root: rootNode };
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

  private checkMust(stmt: YangStatement, currentNode: XPathNode, rootNode: XPathNode, path: string, errors: string[]): void {
    const mustStatements = stmt.statements.filter((child) => child.keyword === "must" && typeof child.argument === "string");

    for (const mustStmt of mustStatements) {
      const expression = mustStmt.argument as string;
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
        const context: XPathContext = { current: currentNode, root: rootNode };
        const result = this.xpath.eval(ast, context, currentNode);
        const ok = this.xpathBoolean(result);
        if (!ok) {
          const errorMessage = typeof mustStmt.data.error_message === "string" && mustStmt.data.error_message.trim().length > 0
            ? mustStmt.data.error_message
            : `must constraint not satisfied on '${stmt.name ?? "node"}'`;
          errors.push(`${path}: ${errorMessage}`);
        }
      } catch {
        errors.push(`${path}: Error evaluating must expression on '${stmt.name ?? "node"}'`);
      }
    }
  }

  private checkWhen(
    stmt: YangStatement,
    value: unknown,
    path: string,
    errors: string[],
    currentNode: XPathNode,
    rootNode: XPathNode,
    parentNode: XPathNode
  ): boolean {
    const whenShape = stmt.data.when as Record<string, unknown> | undefined;
    const expression = typeof whenShape?.expression === "string" ? whenShape.expression : undefined;
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
      const context: XPathContext = { current: evalNode, root: rootNode };
      const result = this.xpath.eval(ast, context, evalNode);
      const active = this.xpathBoolean(result);
      if (!active) {
        if (value !== undefined) {
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

  private validateMandatoryChildren(
    stmt: YangStatement,
    parentValue: unknown,
    path: string,
    errors: string[],
    parentNode: XPathNode,
    rootNode: XPathNode
  ): void {
    const obj = parentValue && typeof parentValue === "object" && !Array.isArray(parentValue)
      ? (parentValue as Record<string, unknown>)
      : undefined;

    for (const child of stmt.statements) {
      const childKeyword = child.keyword ?? "";
      if (
        ![YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes(childKeyword as YangTokenType) ||
        !child.name
      ) {
        continue;
      }
      const cIf = Array.isArray(child.data.if_features) ? (child.data.if_features as string[]) : [];
      if (!stmtIfFeaturesSatisfied(cIf, this.ctx.ifFeatureCtx, this.ctx.enabledByModule)) {
        continue;
      }
      if (!child.data.mandatory) {
        continue;
      }
      const childValue = obj?.[child.name];
      const childNode: XPathNode = { data: childValue, schema: child as unknown as XPathSchema, parent: parentNode };
      if (this.ctx.constraintChecks && !this.checkWhen(child, childValue, `${path}.${child.name}`, errors, childNode, rootNode, parentNode)) {
        continue;
      }
      if (!obj || obj[child.name] === undefined) {
        errors.push(`${path}.${child.name}: mandatory ${childKeyword} is missing`);
      }
    }
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

  private runAnydataSubtreeValidation(
    stmt: YangStatement,
    value: unknown,
    anydataPath: string,
    errors: string[]
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
          `${anydataPath}.${jsonKey}: Unknown anydata member '${jsonKey}': no matching module:identifier in the provided modules`
        );
        continue;
      }

      const mod = moduleMap[moduleName];
      const top = mod?.findStatement(statementName);
      if (!top) {
        errors.push(`${anydataPath}.${jsonKey}: Unknown anydata member '${jsonKey}'`);
        continue;
      }

      if (top.keyword === YangTokenType.LEAF) {
        errors.push(
          `${anydataPath}.${jsonKey}: anydata member '${jsonKey}' maps to a leaf; nested subtree validation expects a container or list`
        );
        continue;
      }

      const fragment = { [statementName]: childVal };
      const payloadIfCtx = mod.data as ModuleData;
      const payloadCtx: ValidationContext = {
        module: mod,
        typeChecker: new TypeChecker(mod),
        constraintChecks: mode === AnydataValidationMode.COMPLETE,
        leafTypeMode:
          mode === AnydataValidationMode.COMPLETE ? "full" : "unsigned_non_negative",
        anydataValidation: undefined,
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
}
