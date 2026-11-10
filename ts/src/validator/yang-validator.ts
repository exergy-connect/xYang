import { YangModule } from "../core/model";
import type { AnydataValidationConfigInput } from "../ext/anydata_validation";
import { normalizationErrors, normalizeInstance } from "../encoding";
import {
  DetailedValidationResult,
  DocumentValidator,
  EnabledFeaturesByModule,
  ValidationIssue
} from "./document-validator";
import { ValidatorExtension } from "./validator-extension";

export type { DetailedValidationResult, ValidationIssue };

export type ValidationResult = {
  isValid: boolean;
  errors: string[];
  warnings: string[];
};

export type YangValidatorOptions = {
  enabledFeaturesByModule?: EnabledFeaturesByModule;
  /** When true, this instance emits `console.debug` for leaf type validation. */
  typeValidationDebug?: boolean;
};

export class YangValidator {
  private readonly documentValidator: DocumentValidator;

  constructor(private readonly module: YangModule, options: YangValidatorOptions = {}) {
    this.documentValidator = new DocumentValidator(module, {
      enabledFeaturesByModule: options.enabledFeaturesByModule ?? null,
      typeValidationDebug: options.typeValidationDebug
    });
  }

  /**
   * Toggle `console.debug` tracing for leaf type checks performed by this validator only.
   */
  setTypeValidationDebug(on: boolean): this {
    this.documentValidator.setTypeValidationDebug(on);
    return this;
  }

  enableExtension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void {
    this.documentValidator.enableExtension(extension, config);
  }

  enable_extension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void {
    this.enableExtension(extension, config);
  }

  validate(data: unknown): ValidationResult {
    const normalized = normalizeInstance(data, this.module);
    const [isValid, errors, warnings] = this.documentValidator.validate(normalized);
    const encoding = normalizationErrors(normalized).map((issue) =>
      issue.path ? `${issue.path}: ${issue.message}` : issue.message
    );
    const all = [...encoding, ...errors];
    return { isValid: isValid && encoding.length === 0, errors: all, warnings };
  }

  /**
   * Structured issues. `validate()` string output is unchanged.
   * Each issue is `{ code, path, message, expression?, severity }` with `path` a JSON Pointer.
   */
  validateDetailed(data: unknown): DetailedValidationResult {
    const normalized = normalizeInstance(data, this.module);
    const result = this.documentValidator.validateDetailed(normalized);
    const encoding: ValidationIssue[] = normalizationErrors(normalized).map((issue) => ({
      code: issue.code,
      path: issue.path,
      message: issue.message,
      severity: "error"
    }));
    const errors = [...encoding, ...result.errors];
    return { valid: errors.length === 0, errors, warnings: result.warnings };
  }
}
