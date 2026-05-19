import { resolve } from "node:path";

export type AnydataValidationCli = "off" | "complete" | "candidate";

export type CommonCliArgs = {
  includePaths: string[];
  positional: string[];
};

export type ValidateCliArgs = CommonCliArgs & {
  anydataValidation: AnydataValidationCli;
  anydataModulePaths: string[];
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

export function parseValidateArgs(rest: string[]): ValidateCliArgs {
  const includePaths: string[] = [];
  const anydataModulePaths: string[] = [];
  const positional: string[] = [];
  let anydataValidation: AnydataValidationCli = "off";

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
    positional.push(arg!);
  }

  return { includePaths, positional, anydataValidation, anydataModulePaths };
}
