#!/usr/bin/env node
import {
  YangParser,
  YangValidator,
  generateJsonSchema,
  parseYangFile
} from "./chunk-FNPPHT3N.js";
import "./chunk-6D65YJDB.js";
import "./chunk-JVFM24VE.js";

// src/cli.ts
import { existsSync as existsSync2, readFileSync } from "fs";
import { resolve as resolve3 } from "path";
import process from "process";

// src/cli/args.ts
import { resolve } from "path";
function parseCommonArgs(rest) {
  const includePaths = [];
  const positional = [];
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
    positional.push(arg);
  }
  return { includePaths, positional };
}
function parseValidateArgs(rest) {
  const includePaths = [];
  const anydataModulePaths = [];
  const positional = [];
  let anydataValidation = "off";
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
    positional.push(arg);
  }
  return { includePaths, positional, anydataValidation, anydataModulePaths };
}

// src/cli/load-anydata-modules.ts
import { existsSync, readdirSync } from "fs";
import { dirname, resolve as resolve2 } from "path";
function yangFilesInDirs(dirs) {
  const seen = /* @__PURE__ */ new Set();
  const out = [];
  for (const dir of dirs) {
    if (!existsSync(dir)) {
      continue;
    }
    for (const name of readdirSync(dir)) {
      if (!name.endsWith(".yang")) {
        continue;
      }
      const path = resolve2(dir, name);
      if (!seen.has(path)) {
        seen.add(path);
        out.push(path);
      }
    }
  }
  out.sort();
  return out;
}
function registerModuleClosure(modules, mod) {
  const name = mod.name;
  if (!name) {
    return;
  }
  modules.set(name, mod);
  const imports = mod.data.import_prefixes ?? {};
  for (const imported of Object.values(imports)) {
    registerModuleClosure(modules, imported);
  }
}
function loadAnydataModules(options) {
  const { hostPath, hostModule, includePaths, extraModulePaths, parseOpts = {} } = options;
  const modules = /* @__PURE__ */ new Map();
  registerModuleClosure(modules, hostModule);
  const hostResolved = resolve2(hostPath);
  const paths = extraModulePaths.length > 0 ? extraModulePaths : yangFilesInDirs([dirname(hostResolved), ...includePaths]);
  const parser = new YangParser({
    include_path: includePaths,
    expand_uses: parseOpts.expandUses ?? true
  });
  for (const yangPath of paths) {
    if (resolve2(yangPath) === hostResolved) {
      continue;
    }
    try {
      const mod = parser.parseFile(yangPath);
      registerModuleClosure(modules, mod);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`Warning: skipping ${yangPath}: ${message}`);
    }
  }
  return [...modules.values()];
}
function normalizeRfc7951InstanceRoot(data, moduleName) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return data;
  }
  const root = data;
  const keys = Object.keys(root);
  if (keys.length !== 1 || !keys[0].includes(":")) {
    return data;
  }
  const [mod, local] = keys[0].split(":", 2);
  if (mod === moduleName && local) {
    return { [local]: root[keys[0]] };
  }
  return data;
}

// src/cli.ts
function printUsage() {
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
function main(argv) {
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
    process.stdout.write(`${module.name}
`);
    return 0;
  }
  if (command === "validate") {
    const { includePaths, positional, anydataValidation, anydataModulePaths } = parseValidateArgs(rest);
    const yangFile = positional[0];
    if (!yangFile) {
      throw new Error("Missing <file.yang>");
    }
    if (!existsSync2(yangFile)) {
      throw new Error(`file not found: ${yangFile}`);
    }
    const parseOpts = includePaths.length > 0 ? { includePath: includePaths } : {};
    const module = parseYangFile(yangFile, parseOpts);
    const validator = new YangValidator(module);
    if (anydataValidation !== "off") {
      for (const path of anydataModulePaths) {
        if (!existsSync2(path)) {
          throw new Error(`file not found: ${path}`);
        }
      }
      const modules = loadAnydataModules({
        hostPath: resolve3(yangFile),
        hostModule: module,
        includePaths,
        extraModulePaths: anydataModulePaths,
        parseOpts
      });
      if (modules.length < 2 && anydataModulePaths.length === 0) {
        process.stderr.write(
          "Warning: --anydata-validation enabled but no extra modules were loaded; use --include-path or --anydata-module\n"
        );
      }
      const mode = anydataValidation === "complete" ? "complete" /* COMPLETE */ : "candidate" /* CANDIDATE */;
      validator.enableExtension("anydata_validation" /* ANYDATA_VALIDATION */, { modules, mode });
    }
    let data;
    if (positional[1]) {
      const dataPath = positional[1];
      if (!existsSync2(dataPath)) {
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
        process.stderr.write(`Warning: ${line}
`);
      }
    }
    if (!result.isValid) {
      process.stderr.write("Validation failed:\n");
      for (const line of result.errors) {
        process.stderr.write(`  ${line}
`);
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
    process.stdout.write(`${JSON.stringify(schema, null, 2)}
`);
    return 0;
  }
  throw new Error(`Unknown command: ${command}`);
}
try {
  process.exit(main(process.argv));
} catch (error) {
  process.stderr.write(`${error.message}
`);
  process.exit(1);
}
//# sourceMappingURL=cli.js.map