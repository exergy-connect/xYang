import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";
import { parseYangFile, YangParser } from "./parser";
import { YangValidator } from "./validator/yang-validator";
import { generateJsonSchema } from "./json";

function printUsage(): void {
  process.stdout.write(
    [
      "xyang-ts commands:",
      "  parse [--include-path DIR]... <file.yang>",
      "  validate [--include-path DIR]... <file.yang> [data.json]",
      "  convert [--include-path DIR]... <file.yang>"
    ].join("\n") + "\n"
  );
}

function parseCommonArgs(rest: string[]): { includePaths: string[]; positional: string[] } {
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

function main(argv: string[]): number {
  const [, , command, ...rest] = argv;
  if (!command) {
    printUsage();
    return 0;
  }

  const { includePaths, positional } = parseCommonArgs(rest);
  const parseOpts = includePaths.length > 0 ? { includePath: includePaths } : {};

  if (command === "parse") {
    const file = positional[0];
    if (!file) {
      throw new Error("Missing <file.yang>");
    }
    const module = parseYangFile(file, parseOpts);
    process.stdout.write(`${module.name}\n`);
    return 0;
  }

  if (command === "validate") {
    const yangFile = positional[0];
    if (!yangFile) {
      throw new Error("Missing <file.yang>");
    }
    const module = parseYangFile(yangFile, parseOpts);
    const validator = new YangValidator(module);
    let data: unknown = JSON.parse(readFileSync(0, "utf-8"));
    if (positional[1]) {
      data = JSON.parse(readFileSync(positional[1], "utf-8"));
    }
    const result = validator.validate(data);
    if (!result.isValid) {
      for (const line of result.errors) {
        process.stderr.write(`${line}\n`);
      }
      return 1;
    }
    process.stdout.write("Valid.\n");
    return 0;
  }

  if (command === "convert") {
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

try {
  process.exit(main(process.argv));
} catch (error) {
  process.stderr.write(`${(error as Error).message}\n`);
  process.exit(1);
}
