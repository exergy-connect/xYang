import { warnDeprecatedOnce } from "../core/deprecation";
import { YangModule } from "../core/model";
import type { AnydataValidationConfigInput } from "../ext/anydata_validation";
import { encodingErrors, iterInstance, projectInstance, remapPointer } from "../encoding";
import {
  DetailedValidationResult,
  DocumentValidator,
  EnabledFeaturesByModule,
  ValidationIssue
} from "./document-validator";
import { ValidatorExtension } from "./validator-extension";
import {
  accessibleModule,
  checkOperationOptions,
  findBody,
  findRpc,
  operationNode,
  resolveAction,
  wrapperMember
} from "./operation";
import type { OperationOptions } from "./operation";

export type { DetailedValidationResult, ValidationIssue };
export type { OperationDirection, OperationOptions } from "./operation";

/** Per-call validation options. `rpc`, `direction` and `context` select an rpc instance (RFC 7950 §7.14). */
export type ValidateCallOptions = { nativeJson?: boolean } & OperationOptions;

export type ValidationResult = {
  isValid: boolean;
  errors: string[];
  warnings: string[];
};

export type YangValidatorOptions = {
  enabledFeaturesByModule?: EnabledFeaturesByModule;
  /** When true, this instance emits `console.debug` for leaf type validation. */
  typeValidationDebug?: boolean;
  /** Opt in to native dict-style JSON. Default is strict RFC 7951. */
  nativeJson?: boolean;
};

export class YangValidator {
  private readonly documentValidator: DocumentValidator;
  private readonly extensions: Array<[ValidatorExtension, AnydataValidationConfigInput]> = [];
  private typeValidationDebug: boolean;

  constructor(private readonly module: YangModule, private readonly options: YangValidatorOptions = {}) {
    this.typeValidationDebug = options.typeValidationDebug === true;
    this.documentValidator = this.newDocumentValidator(module);
  }

  private newDocumentValidator(root: YangModule): DocumentValidator {
    const validator = new DocumentValidator(root, {
      enabledFeaturesByModule: this.options.enabledFeaturesByModule ?? null,
      typeValidationDebug: this.typeValidationDebug
    });
    for (const [extension, config] of this.extensions) {
      validator.enableExtension(extension, config);
    }
    return validator;
  }

  /**
   * Toggle `console.debug` tracing for leaf type checks performed by this validator only.
   */
  setTypeValidationDebug(on: boolean): this {
    this.typeValidationDebug = on;
    this.documentValidator.setTypeValidationDebug(on);
    return this;
  }

  enableExtension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void {
    this.documentValidator.enableExtension(extension, config);
    this.extensions.push([extension, config]);
  }

  /** @deprecated use enableExtension */
  enable_extension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void {
    warnDeprecatedOnce("enable_extension", "enableExtension");
    this.enableExtension(extension, config);
  }

  /**
   * Validate `data` against the module, or against one rpc's or action's input or output.
   *
   * With `options.rpc` (a name) or `options.action` (the RFC 8040 §3.5.3 data resource identifier
   * `/module:list=key/action`) set, `data` is that operation's `options.direction` (`"input"`
   * default, or `"output"`) instance: the RFC 8040 §3.6 `{"module:input": {...}}` wrapper in RFC
   * 7951 mode, the bare parameter object with `nativeJson`. `options.context` is server data
   * (required for an action). It is validated first; its errors carry `document: "context"` and the
   * operation is then not checked. Otherwise the operation's `must` and `leafref` reach it (RFC 7950
   * §6.4.1). An unknown rpc or action, or a bad option combination, throws.
   */
  validate(data: unknown, options: ValidateCallOptions = {}): ValidationResult {
    checkOperationOptions(options);
    if (options.rpc !== undefined || options.action !== undefined) {
      const detailed = this.validateOperation(data, options);
      const text = (issue: ValidationIssue): string => {
        const where = issue.document ? `${issue.document} ${issue.path}` : issue.path;
        return where ? `${where}: ${issue.message}` : issue.message;
      };
      return { isValid: detailed.valid, errors: detailed.errors.map(text), warnings: detailed.warnings.map(text) };
    }
    const prepared = this.prepare(data, options.nativeJson === true);
    const [isValid, errors, warnings] = this.documentValidator.validate(prepared.data);
    const encoding = prepared.errors.map((issue) => (issue.path ? `${issue.path}: ${issue.message}` : issue.message));
    const all = [...encoding, ...errors];
    return { isValid: isValid && encoding.length === 0, errors: all, warnings };
  }

  /**
   * Structured issues. `validate()` string output is unchanged.
   * Each issue is `{ code, path, message, expression?, severity }` with `path` a JSON Pointer; an issue
   * about the server data context of an rpc or action also has `document: "context"`.
   */
  validateDetailed(data: unknown, options: ValidateCallOptions = {}): DetailedValidationResult {
    checkOperationOptions(options);
    if (options.rpc !== undefined || options.action !== undefined) {
      return this.validateOperation(data, options);
    }
    return this.validateDocument(data, options.nativeJson === true);
  }

  private validateDocument(data: unknown, nativeJson: boolean): DetailedValidationResult {
    const prepared = this.prepare(data, nativeJson);
    const result = this.documentValidator.validateDetailed(prepared.data);
    const encoding: ValidationIssue[] = prepared.errors.map((issue) => ({
      code: issue.code,
      path: issue.path,
      message: issue.message,
      severity: "error"
    }));
    const errors = [...encoding, ...result.errors];
    return { valid: errors.length === 0, errors, warnings: result.warnings };
  }

  private validateOperation(data: unknown, options: ValidateCallOptions): DetailedValidationResult {
    const direction = options.direction ?? "input";
    const nativeJson = options.nativeJson === true;
    const target =
      options.rpc !== undefined ? findRpc(this.module, options.rpc) : resolveAction(this.module, options.action as string);
    const operation = operationNode(target.operation, findBody(target.operation, direction));
    let contextWarnings: ValidationIssue[] = [];
    if (options.context !== undefined) {
      // RFC 7950 §6.4.1: the operation reads the server data, so it must be valid data first.
      const checked = this.validateDocument(options.context, nativeJson);
      const mark = (issue: ValidationIssue): ValidationIssue => ({ document: "context", ...issue });
      if (!checked.valid) {
        return { valid: false, errors: checked.errors.map(mark), warnings: checked.warnings.map(mark) };
      }
      contextWarnings = checked.warnings.map(mark);
    }
    let wrapper: string | null = null;
    let params: unknown = data;
    const fail = (issue: Omit<ValidationIssue, "severity">): DetailedValidationResult => ({
      valid: false,
      errors: [{ ...issue, severity: "error" }],
      warnings: contextWarnings
    });
    if (!nativeJson) {
      wrapper = wrapperMember(target.moduleName, direction);
      const keys = data && typeof data === "object" && !Array.isArray(data) ? Object.keys(data) : null;
      if (!keys || keys.length !== 1 || keys[0] !== wrapper) {
        const found = keys ? keys.map((key) => `'${key}'`).join(", ") : Array.isArray(data) ? "array" : typeof data;
        const kind = options.rpc !== undefined ? "rpc" : "action";
        return fail({
          code: "operation-wrapper",
          path: "",
          message:
            `${kind} ${direction} must be an object with the single member '${wrapper}' ` +
            `(RFC 8040 §3.6); found ${found || "no members"}. Pass nativeJson for the bare parameter object`
        });
      }
      params = (data as Record<string, unknown>)[wrapper];
      if (!params || typeof params !== "object" || Array.isArray(params)) {
        return fail({ code: "type", path: `/${escapePointer(wrapper)}`, message: `${direction} must be an object` });
      }
    } else if (!params || typeof params !== "object" || Array.isArray(params)) {
      return fail({ code: "type", path: "", message: "operation parameters must be an object" });
    }
    const host = this.module.name ?? "";
    const nodes = [...iterInstance(params, this.module, { nativeJson, schema: operation, parentModule: target.moduleName, atRoot: false })];
    const projected = projectInstance(nodes, host);
    const rootData =
      options.context !== undefined ? projectInstance([...iterInstance(options.context, this.module, { nativeJson })], host).data : {};
    const accessible = accessibleModule(this.module, target, operation);
    const validator = this.newDocumentValidator(accessible.module);
    validator.setPointerMap(projected.pointerMap);
    const result = validator.validateOperationDetailed({
      target,
      operation,
      parentCopies: accessible.parentCopies,
      params: projected.data,
      rootData,
      wrapper
    });
    const encoding: ValidationIssue[] = encodingErrors(nodes).map((item) => ({
      code: item.code,
      path: wrapper === null ? item.path : `/${escapePointer(wrapper)}${item.path}`,
      message: item.message,
      severity: "error"
    }));
    const errors = [...encoding, ...result.errors];
    return { valid: errors.length === 0, errors, warnings: [...contextWarnings, ...result.warnings] };
  }

  private prepare(data: unknown, nativeJson: boolean): {
    data: unknown;
    errors: Array<{ path: string; code: string; message: string }>;
  } {
    const nodes = [...iterInstance(data, this.module, { nativeJson })];
    const projected = projectInstance(nodes, this.module.name ?? "");
    this.documentValidator.setPointerMap(projected.pointerMap);
    return { data: projected.data, errors: encodingErrors(nodes) };
  }
}

function escapePointer(token: string): string {
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}
