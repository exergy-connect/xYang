import { formatIdentifierRef, type YangIdentifierRef } from "../core/identifier-ref";
import { YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { TypeConstraint, TypeSystem, type TypeIssue } from "../types";
import { REGISTRY } from "../types/registry";
import { resolvePrefixedModule, type ModuleData } from "./if-feature-eval";
import { identityrefValueValid, resolveIdentityValue } from "../identity-graph";
import { summarizeValue, traceTypeValidation } from "./type-validation-debug";

export type TypeCheckerOptions = {
  typeValidationDebug?: boolean;
};

type TypedefShape = { type?: Record<string, unknown> };

function hasTypeRestrictions(constraint?: Record<string, unknown>): boolean {
  if (!constraint) {
    return false;
  }
  if (typeof constraint.range === "string" && constraint.range.trim() !== "") {
    return true;
  }
  if (typeof constraint.length === "string" && constraint.length.trim() !== "") {
    return true;
  }
  return Array.isArray(constraint.patterns) && constraint.patterns.length > 0;
}

function asTypeRef(name: string, constraint?: Record<string, unknown>): YangIdentifierRef {
  const prefix =
    constraint && typeof constraint.prefix === "string" && constraint.prefix
      ? constraint.prefix
      : undefined;
  return prefix ? { prefix, name } : { name };
}

/**
 * The typedef a derived `type` names, resolved in the module that wrote the `type` (`scope_module`,
 * RFC 7950 §7.13): its own prefix and imports, or its own typedefs for an unprefixed name. A `type`
 * without a scope (native JSON form) resolves in `host`. A scope module that was not loaded throws.
 */
export function resolveTypedef(
  host: YangModule,
  type: { name?: unknown; prefix?: unknown; scope_module?: unknown }
): TypedefShape | undefined {
  if (typeof type.name !== "string") return undefined;
  if (!type.prefix && Object.prototype.hasOwnProperty.call(REGISTRY, type.name)) return undefined;
  let scope: ModuleData = host as unknown as ModuleData;
  if (typeof type.scope_module === "string" && type.scope_module && type.scope_module !== host.name) {
    const loaded = host.module_registry?.[type.scope_module];
    if (!loaded) {
      throw new Error(`type '${type.name}' is written in module '${type.scope_module}', which is not loaded`);
    }
    scope = loaded as unknown as ModuleData;
  }
  const target = typeof type.prefix === "string" && type.prefix ? resolvePrefixedModule(scope, type.prefix) : scope;
  const typedef = (target?.typedefs as Record<string, TypedefShape> | undefined)?.[type.name];
  return typedef?.type && typeof typedef.type.name === "string" ? typedef : undefined;
}

export class TypeChecker {
  private readonly system = new TypeSystem();
  private readonly typeValidationDebug: boolean;

  constructor(
    private readonly module: YangModule,
    options: TypeCheckerOptions = {}
  ) {
    this.typeValidationDebug = options.typeValidationDebug === true;
  }

  /** Resolve a local or prefixed typedef where the `type` was written (see `resolveTypedef`). */
  private lookupTypedef(ref: YangIdentifierRef, constraint?: Record<string, unknown>): TypedefShape | undefined {
    const scope = typeof constraint?.scope_module === "string" ? constraint.scope_module : undefined;
    return resolveTypedef(this.module, { name: ref.name, prefix: ref.prefix, scope_module: scope });
  }

  /**
   * Follow a typedef chain to the underlying builtin type name (stops at unions or unknown).
   */
  resolveUnderlyingBuiltinName(typeName: string, constraint?: Record<string, unknown>): string {
    const seen = new Set<string>();
    let ref = asTypeRef(typeName, constraint);
    let shape = constraint;
    while (seen.size < 64) {
      const typedef = this.lookupTypedef(ref, shape);
      if (!typedef?.type || typeof typedef.type.name !== "string") {
        return ref.name;
      }
      if (typedef.type.name === YangTokenType.UNION) {
        return formatIdentifierRef(ref);
      }
      const key = formatIdentifierRef(ref);
      seen.add(key);
      const next = asTypeRef(typedef.type.name, typedef.type as Record<string, unknown>);
      if (formatIdentifierRef(next) === key) {
        return ref.name;
      }
      ref = next;
      shape = typedef.type as Record<string, unknown>;
    }
    return ref.name;
  }

  /** Every `(code, message)` issue. Empty means the value is valid. */
  validate(value: unknown, typeName: string, constraint?: Record<string, unknown>): TypeIssue[] {
    let via: "typedef" | "typedef-union" | "inline-union" | "direct";
    let result: TypeIssue[];

    const ref = asTypeRef(typeName, constraint);
    const typedef = this.lookupTypedef(ref, constraint);
    if (typedef?.type && typeof typedef.type.name === "string") {
      const typedefConstraint = new TypeConstraint(typedef.type as Record<string, unknown>);
      if (typedef.type.name === YangTokenType.UNION) {
        via = "typedef-union";
        result = this.validateUnion(value, typedefConstraint);
      } else if (this.lookupTypedef(asTypeRef(typedef.type.name, typedef.type as Record<string, unknown>), typedef.type as Record<string, unknown>)) {
        via = "typedef";
        result = this.validate(value, typedef.type.name, typedef.type as Record<string, unknown>);
      } else {
        via = "typedef";
        result = this.validateBuiltin(value, typedef.type.name, typedef.type as Record<string, unknown>, typedefConstraint);
      }
    } else {
      const merged = new TypeConstraint(constraint as Record<string, unknown> | undefined);
      if (typeName === YangTokenType.UNION && (merged.types?.length ?? 0) > 0) {
        via = "inline-union";
        result = this.validateUnion(value, merged);
      } else {
        via = "direct";
        result = this.validateBuiltin(value, typeName, constraint, merged);
      }
    }

    // A type that names a typedef may narrow it with its own range, length, or patterns.
    // Each level of the chain checks its own restrictions after the base accepts the value.
    if (result.length === 0 && via === "typedef" && hasTypeRestrictions(constraint)) {
      result = this.system.issues(
        value,
        this.resolveUnderlyingBuiltinName(typeName, constraint),
        new TypeConstraint(constraint)
      );
    }

    if (this.typeValidationDebug) {
      traceTypeValidation(true, "TypeChecker.validate", {
        module: this.module.name ?? "(anonymous)",
        typeName,
        via,
        ok: result.length === 0,
        reason: result.length === 0 ? null : result.map(([, message]) => message).join("; "),
        value: summarizeValue(value)
      });
    }
    return result;
  }

  private validateBuiltin(
    value: unknown,
    typeName: string,
    shape: Record<string, unknown> | undefined,
    constraint: TypeConstraint
  ): TypeIssue[] {
    if (typeName === YangTokenType.IDENTITYREF) {
      return this.checkIdentityref(value, shape ?? {});
    }
    return this.system.issues(value, typeName, constraint);
  }

  /** RFC 7951 §6.8 value, derived from every base (bases resolve in the host module, as in Python). */
  private checkIdentityref(value: unknown, shape: Record<string, unknown>): TypeIssue[] {
    if (typeof value !== "string") {
      return [[
        "identityref",
        `identityref value must be a string, got ${value === null ? "null" : typeof value}`
      ]];
    }
    const bases = Array.isArray(shape.identityref_bases) ? (shape.identityref_bases as YangIdentifierRef[]) : [];
    if (bases.length === 0) {
      return [["identityref", "identityref type has no base identities"]];
    }
    const moduleData = this.module;
    if (!resolveIdentityValue(moduleData, value)) {
      return [["identityref", `identityref value '${value}' does not resolve to a known identity`]];
    }
    if (!identityrefValueValid(moduleData, value, bases)) {
      const shown = bases.map((b) => `'${formatIdentifierRef(b)}'`).join(", ");
      return [["identityref", `identityref value '${value}' is not derived from all bases [${shown}]`]];
    }
    return [];
  }

  /** Union members may name typedefs; validate through this checker so typedefs resolve. */
  private validateUnion(value: unknown, constraint: TypeConstraint): TypeIssue[] {
    if (this.typeValidationDebug) {
      traceTypeValidation(true, "TypeChecker.validateUnion", {
        module: this.module.name ?? "(anonymous)",
        memberCount: constraint.types?.length ?? 0,
        value: summarizeValue(value)
      });
    }
    for (const member of constraint.types ?? []) {
      const memberObj = member as Record<string, unknown>;
      const memberName =
        typeof memberObj.name === "string" ? memberObj.name : YangTokenType.STRING_KW;
      if (this.validate(value, memberName, memberObj).length === 0) {
        return [];
      }
    }
    return [["union", "Value does not match any union member type"]];
  }
}
