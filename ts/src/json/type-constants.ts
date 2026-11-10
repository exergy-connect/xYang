export const JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

export const JSON_TYPE_STRING = "string";
export const JSON_TYPE_INTEGER = "integer";
export const JSON_TYPE_NUMBER = "number";
export const JSON_TYPE_BOOLEAN = "boolean";
export const JSON_TYPE_OBJECT = "object";
export const JSON_TYPE_ARRAY = "array";
export const JSON_TYPE_NULL = "null";

export const JSON_TYPE_FREE_FORM = [
  JSON_TYPE_STRING,
  JSON_TYPE_NUMBER,
  JSON_TYPE_BOOLEAN,
  JSON_TYPE_OBJECT,
  JSON_TYPE_ARRAY,
  JSON_TYPE_NULL
] as const;
