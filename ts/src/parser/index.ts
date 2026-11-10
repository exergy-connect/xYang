import { dirname } from "node:path";
import { YangModule } from "../core/model";
import { YangParser } from "./yang-parser";

export { YangParser };

export type ParseYangFileOptions = {
  includePath?: string[];
  expandUses?: boolean;
};

export type ParseYangStringOptions = {
  filename?: string;
  sourcePath?: string;
  includePath?: string[];
  expandUses?: boolean;
};

/**
 * Parse YANG source text with a fresh parser.
 *
 * Imports resolve against `dirname(sourcePath)` when `sourcePath` is set, then
 * `includePath`.
 */
export function parseYangString(content: string, options: ParseYangStringOptions = {}): YangModule {
  const parser = new YangParser({
    includePath: options.includePath,
    expandUses: options.expandUses
  });
  const sourceDir = options.sourcePath ? dirname(options.sourcePath) : undefined;
  return parser.parseString(content, options.filename ?? "<memory>", sourceDir);
}

/** Parse a YANG file with a fresh parser. Imports inside that parse are still cached. */
export function parseYangFile(path: string, options: ParseYangFileOptions = {}): YangModule {
  const parser = new YangParser({
    includePath: options.includePath,
    expandUses: options.expandUses
  });
  return parser.parseFile(path);
}
