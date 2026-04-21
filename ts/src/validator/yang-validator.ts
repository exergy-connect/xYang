import { YangModule } from "../core/model";
import { DocumentValidator, EnabledFeaturesByModule } from "./document-validator";
import { ValidatorExtension, ValidatorExtensionConfig } from "./validator-extension";

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

  enableExtension(extension: ValidatorExtension, config: ValidatorExtensionConfig): void {
    this.documentValidator.enableExtension(extension, config as Record<string, unknown>);
  }

  enable_extension(extension: ValidatorExtension, config: ValidatorExtensionConfig): void {
    this.enableExtension(extension, config);
  }

  validate(data: unknown): ValidationResult {
    const [isValid, errors, warnings] = this.documentValidator.validate(data);
    return { isValid, errors, warnings };
  }
}
