#!/usr/bin/env node

import { readFileSync } from "node:fs";
import process from "node:process";
import { parseYangFile, parseYangString } from "./parser";
import { YangValidator } from "./validator/yang-validator";
import { generateJsonSchema } from "./json";

function printUsage(): void {
  process.stdout.write(
    [
      "xyang-ts commands:",
      "  parse <file.yang>",
      "  validate <file.yang> [data.json]",
      "  convert <file.yang>"
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
    const file = rest[0];
    if (!file) {
      throw new Error("Missing <file.yang>");
    }
    const module = parseYangFile(file);
    process.stdout.write(`${module.name}\n`);
    return 0;
  }

  if (command === "validate") {
    const yangFile = rest[0];
    if (!yangFile) {
      throw new Error("Missing <file.yang>");
    }
    const module = parseYangFile(yangFile);
    const validator = new YangValidator(module);
    let data: unknown = JSON.parse(readFileSync(0, "utf-8"));
    if (rest[1]) {
      data = JSON.parse(readFileSync(rest[1], "utf-8"));
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
    const file = rest[0];
    if (!file) {
      throw new Error("Missing <file.yang>");
    }
    const module = parseYangString(readFileSync(file, "utf-8"));
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
