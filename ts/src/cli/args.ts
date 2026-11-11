import { resolve } from "node:path";

export type AnydataValidationCli = "off" | "complete" | "candidate";

export type CommonCliArgs = {
  includePaths: string[];
  positional: string[];
};

export type ValidateCliArgs = CommonCliArgs & {
  anydataValidation: AnydataValidationCli;
  anydataModulePaths: string[];
  format: "text" | "json";
  /** ``null`` enables every declared feature. */
  features: Record<string, string[]> | null;
  nativeJson: boolean;
  /** `--rpc NAME`: validate the data as an instance of that rpc. */
  rpc: string | undefined;
  /** `--action PATH`: validate the data as an instance of the action at that data resource identifier. */
  action: string | undefined;
  /** `--output`: with `--rpc` or `--action`, the output instead of the input. */
  output: boolean;
  /** `--context FILE`: server data next to the operation node. */
  contextFile: string | undefined;
};

export function parseCommonArgs(rest: string[]): CommonCliArgs {
  const includePaths: string[] = [];
  const positional: string[] = [];
  for (let i = 0; i < rest.length; i += 1) {
    const arg = rest[i];
    if (arg === "--include-path") {
      const dir = rest[++i];
      if (!dir) {
        throw new Error("Missing directory after --include-path");
      }
      includePaths.push(resolve(dir));
      continue;
    }
    positional.push(arg!);
  }
  return { includePaths, positional };
}

function parseFeaturesArg(raw: string | undefined): Record<string, string[]> | null {
  if (raw === undefined) {
    throw new Error("Missing JSON after --features");
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (error) {
    throw new Error(`--features must be a JSON object or null: ${(error as Error).message}`);
  }
  if (value === null) {
    return null;
  }
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new Error("--features must be a JSON object mapping module names to feature names, or null");
  }
  const features: Record<string, string[]> = {};
  for (const [name, feats] of Object.entries(value)) {
    if (!Array.isArray(feats) || feats.some((feature) => typeof feature !== "string")) {
      throw new Error(`--features[${name}] must be an array of feature name strings`);
    }
    features[name] = feats;
  }
  return features;
}

export function parseValidateArgs(rest: string[]): ValidateCliArgs {
  const includePaths: string[] = [];
  const anydataModulePaths: string[] = [];
  const positional: string[] = [];
  let anydataValidation: AnydataValidationCli = "off";
  let format: "text" | "json" = "text";
  let features: Record<string, string[]> | null = null;
  let nativeJson = false;
  let rpc: string | undefined;
  let action: string | undefined;
  let output = false;
  let contextFile: string | undefined;

  for (let i = 0; i < rest.length; i += 1) {
    const arg = rest[i];
    if (arg === "--include-path") {
      const dir = rest[++i];
      if (!dir) {
        throw new Error("Missing directory after --include-path");
      }
      includePaths.push(resolve(dir));
      continue;
    }
    if (arg === "--native-json") {
      nativeJson = true;
      continue;
    }
    if (arg === "--rpc") {
      rpc = rest[++i];
      if (!rpc) {
        throw new Error("Missing rpc name after --rpc");
      }
      continue;
    }
    if (arg === "--action") {
      action = rest[++i];
      if (!action) {
        throw new Error("Missing data resource identifier after --action");
      }
      continue;
    }
    if (arg === "--output") {
      output = true;
      continue;
    }
    if (arg === "--context") {
      contextFile = rest[++i];
      if (!contextFile) {
        throw new Error("Missing file after --context");
      }
      continue;
    }
    if (arg === "--format") {
      const value = rest[++i];
      if (value !== "text" && value !== "json") {
        throw new Error("--format must be text or json");
      }
      format = value;
      continue;
    }
    if (arg === "--features") {
      features = parseFeaturesArg(rest[++i]);
      continue;
    }
    if (arg === "--anydata-validation") {
      const mode = rest[++i];
      if (mode !== "off" && mode !== "complete" && mode !== "candidate") {
        throw new Error("--anydata-validation must be off, complete, or candidate");
      }
      anydataValidation = mode;
      continue;
    }
    if (arg === "--anydata-module") {
      const path = rest[++i];
      if (!path) {
        throw new Error("Missing path after --anydata-module");
      }
      anydataModulePaths.push(resolve(path));
      continue;
    }
    if (arg?.startsWith("-") && arg !== "-") {
      throw new Error(`unrecognized argument: ${arg}`);
    }
    positional.push(arg!);
  }

  if (rpc !== undefined && action !== undefined) {
    throw new Error("--rpc and --action are mutually exclusive");
  }
  if (rpc === undefined && action === undefined && (output || contextFile !== undefined)) {
    throw new Error("--output and --context apply only together with --rpc or --action");
  }

  return { includePaths, positional, anydataValidation, anydataModulePaths, format, features, nativeJson, rpc, action, output, contextFile };
}
