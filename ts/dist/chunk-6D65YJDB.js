#!/usr/bin/env node

// src/encoding/rfc7951.ts
function resolveQualifiedTopLevel(jsonKey, modules) {
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

export {
  resolveQualifiedTopLevel
};
//# sourceMappingURL=chunk-6D65YJDB.js.map