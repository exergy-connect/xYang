import type {
  YangExtensionStmt,
  YangIdentityStmt,
  YangStatement,
  YangTypedefStmt
} from "./ast";
import { YangStatementList } from "./ast";

export class YangModule extends YangStatementList {
  name = "";
  yang_version = "1.1";
  namespace = "";
  prefix = "";
  organization = "";
  contact = "";
  description = "";
  revisions: Array<Record<string, string>> = [];
  belongs_to_module = "";
  typedefs: Record<string, YangTypedefStmt> = {};
  identities: Record<string, YangIdentityStmt> = {};
  groupings: Record<string, YangStatement> = {};
  features: Set<string> = new Set();
  feature_if_features: Record<string, string[]> = {};
  import_prefixes: Record<string, YangModule> = {};
  extensions: Record<string, YangExtensionStmt> = {};
  extension_runtime: Record<string, unknown> = {};

  constructor(init: Partial<YangModule> = {}) {
    super(init.statements ?? []);
    Object.assign(this, init);
  }

  own_prefix_stripped(): string {
    return (this.prefix || "").replace(/^['\"]|['\"]$/g, "");
  }

  ownPrefixStripped(): string {
    return this.own_prefix_stripped();
  }

  resolve_prefixed_module(prefix: string): YangModule | undefined {
    if (prefix === this.own_prefix_stripped()) {
      return this;
    }
    return this.import_prefixes[prefix];
  }

  resolvePrefixedModule(prefix: string): YangModule | undefined {
    return this.resolve_prefixed_module(prefix);
  }

  get_typedef(name: string): YangTypedefStmt | undefined {
    return this.typedefs[name];
  }

  getTypedef(name: string): YangTypedefStmt | undefined {
    return this.get_typedef(name);
  }

  get_grouping(name: string): YangStatement | undefined {
    return this.groupings[name];
  }

  getGrouping(name: string): YangStatement | undefined {
    return this.get_grouping(name);
  }

  get_identity(name: string): YangIdentityStmt | undefined {
    return this.identities[name];
  }

  getIdentity(name: string): YangIdentityStmt | undefined {
    return this.get_identity(name);
  }

  get_extension(name: string): YangExtensionStmt | undefined {
    return this.extensions[name];
  }

  getExtension(name: string): YangExtensionStmt | undefined {
    return this.get_extension(name);
  }
}
