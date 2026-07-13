type TypeConstraintInput = {
    patterns?: Array<{
        pattern: string;
        invert_match?: boolean;
        error_message?: string;
        error_app_tag?: string;
    }>;
    length?: string;
    range?: string;
    fraction_digits?: number;
    enums?: string[];
    bits?: Array<{
        name: string;
        position: number;
    }>;
    types?: Array<Record<string, unknown>>;
};
declare class TypeConstraint {
    patterns?: Array<{
        pattern: string;
        invert_match?: boolean;
        error_message?: string;
        error_app_tag?: string;
    }>;
    length?: string;
    range?: string;
    fraction_digits?: number;
    enums?: string[];
    bits?: Array<{
        name: string;
        position: number;
    }>;
    types?: Array<Record<string, unknown>>;
    constructor(input?: TypeConstraintInput);
}
declare class TypeSystem {
    validate(value: unknown, typeName: string, constraint?: TypeConstraint): [boolean, string | null];
}

export { TypeConstraint, TypeSystem };
