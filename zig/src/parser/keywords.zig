//! YANG keyword lexemes used by the parser (mirrors `src/xyang/parser/keywords.py`).

pub const MODULE = "module";
pub const SUBMODULE = "submodule";
pub const YANG_VERSION = "yang-version";
pub const NAMESPACE = "namespace";
pub const PREFIX = "prefix";
pub const ORGANIZATION = "organization";
pub const CONTACT = "contact";
pub const DESCRIPTION = "description";
pub const REVISION = "revision";
pub const REFERENCE = "reference";

pub const TYPEDEF = "typedef";
pub const IDENTITY = "identity";
pub const BASE = "base";
pub const TYPE = "type";
pub const GROUPING = "grouping";
pub const USES = "uses";
pub const REFINE = "refine";
pub const FEATURE = "feature";
pub const IF_FEATURE = "if-feature";
pub const EXTENSION = "extension";
pub const ARGUMENT = "argument";
pub const YIN_ELEMENT = "yin-element";

pub const CONTAINER = "container";
pub const LIST = "list";
pub const LEAF = "leaf";
pub const LEAF_LIST = "leaf-list";
pub const ANYDATA = "anydata";
pub const ANYXML = "anyxml";
pub const CHOICE = "choice";
pub const CASE = "case";
pub const MUST = "must";
pub const WHEN = "when";
pub const PRESENCE = "presence";
pub const KEY = "key";
pub const MIN_ELEMENTS = "min-elements";
pub const UNIQUE = "unique";
pub const MAX_ELEMENTS = "max-elements";
pub const ORDERED_BY = "ordered-by";
pub const MANDATORY = "mandatory";
pub const CONFIG = "config";
pub const DEFAULT = "default";
pub const ERROR_MESSAGE = "error-message";
pub const ERROR_APP_TAG = "error-app-tag";

pub const BITS = "bits";
pub const ENUMERATION = "enumeration";
pub const IDENTITYREF = "identityref";
pub const UNION = "union";
pub const PATH = "path";
pub const REQUIRE_INSTANCE = "require-instance";
pub const ENUM = "enum";
pub const VALUE = "value";
pub const STATUS = "status";
pub const UNITS = "units";
pub const BIT = "bit";
pub const POSITION = "position";
pub const PATTERN = "pattern";
pub const MODIFIER = "modifier";
pub const LENGTH = "length";
pub const FRACTION_DIGITS = "fraction-digits";
pub const RANGE = "range";
pub const TRUE = "true";
pub const FALSE = "false";

pub const IMPORT = "import";
pub const INCLUDE = "include";
pub const REVISION_DATE = "revision-date";
pub const AUGMENT = "augment";
pub const BELONGS_TO = "belongs-to";

pub const DEVIATION = "deviation";
pub const DEVIATE = "deviate";
pub const NOT_SUPPORTED = "not-supported";

pub const RPC = "rpc";
pub const ACTION = "action";
pub const NOTIFICATION = "notification";
pub const INPUT = "input";
pub const OUTPUT = "output";
