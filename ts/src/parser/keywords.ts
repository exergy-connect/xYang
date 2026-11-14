export const MODULE = "module";
export const YANG_VERSION = "yang-version";
export const NAMESPACE = "namespace";
export const PREFIX = "prefix";
export const ORGANIZATION = "organization";
export const CONTACT = "contact";
export const DESCRIPTION = "description";
export const REVISION = "revision";
export const TYPEDEF = "typedef";
export const IDENTITY = "identity";
export const BASE = "base";
export const TYPE = "type";
export {
  BINARY,
  BITS,
  BOOLEAN,
  DECIMAL64,
  EMPTY,
  ENUMERATION,
  IDENTITYREF,
  INSTANCE_IDENTIFIER,
  INT8,
  INT16,
  INT32,
  INT64,
  LEAFREF,
  STRING as STRING_KW,
  UINT8,
  UINT16,
  UINT32,
  UINT64,
  UNION
} from "../types/registry";
export const PATH = "path";
export const REQUIRE_INSTANCE = "require-instance";
export const ENUM = "enum";
export const VALUE = "value";
export const STATUS = "status";
export const BIT = "bit";
export const POSITION = "position";
export const PATTERN = "pattern";
export const MODIFIER = "modifier";
export const LENGTH = "length";
export const UNITS = "units";
export const FRACTION_DIGITS = "fraction-digits";
export const RANGE = "range";
export const GROUPING = "grouping";
export const USES = "uses";
export const REFINE = "refine";
export const CONTAINER = "container";
export const LIST = "list";
export const LEAF = "leaf";
export const LEAF_LIST = "leaf-list";
export const ANYDATA = "anydata";
export const ANYXML = "anyxml";
export const CHOICE = "choice";
export const CASE = "case";
export const MUST = "must";
export const WHEN = "when";
export const PRESENCE = "presence";
export const KEY = "key";
export const MIN_ELEMENTS = "min-elements";
export const UNIQUE = "unique";
export const MAX_ELEMENTS = "max-elements";
export const ORDERED_BY = "ordered-by";
export const MANDATORY = "mandatory";
export const CONFIG = "config";
export const DEFAULT = "default";
export const ERROR_MESSAGE = "error-message";
export const ERROR_APP_TAG = "error-app-tag";
export const TRUE = "true";
export const FALSE = "false";
export const IMPORT = "import";
export const INCLUDE = "include";
export const REVISION_DATE = "revision-date";
export const FEATURE = "feature";
export const IF_FEATURE = "if-feature";
export const AUGMENT = "augment";
export const SUBMODULE = "submodule";
export const BELONGS_TO = "belongs-to";
export const REFERENCE = "reference";
export const ARGUMENT = "argument";
export const YIN_ELEMENT = "yin-element";
export const DEVIATION = "deviation";
export const DEVIATE = "deviate";
export const NOT_SUPPORTED = "not-supported";
const ADD = "add";
const DELETE = "delete";
const REPLACE = "replace";
/** Substatements each ``deviate`` argument allows (RFC 7950 §7.20.3.2 grammar). */
export const DEVIATE_SUBSTATEMENTS: ReadonlyMap<string, ReadonlySet<string>> = new Map([
  [ADD, new Set(["units", "must", "unique", "default", "config", "mandatory", "min-elements", "max-elements"])],
  [DELETE, new Set(["units", "must", "unique", "default"])],
  [REPLACE, new Set(["type", "units", "default", "config", "mandatory", "min-elements", "max-elements"])]
]);
export const EXTENSION = "extension";
export const RPC = "rpc";
export const ACTION = "action";
export const NOTIFICATION = "notification";
export const INPUT = "input";
export const OUTPUT = "output";

export const UNSUPPORTED_CONSTRUCT_KEYWORDS = new Set<string>();
