import { UnsupportedXPathError } from "../core/errors";

/** Names both implementations implement. Keep in step with Python ``FUNCTIONS``. */
export const XPATH_FUNCTION_NAMES = new Set([
  "boolean",
  "concat",
  "count",
  "current",
  "deref",
  "derived-from",
  "derived-from-or-self",
  "false",
  "not",
  "number",
  "string",
  "string-length",
  "translate",
  "true"
]);

/** Same code string as Python ``UNKNOWN_FUNCTION_CODE``. */
export const UNKNOWN_FUNCTION_CODE = "xpath-unknown-function";

export function unknownFunctionError(name: string, expression?: string): UnsupportedXPathError {
  const key = name.toLowerCase();
  return new UnsupportedXPathError(`${UNKNOWN_FUNCTION_CODE}: unknown XPath function '${key}'`, {
    expression,
    construct: key,
    code: UNKNOWN_FUNCTION_CODE
  });
}
