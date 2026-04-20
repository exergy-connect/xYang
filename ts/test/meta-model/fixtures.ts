import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse as parseYaml } from "yaml";
import { parseYangFile, type YangModule } from "../../src";

const DEFAULT_VERSION = "26.03.29.1";

export const repoRoot = resolve(__dirname, "..", "..", "..");
export const metaModelYangPath = resolve(repoRoot, "examples/meta-model.yang");

export function loadMetaModel(): YangModule {
  return parseYangFile(metaModelYangPath);
}

export function loadYamlDataModel(relativeToRepo: string): Record<string, unknown> {
  const path = resolve(repoRoot, relativeToRepo);
  const tree = parseYaml(readFileSync(path, "utf-8"));
  if (!tree || typeof tree !== "object" || Array.isArray(tree)) {
    throw new Error(`YAML root must be a mapping: ${path}`);
  }
  return { "data-model": tree as Record<string, unknown> };
}

export function dm(kwargs: Record<string, unknown>): Record<string, unknown> {
  const name = (kwargs.name as string | undefined) ?? "M";
  const version = (kwargs.version as string | undefined) ?? DEFAULT_VERSION;
  const author = (kwargs.author as string | undefined) ?? "A";
  const description = (kwargs.description as string | undefined) ?? "Test data model.";
  const rest = { ...kwargs };
  delete rest.name;
  delete rest.version;
  delete rest.author;
  delete rest.description;
  return {
    "data-model": {
      name,
      version,
      author,
      description,
      ...rest
    }
  };
}

export function ent(
  name: string,
  primaryKey: string,
  fields: unknown[],
  extra: Record<string, unknown> = {}
): Record<string, unknown> {
  const description = (extra.description as string | undefined) ?? `Entity ${name}.`;
  return { name, primary_key: primaryKey, fields, description, ...extra };
}

export function fp(
  name: string,
  primitive: string,
  opts: Record<string, unknown> = {}
): Record<string, unknown> {
  const {
    description = `Field ${name}.`,
    minDate,
    maxDate,
    foreignKeys,
    ...fieldTop
  } = opts;
  const t: Record<string, unknown> = { primitive };
  if (minDate !== undefined) t.minDate = minDate;
  if (maxDate !== undefined) t.maxDate = maxDate;
  if (foreignKeys !== undefined) t.foreignKeys = foreignKeys;
  return { name, description, type: t, ...fieldTop };
}

export function fArrayEntity(name: string, entity: string, opts: Record<string, unknown> = {}): Record<string, unknown> {
  const description = (opts.description as string | undefined) ?? `Field ${name}.`;
  const rest = { ...opts };
  delete rest.description;
  return { name, description, type: { array: { entity } }, ...rest };
}

export function subf(name: string, primitive: string, opts: Record<string, unknown> = {}): Record<string, unknown> {
  const description = (opts.description as string | undefined) ?? `Subfield ${name}.`;
  const rest = { ...opts };
  delete rest.description;
  return { name, description, type: { primitive }, ...rest };
}

export function fComposite(
  name: string,
  components: unknown[],
  opts: Record<string, unknown> = {}
): Record<string, unknown> {
  const description = (opts.description as string | undefined) ?? `Field ${name}.`;
  const rest = { ...opts };
  delete rest.description;
  return { name, description, type: { composite: components }, ...rest };
}

export function fComputed(
  name: string,
  primitive: string,
  operation: string,
  fields: unknown[],
  opts: Record<string, unknown> = {}
): Record<string, unknown> {
  const description = (opts.description as string | undefined) ?? `Field ${name}.`;
  const rest = { ...opts };
  delete rest.description;
  return {
    name,
    description,
    type: { primitive },
    computed: { operation, fields },
    ...rest
  };
}
