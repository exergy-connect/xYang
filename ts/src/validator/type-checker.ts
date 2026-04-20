import { YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { TypeConstraint, TypeSystem } from "../types";

export class TypeChecker {
  private readonly system = new TypeSystem();

  constructor(private readonly module: YangModule) {}

  validate(value: unknown, typeName: string, constraint?: Record<string, unknown>): [boolean, string | null] {
    const typedef = this.module.typedefs[typeName] as { type?: Record<string, unknown> } | undefined;
    if (typedef?.type && typeof typedef.type.name === "string") {
      const typedefConstraint = new TypeConstraint(typedef.type as Record<string, unknown>);
      if (typedef.type.name === YangTokenType.UNION) {
        return this.validateUnion(value, typedefConstraint);
      }
      return this.system.validate(value, typedef.type.name, typedefConstraint);
    }

    const merged = new TypeConstraint(constraint as Record<string, unknown> | undefined);
    if (typeName === YangTokenType.UNION && (merged.types?.length ?? 0) > 0) {
      return this.validateUnion(value, merged);
    }
    return this.system.validate(value, typeName, merged);
  }

  /** Union members may name typedefs; validate through this checker so typedefs resolve. */
  private validateUnion(value: unknown, constraint: TypeConstraint): [boolean, string | null] {
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
