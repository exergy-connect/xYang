import { YangModule } from "../core/model";
import { YangParser } from "./yang-parser";

const defaultParser = new YangParser();

export { YangParser };

export type ParseYangFileOptions = {
  includePath?: string[];
  expandUses?: boolean;
};

export function parseYangString(content: string): YangModule {
  return defaultParser.parseString(content);
}

export function parseYangFile(path: string, options: ParseYangFileOptions = {}): YangModule {
  if (options.includePath?.length || options.expandUses === false) {
    const parser = new YangParser({
      include_path: options.includePath,
      expand_uses: options.expandUses
    });
    return parser.parseFile(path);
  }
  return defaultParser.parseFile(path);
}
