import { AnydataValidationConfig, parseAnydataValidationConfig } from "../validator/anydata-validation";

/**
 * Parses `ANYDATA_VALIDATION` extension kwargs: `modules` is a `YangModule[]`, optional `mode`.
 * @see parseAnydataValidationConfig
 */
export function parseAnydataExtensionConfig(config: Record<string, unknown>): AnydataValidationConfig {
  return parseAnydataValidationConfig(config);
}
