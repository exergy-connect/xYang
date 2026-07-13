import { Y as YangModule } from './model-C9I603Qs.js';
export { a as YangStatement } from './model-C9I603Qs.js';

type ParserOptions = {
    expand_uses?: boolean;
    include_path?: string[];
};
declare class YangParser {
    readonly expandUses: boolean;
    readonly includePath: string[];
    private readonly moduleCache;
    private readonly tokenizer;
    private readonly parsers;
    constructor(options?: ParserOptions);
    /** Resolve `import` like Python `YangParser._resolve_submodule_path` (revision file, then basename, then last `name@*.yang`). */
    private resolveImportedModulePath;
    private resolveImport;
    private parseTokenStream;
    parseString(content: string, sourceName?: string): YangModule;
    parseFile(path: string): YangModule;
}

type ParseYangFileOptions = {
    includePath?: string[];
    expandUses?: boolean;
};
declare function parseYangString(content: string): YangModule;
declare function parseYangFile(path: string, options?: ParseYangFileOptions): YangModule;

/**
 * Optional anydata subtree validation modes from
 * [draft-ietf-netmod-yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation) §5
 * (anydata-complete / anydata-candidate, aligned with RFC 7950 §8.3.3 datastore semantics).
 */
declare enum AnydataValidationMode {
    /** Full RFC 7950 validation for resolved subtree members (anydata-complete). */
    COMPLETE = "complete",
    /** Structural validation without constraint checks: no type, must, when, etc. (anydata-candidate). */
    CANDIDATE = "candidate"
}
type AnydataValidationConfig = {
    modules: YangModule[];
    mode: AnydataValidationMode;
};
/** Arguments for the anydata-validation extension (RFC 7951 module set for subtree resolution). */
type AnydataValidationConfigInput = {
    modules: readonly YangModule[];
    mode?: AnydataValidationMode;
};
/**
 * Validates arguments for the anydata-validation validator extension (parity with
 * Python `parse_anydata_extension_kwargs`).
 */
declare function parseAnydataExtensionConfig(config: AnydataValidationConfigInput): AnydataValidationConfig;

declare enum ValidatorExtension {
    ANYDATA_VALIDATION = "anydata_validation"
}

/**
 * YANG 1.1 if-feature boolean expressions (RFC 7950 §7.20.2, §14).
 * Multiple if-feature substatements on one node are combined with logical AND.
 */
type ModuleData = Record<string, unknown>;
declare function reachableModuleData(root: ModuleData): ModuleData[];
declare function evaluateIfFeatureExpression(expr: string, ctxModule: ModuleData, enabledByModule: Readonly<Record<string, ReadonlySet<string>>>): boolean;
declare function stmtIfFeaturesSatisfied(ifFeatures: string[] | undefined, ctxModule: ModuleData, enabledByModule: Readonly<Record<string, ReadonlySet<string>>>): boolean;
/**
 * For each reachable module, the set of feature names that are enabled.
 * - override is null/undefined: every declared feature is enabled.
 * - override[moduleName] present: only those names are enabled for that module.
 * - Module not listed: all declared features enabled for that module.
 */
declare function buildEnabledFeaturesMap(root: ModuleData, override: ReadonlyMap<string, ReadonlySet<string>> | Record<string, ReadonlySet<string>> | null | undefined): Record<string, ReadonlySet<string>>;

type EnabledFeaturesByModule = Record<string, ReadonlySet<string>>;

type ValidationResult = {
    isValid: boolean;
    errors: string[];
    warnings: string[];
};
type YangValidatorOptions = {
    enabledFeaturesByModule?: EnabledFeaturesByModule;
    /** When true, this instance emits `console.debug` for leaf type validation. */
    typeValidationDebug?: boolean;
};
declare class YangValidator {
    private readonly module;
    private readonly documentValidator;
    constructor(module: YangModule, options?: YangValidatorOptions);
    /**
     * Toggle `console.debug` tracing for leaf type checks performed by this validator only.
     */
    setTypeValidationDebug(on: boolean): this;
    enableExtension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void;
    enable_extension(extension: ValidatorExtension, config: AnydataValidationConfigInput): void;
    validate(data: unknown): ValidationResult;
}

declare class YangError extends Error {
    constructor(message: string);
}
declare class YangSyntaxError extends SyntaxError {
    readonly messageText: string;
    readonly line_num?: number;
    readonly line?: string;
    readonly context_lines: Array<[number, string]>;
    readonly filename?: string;
    constructor(message: string, options?: {
        line_num?: number;
        line?: string;
        context_lines?: Array<[number, string]>;
        filename?: string;
    });
    private formatHeadline;
    toString(): string;
}
declare class YangSemanticError extends YangError {
    constructor(message: string);
}
declare class YangRefineTargetNotFoundError extends YangSemanticError {
    readonly target_path: string;
    constructor(target_path: string);
}
declare class YangCircularUsesError extends YangSemanticError {
    readonly prefix_chain: readonly string[];
    readonly repeated: string;
    constructor(prefix_chain: readonly string[], repeated: string);
}

declare function generateJsonSchema(module: YangModule): Record<string, unknown>;

/**
 * Build a {@link YangModule} (serialized AST in `module.data`) from JSON Schema with `x-yang` annotations,
 * as produced by {@link generateJsonSchema}. Covers common data nodes used in tests; extend as needed for parity.
 */
declare function parseJsonSchema(source: string | Record<string, unknown>): YangModule;

export { type AnydataValidationConfigInput, type ModuleData, ValidatorExtension, YangCircularUsesError, YangModule, YangParser, YangRefineTargetNotFoundError, YangSemanticError, YangSyntaxError, YangValidator, type YangValidatorOptions, buildEnabledFeaturesMap, evaluateIfFeatureExpression, generateJsonSchema, parseAnydataExtensionConfig, parseJsonSchema, parseYangFile, parseYangString, reachableModuleData, stmtIfFeaturesSatisfied };
