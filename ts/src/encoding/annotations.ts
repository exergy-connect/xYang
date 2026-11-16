import { ANNOTATION_FAMILIES } from "./annotation-families";
export type AnnotationOptions = { allowJsonld?: boolean; allowJsonSchema?: boolean };
export function isAnnotation(key: string, options: AnnotationOptions = {}): boolean {
  return (Object.keys(ANNOTATION_FAMILIES) as Array<keyof typeof ANNOTATION_FAMILIES>).some((family) => {
    const enabled = family === "jsonld" ? options.allowJsonld !== false : options.allowJsonSchema !== false;
    return enabled && new RegExp(ANNOTATION_FAMILIES[family].pattern).exec(key)?.[0] === key;
  });
}
export function annotateSchema(schema: Record<string, unknown>, options: AnnotationOptions): void {
  const patterns = Object.fromEntries(Object.entries(ANNOTATION_FAMILIES)
    .filter(([family]) => family === "jsonld" ? options.allowJsonld !== false : options.allowJsonSchema !== false)
    .map(([, value]) => [value.pattern, true]));
  if (Object.keys(patterns).length === 0) return;
  if (schema.type === "object" || schema.properties) {
    if (schema.maxProperties === 0) {
      delete schema.maxProperties;
      schema.properties = {};
      schema.additionalProperties = false;
    }
    schema.patternProperties = { ...patterns };
  }
  const visit = (value: unknown): void => {
    if (value && typeof value === "object" && !Array.isArray(value)) annotateSchema(value as Record<string, unknown>, options);
  };
  for (const key of ["properties", "$defs"]) {
    for (const child of Object.values((schema[key] as Record<string, unknown>) ?? {})) visit(child);
  }
  for (const key of ["items", "not", "additionalProperties"]) visit(schema[key]);
  for (const key of ["oneOf", "anyOf", "allOf"]) for (const child of (schema[key] as unknown[]) ?? []) visit(child);
}
export function isEmptyChoiceBranch(schema: Record<string, unknown>): boolean {
  return schema.type === "object" && (schema.maxProperties === 0 ||
    (schema.additionalProperties === false && schema.patternProperties !== undefined &&
      Object.keys((schema.properties as Record<string, unknown>) ?? {}).length === 0));
}
