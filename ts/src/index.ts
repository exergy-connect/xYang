import { parseYangFile, parseYangString } from "./parser";
import { YangModule, YangStatement } from "./core/model";
import { YangValidator } from "./validator/yang-validator";
import type {
  DetailedValidationResult,
  OperationDirection,
  OperationOptions,
  ValidateCallOptions,
  ValidationIssue,
  YangValidatorOptions
} from "./validator/yang-validator";

export { parseYangFile, parseYangString };
export type { ParseYangFileOptions, ParseYangStringOptions } from "./parser";
export { YangParser } from "./parser/yang-parser";
export { YangValidator };
export type {
  DetailedValidationResult,
  OperationDirection,
  OperationOptions,
  ValidateCallOptions,
  ValidationIssue,
  YangValidatorOptions
};
export {
  buildEnabledFeaturesMap,
  evaluateIfFeatureExpression,
  reachableModuleData,
  stmtIfFeaturesSatisfied
} from "./validator/if-feature-eval";
export type { ModuleData } from "./validator/if-feature-eval";
export { ValidatorExtension } from "./validator/validator-extension";
export type { AnydataValidationConfigInput } from "./ext/anydata_validation";
export { parseAnydataExtensionConfig } from "./ext/anydata_validation";
export { YangModule, YangStatement };
export type { YangIdentifierRef } from "./core/identifier-ref";
export {
  coerceIdentifierRef,
  formatIdentifierRef,
  identifierRef,
  parseAbsoluteSchemaPath,
  parseIdentifierRefAtom
} from "./core/identifier-ref";
export {
  YangCircularUsesError,
  YangRefineTargetNotFoundError,
  YangSemanticError,
  YangSyntaxError
} from "./core/errors";
export { generateJsonSchema, parseJsonSchema } from "./json";

export { inferRequiredFeatures } from "./validator/infer-required-features";

export type ValidateOptions = {
  /** Case-file shape ``{"module": ["feature", ...]}``. ``null`` enables every declared feature. */
  features?: Record<string, readonly string[]> | null;
  /** Extra directories for ``import`` / ``include``. Used only when ``schema`` is a path. */
  includePath?: readonly string[];
  /** Opt in to native dict-style JSON. Default is strict RFC 7951. */
  nativeJson?: boolean;
  /** Validate `data` as an instance of this rpc (RFC 7950 §7.14): `{"module:input": {...}}`, or bare parameters with `nativeJson`. */
  rpc?: string;
  /** Which instance of `rpc`. Default `"input"`. */
  direction?: "input" | "output";
  /** Server data next to the operation node (RFC 7950 §6.4.1) for `must` and `leafref`. Not validated. */
  context?: Record<string, unknown>;
};

function featureMap(
  features: Record<string, readonly string[]> | null | undefined
): Record<string, Set<string>> | undefined {
  if (features == null) {
    return undefined;
  }
  if (typeof features !== "object" || Array.isArray(features)) {
    throw new TypeError("features must be an object mapping module names to feature names, or null");
  }
  const enabled: Record<string, Set<string>> = {};
  for (const [name, feats] of Object.entries(features)) {
    if (!Array.isArray(feats) || feats.some((feature) => typeof feature !== "string")) {
      throw new TypeError(`features[${name}] must be an array of feature name strings`);
    }
    enabled[name] = new Set(feats);
  }
  return enabled;
}

/**
 * Validate ``data`` against ``schema`` and return ``validateDetailed``'s object.
 * ``schema`` is a YANG file path or a parsed module.
 */
export function validate(schema: string | YangModule, data: unknown, options: ValidateOptions = {}): DetailedValidationResult {
  const includePath = options.includePath ?? [];
  const enabled = featureMap(options.features);
  let module: YangModule;
  if (typeof schema === "string") {
    module = parseYangFile(schema, includePath.length > 0 ? { includePath: [...includePath] } : {});
  } else if (schema instanceof YangModule) {
    if (includePath.length > 0) {
      throw new Error("includePath applies only when schema is a path");
    }
    module = schema;
  } else {
    throw new TypeError("schema must be a path or YangModule");
  }
  const validator = new YangValidator(module, enabled ? { enabledFeaturesByModule: enabled } : {});
  return validator.validateDetailed(data, {
    nativeJson: options.nativeJson === true,
    ...(options.rpc !== undefined ? { rpc: options.rpc } : {}),
    ...(options.direction !== undefined ? { direction: options.direction } : {}),
    ...(options.context !== undefined ? { context: options.context } : {})
  });
}
