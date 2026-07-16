import { existsSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { YangModule } from "../core/model";
import { YangParser, type ParseYangFileOptions } from "../parser";
import {
  applyAugmentationsAcrossModuleMap,
  registerModuleClosure
} from "../transform/augment-expand";

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

export type LoadAnydataModulesOptions = {
  hostPath: string;
  hostModule: YangModule;
  includePaths: string[];
  extraModulePaths: string[];
  parseOpts?: ParseYangFileOptions;
};

/**
 * Build the module set for anydata subtree validation (parity with Python
 * ``_load_anydata_module_map``). Uses one parser cache so cross-file ``augment``
 * merges into shared imported module data; runs a final across-map pass for any
 * remaining top-level ``augment`` statements.
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

  applyAugmentationsAcrossModuleMap(modules);
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
