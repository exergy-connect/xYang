export type ModuleSource = {
  kind: "file" | "string";
  value: string;
  name?: string;
};

export type SerializedStatement = {
  __class__?: string;
  name?: string;
  keyword?: string;
  argument?: string;
  description?: string;
  statements?: SerializedStatement[];
  type?: Record<string, unknown>;
  [key: string]: unknown;
};

function asStatement(data: unknown): YangStatement | undefined {
  if (!data || typeof data !== "object") {
    return undefined;
  }
  return new YangStatement(data as SerializedStatement);
}

export class YangStatement {
  readonly data: SerializedStatement;

  constructor(data: SerializedStatement) {
    this.data = data;
  }

  get name(): string | undefined {
    return this.data.name;
  }

  get keyword(): string | undefined {
    return this.data.keyword;
  }

  get argument(): string | undefined {
    return this.data.argument;
  }

  get statements(): YangStatement[] {
    const items = Array.isArray(this.data.statements) ? this.data.statements : [];
    return items.map((item) => new YangStatement(item));
  }

  findStatement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }
}

export class YangModule {
  readonly data: Record<string, unknown>;
  readonly source: ModuleSource;

  constructor(data: Record<string, unknown>, source: ModuleSource) {
    this.data = data;
    this.source = source;
  }

  get name(): string | undefined {
    return this.data.name as string | undefined;
  }

  get yangVersion(): string | undefined {
    return this.data.yang_version as string | undefined;
  }

  get namespace(): string | undefined {
    return this.data.namespace as string | undefined;
  }

  get prefix(): string | undefined {
    return this.data.prefix as string | undefined;
  }

  get organization(): string | undefined {
    const v = this.data.organization;
    return typeof v === "string" && v.length > 0 ? v : undefined;
  }

  get contact(): string | undefined {
    const v = this.data.contact;
    return typeof v === "string" && v.length > 0 ? v : undefined;
  }

  /** First module-level ``description`` substatement (RFC 7950). */
  get description(): string | undefined {
    const v = this.data.description;
    return typeof v === "string" ? v : undefined;
  }

  get typedefs(): Record<string, unknown> {
    return (this.data.typedefs as Record<string, unknown>) ?? {};
  }

  /** Identity names → `{ bases }` from parsed `identity` / `base` statements (RFC 7950). */
  get identities(): Record<string, { bases: string[] }> {
    const raw = this.data.identities;
    if (!raw || typeof raw !== "object") {
      return {};
    }
    return raw as Record<string, { bases: string[] }>;
  }

  get statements(): YangStatement[] {
    const raw = this.data.statements;
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw.map(asStatement).filter((stmt): stmt is YangStatement => Boolean(stmt));
  }

  findStatement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }
}
