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
  wrapperMember
} from "./operation";
import type { OperationOptions } from "./operation";
import type { YangStatement } from "../core/model";

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
   * Validate `data` against the module, or against one rpc's input or output.
   *
   * With `options.rpc` set, `data` is that rpc's `options.direction` (`"input"` default, or
   * `"output"`) instance: the RFC 8040 `{"module:input": {...}}` wrapper in RFC 7951 mode, the
   * bare parameter object with `nativeJson`. `options.context` is optional server data that the
   * rpc's `must` and `leafref` may reach (RFC 7950 §6.4.1); it is not validated. An unknown rpc,
   * or `direction` / `context` without `rpc`, throws.
   */
  validate(data: unknown, options: ValidateCallOptions = {}): ValidationResult {
    checkOperationOptions(options);
    if (options.rpc !== undefined) {
      const prepared = this.prepareOperation(data, options);
      if ("issue" in prepared) {
        const text = prepared.issue.path ? `${prepared.issue.path}: ${prepared.issue.message}` : prepared.issue.message;
        return { isValid: false, errors: [text], warnings: [] };
      }
      const [isValid, errors, warnings] = prepared.validator.validateOperationText(
        prepared.rpc,
        prepared.operation,
        prepared.params,
        prepared.rootData,
        prepared.wrapper
      );
      const encoding = prepared.errors.map((item) => (item.path ? `${item.path}: ${item.message}` : item.message));
      return { isValid: isValid && encoding.length === 0, errors: [...encoding, ...errors], warnings };
    }
    const prepared = this.prepare(data, options.nativeJson === true);
    const [isValid, errors, warnings] = this.documentValidator.validate(prepared.data);
    const encoding = prepared.errors.map((issue) => (issue.path ? `${issue.path}: ${issue.message}` : issue.message));
    const all = [...encoding, ...errors];
    return { isValid: isValid && encoding.length === 0, errors: all, warnings };
  }

  /**
   * Structured issues. `validate()` string output is unchanged.
   * Each issue is `{ code, path, message, expression?, severity }` with `path` a JSON Pointer.
   */
  validateDetailed(data: unknown, options: ValidateCallOptions = {}): DetailedValidationResult {
    checkOperationOptions(options);
    if (options.rpc !== undefined) {
      const prepared = this.prepareOperation(data, options);
      if ("issue" in prepared) {
        return { valid: false, errors: [prepared.issue], warnings: [] };
      }
      const result = prepared.validator.validateOperationDetailed(
        prepared.rpc,
        prepared.operation,
        prepared.params,
        prepared.rootData,
        prepared.wrapper
      );
      const encoding: ValidationIssue[] = prepared.errors.map((item) => ({
        code: item.code,
        path: prepared.wrapper === null ? item.path : `/${escapePointer(prepared.wrapper)}${item.path}`,
        message: item.message,
        severity: "error"
      }));
      const errors = [...encoding, ...result.errors];
      return { valid: errors.length === 0, errors, warnings: result.warnings };
    }
    const prepared = this.prepare(data, options.nativeJson === true);
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

  private prepareOperation(
    data: unknown,
    options: ValidateCallOptions
  ):
    | { issue: ValidationIssue }
    | {
        validator: DocumentValidator;
        rpc: YangStatement;
        operation: YangStatement;
        params: Record<string, unknown>;
        rootData: Record<string, unknown>;
        wrapper: string | null;
        errors: Array<{ path: string; code: string; message: string }>;
      } {
    const direction = options.direction ?? "input";
    const nativeJson = options.nativeJson === true;
    const rpc = findRpc(this.module, options.rpc as string);
    const operation = operationNode(rpc, findBody(rpc, direction));
    let wrapper: string | null = null;
    let params: unknown = data;
    if (!nativeJson) {
      wrapper = wrapperMember(this.module, direction);
      const keys = data && typeof data === "object" && !Array.isArray(data) ? Object.keys(data) : null;
      if (!keys || keys.length !== 1 || keys[0] !== wrapper) {
        const found = keys ? keys.map((key) => `'${key}'`).join(", ") : Array.isArray(data) ? "array" : typeof data;
        return {
          issue: {
            code: "rpc-wrapper",
            path: "",
            message:
              `rpc ${direction} must be an object with the single member '${wrapper}' ` +
              `(RFC 8040 §3.6); found ${found || "no members"}. Pass nativeJson for the bare parameter object`,
            severity: "error"
          }
        };
      }
      params = (data as Record<string, unknown>)[wrapper];
      if (!params || typeof params !== "object" || Array.isArray(params)) {
        return {
          issue: { code: "type", path: `/${escapePointer(wrapper)}`, message: `${direction} must be an object`, severity: "error" }
        };
      }
    } else if (!params || typeof params !== "object" || Array.isArray(params)) {
      return { issue: { code: "type", path: "", message: "rpc parameters must be an object", severity: "error" } };
    }
    const owner = this.module.name ?? "";
    const nodes = [...iterInstance(params, this.module, { nativeJson, schema: operation, parentModule: owner, atRoot: false })];
    const projected = projectInstance(nodes, owner);
    let rootData: Record<string, unknown> = {};
    if (options.context !== undefined) {
      const contextNodes = [...iterInstance(options.context, this.module, { nativeJson })];
      const problems = encodingErrors(contextNodes);
      if (problems.length > 0) {
        throw new Error(
          `context is not valid instance data at ${problems[0]!.path || "/"}: ${problems[0]!.message}`
        );
      }
      rootData = projectInstance(contextNodes, owner).data;
    }
    rootData[operation.name as string] = projected.data;
    const validator = this.newDocumentValidator(accessibleModule(this.module, operation));
    validator.setPointerMap(projected.pointerMap);
    return {
      validator,
      rpc,
      operation,
      params: projected.data,
      rootData,
      wrapper,
      errors: encodingErrors(nodes)
    };
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
