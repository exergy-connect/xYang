import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";
import { AnydataValidationMode } from "./ext/anydata_validation";
import { parseYangFile, YangParser } from "./parser";
import { ValidatorExtension } from "./validator/validator-extension";
import { YangValidator } from "./validator/yang-validator";
import { generateJsonSchema } from "./json";
import { parseCommonArgs, parseValidateArgs } from "./cli/args";
import { loadAnydataModules, normalizeRfc7951InstanceRoot } from "./cli/load-anydata-modules";

function printUsage(): void {
  process.stdout.write(
    [
      "xyang-ts commands:",
      "  parse [--include-path DIR]... <file.yang>",
      "  validate [--include-path DIR]... [--anydata-validation MODE] [--anydata-module PATH]... <file.yang> [data.json]",
      "  convert [--include-path DIR]... <file.yang>",
      "",
      "  --anydata-validation  off | complete | candidate  (default: off)",
      "  --anydata-module      additional .yang for anydata subtree validation (repeatable)"
    ].join("\n") + "\n"
  );
}

function main(argv: string[]): number {
  const [, , command, ...rest] = argv;
  if (!command) {
    printUsage();
    return 0;
  }

  if (command === "parse") {
    const { includePaths, positional } = parseCommonArgs(rest);
    const file = positional[0];
    if (!file) {
      throw new Error("Missing <file.yang>");
    }
    const parseOpts = includePaths.length > 0 ? { includePath: includePaths } : {};
    const module = parseYangFile(file, parseOpts);
    process.stdout.write(`${module.name}\n`);
    return 0;
  }

  if (command === "validate") {
    const { includePaths, positional, anydataValidation, anydataModulePaths } = parseValidateArgs(rest);
    const yangFile = positional[0];
    if (!yangFile) {
      throw new Error("Missing <file.yang>");
    }
    if (!existsSync(yangFile)) {
      throw new Error(`file not found: ${yangFile}`);
    }

    const parseOpts = includePaths.length > 0 ? { includePath: includePaths } : {};
    const module = parseYangFile(yangFile, parseOpts);
    const validator = new YangValidator(module);

    if (anydataValidation !== "off") {
      for (const path of anydataModulePaths) {
        if (!existsSync(path)) {
          throw new Error(`file not found: ${path}`);
        }
      }
      const modules = loadAnydataModules({
        hostPath: resolve(yangFile),
        hostModule: module,
        includePaths,
        extraModulePaths: anydataModulePaths,
        parseOpts
      });
      if (modules.length < 2 && anydataModulePaths.length === 0) {
        process.stderr.write(
          "Warning: --anydata-validation enabled but no extra modules were loaded; " +
            "use --include-path or --anydata-module\n"
        );
      }
      const mode =
        anydataValidation === "complete"
          ? AnydataValidationMode.COMPLETE
          : AnydataValidationMode.CANDIDATE;
      validator.enableExtension(ValidatorExtension.ANYDATA_VALIDATION, { modules, mode });
    }

    let data: unknown;
    if (positional[1]) {
      const dataPath = positional[1];
      if (!existsSync(dataPath)) {
        throw new Error(`file not found: ${dataPath}`);
      }
      data = JSON.parse(readFileSync(dataPath, "utf-8"));
    } else {
      data = JSON.parse(readFileSync(0, "utf-8"));
    }
    if (module.name) {
      data = normalizeRfc7951InstanceRoot(data, module.name);
    }

    const result = validator.validate(data);
    if (result.warnings?.length) {
      for (const line of result.warnings) {
        process.stderr.write(`Warning: ${line}\n`);
      }
    }
    if (!result.isValid) {
      process.stderr.write("Validation failed:\n");
      for (const line of result.errors) {
        process.stderr.write(`  ${line}\n`);
      }
      return 1;
    }
    process.stdout.write("Valid.\n");
    return 0;
  }

  if (command === "convert") {
    const { includePaths, positional } = parseCommonArgs(rest);
    const file = positional[0];
    if (!file) {
      throw new Error("Missing <file.yang>");
    }
    const module = new YangParser({ expand_uses: false, include_path: includePaths }).parseFile(file);
    const schema = generateJsonSchema(module);
    process.stdout.write(`${JSON.stringify(schema, null, 2)}\n`);
    return 0;
  }

  throw new Error(`Unknown command: ${command}`);
}

/**
 * Exit only after stdout and stderr have been handed to the OS.
 *
 * `process.stdout.write` of a large JSON Schema fills the pipe buffer and
 * returns while the rest sits in the stream (Node's pipe highWaterMark is
 * 64 KiB). `process.exit` right after that drops the tail, so piped
 * `convert` output is truncated. `stream.end` runs its callback once that
 * buffer has been written.
 *
 * The QuickJS process shim writes with synchronous stdio and does not
 * implement stream `.end()`. `process.exit` there flushes and sets the
 * static binary's status.
 */
function finish(code: number): void {
  const streams = [process.stdout, process.stderr].filter((stream) => typeof stream.end === "function");
  if (streams.length === 0) {
    process.exit(code);
    return;
  }

  let pending = streams.length;
  let exited = false;
  const exit = (): void => {
    if (exited) {
      return;
    }
    exited = true;
    process.exit(code);
  };

  for (const stream of streams) {
    let settled = false;
    const done = (): void => {
      if (settled) {
        return;
      }
      settled = true;
      pending -= 1;
      if (pending === 0) {
        exit();
      }
    };
    stream.once("error", done);
    stream.end(done);
  }
}

try {
  finish(main(process.argv));
} catch (error) {
  process.stderr.write(`${(error as Error).message}\n`);
  finish(1);
}
