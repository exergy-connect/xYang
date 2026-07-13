type ModuleSource = {
    kind: "file" | "string";
    value: string;
    name?: string;
};
type SerializedStatement = {
    __class__?: string;
    name?: string;
    keyword?: string;
    argument?: string;
    description?: string;
    statements?: SerializedStatement[];
    type?: Record<string, unknown>;
    [key: string]: unknown;
};
declare class YangStatement {
    readonly data: SerializedStatement;
    constructor(data: SerializedStatement);
    get name(): string | undefined;
    get keyword(): string | undefined;
    get argument(): string | undefined;
    get statements(): YangStatement[];
    findStatement(name: string): YangStatement | undefined;
}
declare class YangModule {
    readonly data: Record<string, unknown>;
    readonly source: ModuleSource;
    constructor(data: Record<string, unknown>, source: ModuleSource);
    get name(): string | undefined;
    get yangVersion(): string | undefined;
    get namespace(): string | undefined;
    get prefix(): string | undefined;
    get organization(): string | undefined;
    get contact(): string | undefined;
    /** First module-level ``description`` substatement (RFC 7950). */
    get description(): string | undefined;
    get typedefs(): Record<string, unknown>;
    /** Identity names → `{ bases }` from parsed `identity` / `base` statements (RFC 7950). */
    get identities(): Record<string, {
        bases: string[];
    }>;
    get statements(): YangStatement[];
    findStatement(name: string): YangStatement | undefined;
}

export { YangModule as Y, YangStatement as a };
