import { YangModule } from "../core/model";
import { YangParser } from "./yang-parser";

const defaultParser = new YangParser();

export function parseYangString(content: string): YangModule {
  return defaultParser.parseString(content);
}

export function parseYangFile(path: string): YangModule {
  return defaultParser.parseFile(path);
}
