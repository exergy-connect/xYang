import { YangModule } from "../core/model";

export enum AnydataValidationMode {
  COMPLETE = "complete",
  CANDIDATE = "candidate"
}

export type AnydataValidationConfig = {
  modules: YangModule[];
  mode: AnydataValidationMode;
};

function rejectUnknownKeys(kwargs: Record<string, unknown>, allowed: ReadonlySet<string>): void {
  const unknown = Object.keys(kwargs)
    .filter((k) => !allowed.has(k))
    .sort();
  if (unknown.length > 0) {
    throw new TypeError(`unexpected keyword arguments: ${JSON.stringify(unknown)}`);
  }
}

function parseAnydataValidationConfig(config: Record<string, unknown>): AnydataValidationConfig {
  rejectUnknownKeys(config, new Set(["modules", "mode"]));

  const modules = config.modules;
  if (!Array.isArray(modules)) {
    throw new TypeError("'modules' must be an array of YangModule");
  }

  const modeRaw = config.mode;
  const mode = modeRaw === undefined ? AnydataValidationMode.COMPLETE : modeRaw;
  if (mode !== AnydataValidationMode.COMPLETE && mode !== AnydataValidationMode.CANDIDATE) {
    throw new TypeError("'mode' must be an AnydataValidationMode");
  }

  const seenNames = new Set<string>();
  for (let i = 0; i < modules.length; i += 1) {
    const value = modules[i];
    if (!(value instanceof YangModule)) {
      throw new TypeError(`modules[${i}] must be a YangModule`);
    }
    const moduleName = value.name;
    if (!moduleName) {
      throw new TypeError(`modules[${i}] must have a module name`);
    }
    if (seenNames.has(moduleName)) {
      throw new TypeError(`duplicate module name '${moduleName}' in modules`);
    }
    seenNames.add(moduleName);
  }

  return {
    modules: modules as YangModule[],
    mode
  };
}

/**
 * Validates keyword arguments for the anydata-validation validator extension (parity with
 * Python `parse_anydata_extension_kwargs`).
 */
export function parseAnydataExtensionConfig(config: Record<string, unknown>): AnydataValidationConfig {
  return parseAnydataValidationConfig(config);
}
