import { YangModule, YangStatement } from "../core/model";

const STRUCTURE_INDEX = "ietf-yang-structure-ext:structure-index";

/** A one-member document for a registered RFC 8791 structure. Mirrors Python `resolve_structure_instance`. */
export function resolveStructureInstance(
  data: Record<string, unknown>,
  module: YangModule
): { schema: YangStatement; inner: Record<string, unknown>; key: string } | undefined {
  const keys = Object.keys(data);
  if (keys.length !== 1) {
    return undefined;
  }
  const key = keys[0]!;
  const inner = data[key];
  if (!inner || typeof inner !== "object" || Array.isArray(inner)) {
    return undefined;
  }
  let name = key;
  if (key.includes(":")) {
    const colon = key.indexOf(":");
    const owner = key.slice(0, colon);
    name = key.slice(colon + 1);
    if (!owner || !name || owner !== (module.name ?? "")) {
      return undefined;
    }
  }
  const index = module.extension_runtime?.[STRUCTURE_INDEX];
  if (!index || typeof index !== "object") {
    return undefined;
  }
  const schema = (index as Record<string, unknown>)[name];
  if (!(schema instanceof YangStatement)) {
    return undefined;
  }
  return { schema, inner: inner as Record<string, unknown>, key };
}

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
