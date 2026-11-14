import { typeStatementKind, type TypeStatementKind } from "../types/registry";
/**
 * Runtime model. `YangModule` and `YangStatement` are the only representation.
 * Fields are read on the objects (`statement.if_features`, `module.import_prefixes`,
 * `module.yangVersion`). There is no `.data` bag and no `__class__` dict layer.
 */

import type { YangIdentifierRef } from "./identifier-ref";

export type ModuleSource = {
  kind: "file" | "string";
  value: string;
  name?: string;
};

export type WhenShape = {
  expression?: string;
  description?: string;
  evaluate_with_parent_context?: boolean;
  /** Module each prefixed step in `expression` is bound to, by prefix. */
  xpath_prefixes?: Record<string, string>;
};

/** Sparse input accepted by constructors; runtime output is discriminated by family. */
export type StatementTypeInput = Record<string, unknown> & { name?: string };
type TypeIdentity = {
  name: string;
  prefix?: string;
  scope_module?: string;
  context?: string;
  units?: string;
};
type RangeRestrictionShape = {
  range?: string; range_error_message?: string; range_error_app_tag?: string;
  range_description?: string; range_reference?: string;
};
type LengthRestrictionShape = {
  length?: string; length_error_message?: string; length_error_app_tag?: string;
  length_description?: string; length_reference?: string;
};
export type PatternShape = { pattern: string; invert_match?: boolean; error_message?: string; error_app_tag?: string };
type PatternRestrictions = { patterns?: PatternShape[]; pattern?: string };
export type StatementTypeShape = TypeIdentity & (
  | { kind: "plain" }
  | ({ kind: "numeric" } & RangeRestrictionShape)
  | ({ kind: "decimal"; fraction_digits?: number } & RangeRestrictionShape)
  | ({ kind: "string" } & LengthRestrictionShape & PatternRestrictions)
  | ({ kind: "binary" } & LengthRestrictionShape)
  | { kind: "enumeration"; enums?: string[] }
  | { kind: "bits"; bits?: unknown }
  | { kind: "union"; types?: StatementTypeShape[] }
  | { kind: "leafref"; path?: unknown; xpath_prefixes?: Record<string, string>; require_instance?: boolean }
  | { kind: "instance-identifier"; require_instance?: boolean }
  | { kind: "identityref"; identityref_bases?: unknown }
  | ({ kind: "derived"; enums?: string[]; bits?: unknown; require_instance?: boolean } & RangeRestrictionShape & LengthRestrictionShape & PatternRestrictions)
);

const RANGE_FIELDS = ["range", "range_error_message", "range_error_app_tag", "range_description", "range_reference"];
const LENGTH_FIELDS = ["length", "length_error_message", "length_error_app_tag", "length_description", "length_reference"];
const TYPE_FIELDS: Record<TypeStatementKind, readonly string[]> = {
  plain: [], numeric: RANGE_FIELDS, decimal: [...RANGE_FIELDS, "fraction_digits"],
  string: [...LENGTH_FIELDS, "patterns", "pattern"], binary: LENGTH_FIELDS,
  enumeration: ["enums"], bits: ["bits"], union: ["types"],
  leafref: ["path", "xpath_prefixes", "require_instance"],
  "instance-identifier": ["require_instance"], identityref: ["identityref_bases"],
  derived: [...RANGE_FIELDS, ...LENGTH_FIELDS, "patterns", "pattern", "enums", "bits", "require_instance"]
};
const COMMON_TYPE_FIELDS = new Set(["name", "prefix", "scope_module", "context", "units"]);

export function normalizeTypeShape(input: StatementTypeInput): StatementTypeShape {
  const name = input.name ?? "";
  const kind = typeStatementKind(name, typeof input.prefix === "string" ? input.prefix : undefined);
  const output: Record<string, unknown> = { kind, name };
  const fields = TYPE_FIELDS[kind];
  for (const [key, value] of Object.entries(input)) {
    if (key === "kind" || value === undefined) continue;
    if (!COMMON_TYPE_FIELDS.has(key) && !fields.includes(key)) {
      throw new TypeError(`Attribute '${key}' does not belong to type '${name}' (${kind})`);
    }
    output[key] = key === "types" && Array.isArray(value)
      ? value.map((member) => normalizeTypeShape(member as StatementTypeInput)) : value;
  }
  return output as StatementTypeShape;
}

export type IdentityBases = {
  bases: Array<{ prefix?: string; name: string }>;
  description?: string;
  if_features?: string[];
  /** Extension invocations on this identity. Present after a native JSON reload. */
  statements?: YangStatement[];
};

interface YangStatementFields {
  keyword?: string;
  name?: string;
  argument?: string;
  description?: string;
  reference?: string;
  units?: string;
  mandatory?: boolean;
  default?: unknown;
  defaults?: unknown[];
  key?: string;
  unique?: string[][];
  min_elements?: number;
  max_elements?: number;
  config?: boolean;
  if_features?: string[];
  when?: WhenShape;
  presence?: string;
  error_message?: string;
  error_app_tag?: string;
  /** Module each prefixed step in a `must` expression is bound to, by prefix. */
  xpath_prefixes?: Record<string, string>;
  grouping_name?: string;
  grouping_prefix?: string;
  path?: string;
  augment_path?: string;
  augment_path_segments?: YangIdentifierRef[];
  argument_name?: string;
  argument_yin_element?: boolean;
  prefix?: string;
  resolved_module_name?: string;
  resolved_extension_name?: string;
  deviation_path?: string;
  deviation_path_segments?: YangIdentifierRef[];
  not_supported?: boolean;
  defining_module?: string;
  data_node_kind?: string;
  refine_target_path?: string;
  refined_mandatory?: boolean;
  refined_defaults?: unknown[];
  refined_config?: boolean;
  allOf?: unknown;
}

/** Constructor input permits plain child objects and unnormalized types. */
export type YangStatementInit = YangStatementFields & {
  local_groupings?: Record<string, YangStatement | YangStatementInit>;
  statements?: Array<YangStatement | YangStatementInit>;
  type?: StatementTypeInput;
  refines?: Array<YangStatement | YangStatementInit>;
  augmentations?: Array<YangStatement | YangStatementInit>;
};

const STATEMENT_LIST_KEYS = new Set(["statements", "refines", "augmentations", "local_groupings"]);

function isStatementInit(value: unknown): value is YangStatementInit {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

// Declaration merging shares the common fields without emitting unused properties.
export interface YangStatement extends YangStatementFields {}

export class YangStatement {
  declare local_groupings?: Record<string, YangStatement>;
  statements: YangStatement[] = [];
  declare type?: StatementTypeShape;
  declare refines?: YangStatement[];
  declare augmentations?: YangStatement[];

  constructor(init: YangStatementInit = {}) {
    const raw = init as Record<string, unknown>;
    for (const key of Object.keys(raw)) {
      if (key === "__class__" || key === "type" || STATEMENT_LIST_KEYS.has(key)) {
        continue;
      }
      (this as Record<string, unknown>)[key] = raw[key];
    }
    this.statements = statementList(init.statements);
    if (init.type) this.type = normalizeTypeShape(init.type);
    if (Array.isArray(init.refines)) {
      this.refines = statementList(init.refines);
    }
    if (Array.isArray(init.augmentations)) {
      this.augmentations = statementList(init.augmentations);
    }
    if (init.local_groupings && typeof init.local_groupings === "object") {
      const local: Record<string, YangStatement> = {};
      for (const [key, value] of Object.entries(init.local_groupings)) {
        local[key] = value instanceof YangStatement ? value : new YangStatement(value);
      }
      this.local_groupings = local;
    }
  }

  findStatement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }
}

function statementList(value: Array<YangStatement | YangStatementInit> | undefined): YangStatement[] {
  if (!Array.isArray(value)) {
    return [];
  }
  // Keep the caller's array when it already holds statement objects. Producers
  // pass that array into the constructor and then push into it.
  if (value.every((item) => item instanceof YangStatement)) {
    return value as YangStatement[];
  }
  return value.map((item) => {
    if (item instanceof YangStatement) {
      return item;
    }
    if (!isStatementInit(item)) {
      throw new TypeError("Expected a YANG statement");
    }
    return new YangStatement(item);
  });
}

export type ModuleInit = {
  name?: string;
  yang_version?: string;
  namespace?: string;
  prefix?: string;
  organization?: string;
  contact?: string;
  description?: string;
  typedefs?: Record<string, unknown>;
  identities?: Record<string, IdentityBases>;
  import_prefixes?: Record<string, YangModule>;
  extensions?: Record<string, unknown>;
  extension_runtime?: Record<string, unknown>;
  features?: Set<string> | string[];
  feature_if_features?: Record<string, string[]>;
  groupings?: Record<string, YangStatement | YangStatementInit>;
  statements?: Array<YangStatement | YangStatementInit>;
};

function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export class YangModule {
  name?: string;
  /** YANG `yang-version` argument. The camelCase accessor is {@link yangVersion}. */
  yang_version?: string;
  namespace?: string;
  prefix?: string;
  organization?: string;
  contact?: string;
  description?: string;
  typedefs: Record<string, unknown> = {};
  identities: Record<string, IdentityBases> = {};
  /** Prefix → imported module. The same object the parser cached for that file. */
  import_prefixes: Record<string, YangModule> = {};
  extensions: Record<string, unknown> = {};
  extension_runtime: Record<string, unknown> = {};
  features: Set<string> = new Set();
  feature_if_features: Record<string, string[]> = {};
  groupings: Record<string, YangStatement> = {};
  statements: YangStatement[] = [];
  readonly source: ModuleSource;
  /**
   * Modules loaded by the parser that loaded this one, by name. A `type` written in another module
   * (`scope_module`) resolves there. Not enumerable, so module copies and JSON dumps skip it.
   */
  declare readonly module_registry?: Record<string, YangModule>;

  constructor(init: ModuleInit, source: ModuleSource) {
    this.source = source;
    this.name = typeof init.name === "string" ? init.name : undefined;
    this.yang_version = typeof init.yang_version === "string" ? init.yang_version : undefined;
    this.namespace = typeof init.namespace === "string" ? init.namespace : undefined;
    this.prefix = typeof init.prefix === "string" ? init.prefix : undefined;
    this.organization = nonEmpty(init.organization);
    this.contact = nonEmpty(init.contact);
    this.description = typeof init.description === "string" ? init.description : undefined;
    this.typedefs = init.typedefs ?? {};
    this.identities = init.identities ?? {};
    this.import_prefixes = init.import_prefixes ?? {};
    this.extensions = init.extensions ?? {};
    this.extension_runtime = init.extension_runtime ?? {};
    this.features =
      init.features instanceof Set
        ? init.features
        : new Set(Array.isArray(init.features) ? init.features : []);
    this.feature_if_features = init.feature_if_features ?? {};
    this.statements = statementList(init.statements);
    const groupings: Record<string, YangStatement> = {};
    for (const [key, value] of Object.entries(init.groupings ?? {})) {
      groupings[key] = value instanceof YangStatement ? value : new YangStatement(value);
    }
    this.groupings = groupings;
  }

  get yangVersion(): string | undefined {
    return this.yang_version;
  }

  findStatement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }
}
