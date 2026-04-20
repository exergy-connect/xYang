import { YangModule } from "../core/model";

export function resolveQualifiedTopLevel(
  jsonKey: string,
  modules: Record<string, YangModule>
): { statementName: string | null; moduleName: string | null } {
  if (!jsonKey.includes(":")) {
    return { statementName: null, moduleName: null };
  }

  const [moduleQualifier, statementName] = jsonKey.split(":", 2);
  if (!moduleQualifier || !statementName) {
    return { statementName: null, moduleName: null };
  }

  const mod = modules[moduleQualifier];
  if (!mod) {
    return { statementName: null, moduleName: null };
  }
  if (!mod.findStatement(statementName)) {
    return { statementName: null, moduleName: null };
  }

  return { statementName, moduleName: moduleQualifier };
}
