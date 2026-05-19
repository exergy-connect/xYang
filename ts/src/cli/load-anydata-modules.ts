import { existsSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { YangModule } from "../core/model";
import { YangParser, type ParseYangFileOptions } from "../parser";

function yangFilesInDirs(dirs: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const dir of dirs) {
    if (!existsSync(dir)) {
      continue;
    }
    for (const name of readdirSync(dir)) {
      if (!name.endsWith(".yang")) {
        continue;
      }
      const path = resolve(dir, name);
      if (!seen.has(path)) {
        seen.add(path);
        out.push(path);
      }
    }
  }
  out.sort();
  return out;
}

function registerModuleClosure(modules: Map<string, YangModule>, mod: YangModule): void {
  const name = mod.name;
  if (!name) {
    return;
  }
  modules.set(name, mod);
  const imports =
    (mod.data.import_prefixes as Record<string, YangModule> | undefined) ?? {};
  for (const imported of Object.values(imports)) {
    registerModuleClosure(modules, imported);
  }
}

export type LoadAnydataModulesOptions = {
  hostPath: string;
  hostModule: YangModule;
  includePaths: string[];
  extraModulePaths: string[];
  parseOpts?: ParseYangFileOptions;
};

/**
 * Build the module set for anydata subtree validation (parity with Python
 * ``_load_anydata_module_map``; augment merging across modules is not applied yet).
 */
export function loadAnydataModules(options: LoadAnydataModulesOptions): YangModule[] {
  const { hostPath, hostModule, includePaths, extraModulePaths, parseOpts = {} } = options;
  const modules = new Map<string, YangModule>();
  registerModuleClosure(modules, hostModule);

  const hostResolved = resolve(hostPath);
  const paths =
    extraModulePaths.length > 0
      ? extraModulePaths
      : yangFilesInDirs([dirname(hostResolved), ...includePaths]);

  const parser = new YangParser({
    include_path: includePaths,
    expand_uses: parseOpts.expandUses ?? true
  });

  for (const yangPath of paths) {
    if (resolve(yangPath) === hostResolved) {
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

/** Unwrap a single RFC 7951 qualified top-level key when it names this module. */
export function normalizeRfc7951InstanceRoot(data: unknown, moduleName: string): unknown {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return data;
  }
  const root = data as Record<string, unknown>;
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
