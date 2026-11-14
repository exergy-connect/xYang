//! Shared string keys for the native JSON form and its `x-yang` annotations (mirrors
//! `src/xyang/json/schema_keys.py`). The generator emits and the parser consumes these,
//! so keyword names stay in sync.

pub const REF = "$ref";
pub const DEFS = "$defs";
pub const SCHEMA = "$schema";
pub const ID = "$id";
pub const ALL_OF = "allOf";
pub const NOT = "not";
pub const ONE_OF = "oneOf";
pub const PROPERTIES = "properties";
pub const REQUIRED = "required";
pub const DESCRIPTION = "description";
pub const TYPE = "type";
pub const ITEMS = "items";
pub const DEFAULT = "default";
pub const EXAMPLES = "examples";
pub const ENUM = "enum";
pub const PATTERN = "pattern";
pub const MIN_LENGTH = "minLength";
pub const MAX_LENGTH = "maxLength";
pub const MINIMUM = "minimum";
pub const MAXIMUM = "maximum";
pub const MAX_PROPERTIES = "maxProperties";
pub const MULTIPLE_OF = "multipleOf";
pub const X_FRACTION_DIGITS = "x-fraction-digits";
pub const MIN_ITEMS = "minItems";
pub const MAX_ITEMS = "maxItems";
pub const ADDITIONAL_PROPERTIES = "additionalProperties";
pub const X_YANG = "x-yang";
pub const NAME = "name";

pub const DEFS_URI_PREFIX = "#/" ++ DEFS ++ "/";

/// Keys inside the `x-yang` object (and the root module metadata).
pub const xy = struct {
    pub const SCOPE = "scope";
    pub const TYPE_CONTEXT = "type-context";
    pub const TYPE = "type";
    pub const BASE = "base";
    pub const BASES = "bases";
    pub const PATH = "path";
    pub const REQUIRE_INSTANCE = "require-instance";
    pub const WHEN = "when";
    pub const MUST = "must";
    pub const BITS = "bits";
    pub const KEY = "key";
    pub const UNIQUE = "unique";
    pub const PRESENCE = "presence";
    pub const MANDATORY = "mandatory";
    pub const CONFIG = "config";
    pub const CHOICE = "choice";
    pub const AUGMENT_STRUCTURE = "augment-structure";
    pub const FEATURES = "features";
    pub const IF_FEATURES = "if-features";
    pub const MODULE = "module";
    pub const YANG_VERSION = "yang-version";
    pub const NAMESPACE = "namespace";
    pub const PREFIX = "prefix";
    pub const ORGANIZATION = "organization";
    pub const CONTACT = "contact";
    pub const RPCS = "rpcs";
    pub const ACTIONS = "actions";
    pub const PATTERN_ERROR_MESSAGE = "pattern-error-message";
    pub const PATTERN_ERROR_APP_TAG = "pattern-error-app-tag";
    pub const STRING_PATTERNS = "string-patterns";
    pub const UNITS = "units";
    pub const XPATH_PREFIXES = "xpath-prefixes";
    pub const IMPORTS = "imports";
    pub const IDENTITIES = "identities";
    pub const EXTENSION = "extension";
    pub const EXTENSIONS = "extensions";
    pub const ARGUMENT = "argument";
    pub const YIN_ELEMENT = "yin-element";
    pub const REFERENCE = "reference";
    pub const BODY = "body";
    pub const RANGE = "range";
    pub const FRACTION_DIGITS = "fraction-digits";
    pub const INVERT_MATCH = "invert-match";
};

/// Values of `x-yang.type`.
pub const types = struct {
    pub const LEAFREF = "leafref";
    pub const IDENTITY = "identity";
    pub const IDENTITYREF = "identityref";
    pub const INSTANCE_IDENTIFIER = "instance-identifier";
    pub const BITS = "bits";
    pub const ANYDATA = "anydata";
    pub const ANYXML = "anyxml";
    pub const RPC = "rpc";
    pub const ACTION = "action";
    pub const INPUT = "input";
    pub const OUTPUT = "output";
};

/// Keys of one `x-yang.must` entry.
pub const must_entry = struct {
    pub const MUST = "must";
    pub const ERROR_MESSAGE = "error-message";
    pub const ERROR_APP_TAG = "error-app-tag";
};

/// Keys of `x-yang.when`.
pub const when_entry = struct {
    pub const EVALUATE_WITH_PARENT_CONTEXT = "evaluate-with-parent-context";
    pub const CONDITION = "condition";
};
