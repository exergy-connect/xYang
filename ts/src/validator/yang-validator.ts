import { YangModule } from "../core/model";
import { AnydataValidationMode, parseAnydataValidationConfig } from "./anydata-validation";
import { DocumentValidator, EnabledFeaturesByModule } from "./document-validator";
import { ValidatorExtension, ValidatorExtensionConfig } from "./validator-extension";

export type ValidationResult = {
  isValid: boolean;
  errors: string[];
  warnings: string[];
};

export type YangValidatorOptions = {
  enabledFeaturesByModule?: EnabledFeaturesByModule;
};

export class YangValidator {
  private readonly documentValidator: DocumentValidator;

  constructor(private readonly module: YangModule, options: YangValidatorOptions = {}) {
    this.documentValidator = new DocumentValidator(module, {
      enabledFeaturesByModule: options.enabledFeaturesByModule ?? null
    });
  }

  enableExtension(extension: ValidatorExtension, config: ValidatorExtensionConfig): void {
    if (extension === ValidatorExtension.ANYDATA_VALIDATION) {
      const parsed = parseAnydataValidationConfig(config as Record<string, unknown>);
      this.documentValidator.enableExtension(extension, {
        modules: parsed.modules,
        mode: parsed.mode
      });
      return;
    }
    throw new Error(`unknown validator extension: ${String(extension)}`);
  }

  enable_extension(extension: ValidatorExtension, config: ValidatorExtensionConfig): void {
    this.enableExtension(extension, config);
  }

  validate(data: unknown): ValidationResult {
    const [isValid, errors, warnings] = this.documentValidator.validate(data);
    return { isValid, errors, warnings };
  }
}

export { AnydataValidationMode };
