import { formatIdentifierRef, type YangIdentifierRef } from "../core/identifier-ref";
import { YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { TypeConstraint, TypeSystem } from "../types";
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

export class TypeChecker {
  private readonly system = new TypeSystem();
  private readonly typeValidationDebug: boolean;

  constructor(
    private readonly module: YangModule,
    options: TypeCheckerOptions = {}
  ) {
    this.typeValidationDebug = options.typeValidationDebug === true;
  }

  /**
   * Resolve a local or prefixed typedef via the host module and its imports.
   */
  private lookupTypedef(ref: YangIdentifierRef): TypedefShape | undefined {
    if (ref.prefix) {
      const target = resolvePrefixedModule(this.module.data as ModuleData, ref.prefix);
      if (!target) {
        return undefined;
      }
      const imported = (target.typedefs as Record<string, TypedefShape> | undefined)?.[ref.name];
      if (imported?.type && typeof imported.type.name === "string") {
        return imported;
      }
      return undefined;
    }
    const own = this.module.typedefs[ref.name] as TypedefShape | undefined;
    if (own?.type && typeof own.type.name === "string") {
      return own;
    }
    return undefined;
  }

  /**
   * Follow a typedef chain to the underlying builtin type name (stops at unions or unknown).
   */
  resolveUnderlyingBuiltinName(typeName: string, constraint?: Record<string, unknown>): string {
    const seen = new Set<string>();
    let ref = asTypeRef(typeName, constraint);
    while (seen.size < 64) {
      const typedef = this.lookupTypedef(ref);
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
    }
    return ref.name;
  }

  validate(value: unknown, typeName: string, constraint?: Record<string, unknown>): [boolean, string | null] {
    let via: "typedef" | "typedef-union" | "inline-union" | "direct";
    let result: [boolean, string | null];

    const ref = asTypeRef(typeName, constraint);
    const typedef = this.lookupTypedef(ref);
    if (typedef?.type && typeof typedef.type.name === "string") {
      const typedefConstraint = new TypeConstraint(typedef.type as Record<string, unknown>);
      if (typedef.type.name === YangTokenType.UNION) {
        via = "typedef-union";
        result = this.validateUnion(value, typedefConstraint);
      } else if (this.lookupTypedef(asTypeRef(typedef.type.name, typedef.type as Record<string, unknown>))) {
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
    if (result[0] && via === "typedef" && hasTypeRestrictions(constraint)) {
      result = this.system.validate(
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
        ok: result[0],
        reason: result[1],
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
  ): [boolean, string | null] {
    if (typeName === YangTokenType.IDENTITYREF) {
      return this.checkIdentityref(value, shape ?? {});
    }
    return this.system.validate(value, typeName, constraint);
  }

  /** RFC 7951 §6.8 value, derived from every base (bases resolve in the host module, as in Python). */
  private checkIdentityref(value: unknown, shape: Record<string, unknown>): [boolean, string | null] {
    if (typeof value !== "string") {
      return [false, `identityref value must be a string, got ${value === null ? "null" : typeof value}`];
    }
    const bases = Array.isArray(shape.identityref_bases) ? (shape.identityref_bases as YangIdentifierRef[]) : [];
    if (bases.length === 0) {
      return [false, "identityref type has no base identities"];
    }
    const moduleData = this.module.data as Record<string, unknown>;
    if (!resolveIdentityValue(moduleData, value)) {
      return [false, `identityref value '${value}' does not resolve to a known identity`];
    }
    if (!identityrefValueValid(moduleData, value, bases)) {
      const shown = bases.map((b) => `'${formatIdentifierRef(b)}'`).join(", ");
      return [false, `identityref value '${value}' is not derived from all bases [${shown}]`];
    }
    return [true, null];
  }

  /** Union members may name typedefs; validate through this checker so typedefs resolve. */
  private validateUnion(value: unknown, constraint: TypeConstraint): [boolean, string | null] {
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
      const [ok] = this.validate(value, memberName, memberObj);
      if (ok) {
        return [true, null];
      }
    }
    return [false, "Value does not match any union member type"];
  }
}
