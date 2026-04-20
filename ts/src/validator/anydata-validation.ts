import { YangModule } from "../core/model";

export enum AnydataValidationMode {
  COMPLETE = "complete",
  CANDIDATE = "candidate"
}

export type AnydataValidationConfig = {
  modules: YangModule[];
  mode: AnydataValidationMode;
};

export function parseAnydataValidationConfig(config: Record<string, unknown>): AnydataValidationConfig {
  const rest = { ...config };
  const modules = rest.modules;
  delete rest.modules;
  const modeRaw = rest.mode;
  delete rest.mode;

  const unknownKeys = Object.keys(rest);
  if (unknownKeys.length > 0) {
    throw new TypeError(`unexpected keyword arguments: ${JSON.stringify(unknownKeys)}`);
  }

  if (!Array.isArray(modules)) {
    throw new TypeError("'modules' must be an array of YangModule");
  }

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

