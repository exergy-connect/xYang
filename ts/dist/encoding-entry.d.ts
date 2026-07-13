import { Y as YangModule } from './model-C9I603Qs.js';

declare function resolveQualifiedTopLevel(jsonKey: string, modules: Record<string, YangModule>): {
    statementName: string | null;
    moduleName: string | null;
};

export { resolveQualifiedTopLevel };
