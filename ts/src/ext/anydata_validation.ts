import { YangModule } from "../core/model";

/**
 * Optional anydata subtree validation modes from
 * [draft-ietf-netmod-yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation) §5
 * (anydata-complete / anydata-candidate, aligned with RFC 7950 §8.3.3 datastore semantics).
 */
export enum AnydataValidationMode {
  /** Full RFC 7950 validation for resolved subtree members (anydata-complete). */
  COMPLETE = "complete",
  /** Structural validation without constraint checks: no type, must, when, etc. (anydata-candidate). */
  CANDIDATE = "candidate"
}

export type AnydataValidationConfig = {
  modules: YangModule[];
  mode: AnydataValidationMode;
};

/** Arguments for the anydata-validation extension (RFC 7951 module set for subtree resolution). */
export type AnydataValidationConfigInput = {
  modules: readonly YangModule[];
  mode?: AnydataValidationMode;
};

function rejectUnknownKeys(kwargs: object, allowed: ReadonlySet<string>): void {
  const unexpected = Object.keys(kwargs)
    .filter((k) => !allowed.has(k))
    .sort();
  if (unexpected.length > 0) {
    throw new TypeError(`unexpected keyword arguments: ${JSON.stringify(unexpected)}`);
  }
}

/**
 * Validates arguments for the anydata-validation validator extension (parity with
 * Python `parse_anydata_extension_kwargs`).
 */
export function parseAnydataExtensionConfig(config: AnydataValidationConfigInput): AnydataValidationConfig {
  rejectUnknownKeys(config, new Set(["modules", "mode"]));

  const mode = config.mode === undefined ? AnydataValidationMode.COMPLETE : config.mode;

  const seenNames = new Set<string>();
  for (let i = 0; i < config.modules.length; i += 1) {
    const mod = config.modules[i];
    const moduleName = mod.name;
    if (!moduleName) {
      throw new TypeError(`modules[${i}] must have a module name`);
    }
    if (seenNames.has(moduleName)) {
      throw new TypeError(`duplicate module name '${moduleName}' in modules`);
    }
    seenNames.add(moduleName);
  }

  return {
    modules: [...config.modules],
    mode
  };
}
