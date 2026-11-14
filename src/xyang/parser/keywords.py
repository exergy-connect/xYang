"""
YANG keyword constants used by parser modules.

All YANG statement/type keywords are represented as plain identifier lexemes.
"""

# Core module/header keywords
MODULE = "module"
YANG_VERSION = "yang-version"
NAMESPACE = "namespace"
PREFIX = "prefix"
ORGANIZATION = "organization"
CONTACT = "contact"
DESCRIPTION = "description"
REVISION = "revision"
REFERENCE = "reference"

# Definitions
TYPEDEF = "typedef"
IDENTITY = "identity"
BASE = "base"
TYPE = "type"
GROUPING = "grouping"
USES = "uses"
REFINE = "refine"
FEATURE = "feature"
IF_FEATURE = "if-feature"
EXTENSION = "extension"
ARGUMENT = "argument"
YIN_ELEMENT = "yin-element"

# Data nodes/statements
CONTAINER = "container"
LIST = "list"
LEAF = "leaf"
LEAF_LIST = "leaf-list"
ANYDATA = "anydata"
ANYXML = "anyxml"
CHOICE = "choice"
CASE = "case"
MUST = "must"
WHEN = "when"
PRESENCE = "presence"
KEY = "key"
MIN_ELEMENTS = "min-elements"
UNIQUE = "unique"
MAX_ELEMENTS = "max-elements"
ORDERED_BY = "ordered-by"
MANDATORY = "mandatory"
CONFIG = "config"
DEFAULT = "default"
ERROR_MESSAGE = "error-message"
ERROR_APP_TAG = "error-app-tag"

# Built-in type names live in the type registry.
from ..types.registry import (  # noqa: F401
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
    UINT8,
    UINT16,
    UINT32,
    UINT64,
    UNION,
)

# Type substatements
PATH = "path"
REQUIRE_INSTANCE = "require-instance"
ENUM = "enum"
VALUE = "value"
STATUS = "status"
UNITS = "units"
BIT = "bit"
POSITION = "position"
PATTERN = "pattern"
MODIFIER = "modifier"
LENGTH = "length"
FRACTION_DIGITS = "fraction-digits"
RANGE = "range"
TRUE = "true"
FALSE = "false"

# Cross-module/submodule
IMPORT = "import"
INCLUDE = "include"
REVISION_DATE = "revision-date"
AUGMENT = "augment"
SUBMODULE = "submodule"
BELONGS_TO = "belongs-to"

# Deviation (RFC 7950 §7.20.3)
DEVIATION = "deviation"
DEVIATE = "deviate"
NOT_SUPPORTED = "not-supported"
ADD = "add"
DELETE = "delete"
REPLACE = "replace"
# Substatements each ``deviate`` argument allows (RFC 7950 §7.20.3.2 grammar).
DEVIATE_SUBSTATEMENTS: dict[str, frozenset[str]] = {
    ADD: frozenset(
        {UNITS, MUST, UNIQUE, DEFAULT, CONFIG, MANDATORY, MIN_ELEMENTS, MAX_ELEMENTS}
    ),
    DELETE: frozenset({UNITS, MUST, UNIQUE, DEFAULT}),
    REPLACE: frozenset(
        {TYPE, UNITS, DEFAULT, CONFIG, MANDATORY, MIN_ELEMENTS, MAX_ELEMENTS}
    ),
}

# Unsupported statements
RPC = "rpc"
ACTION = "action"
NOTIFICATION = "notification"
INPUT = "input"
OUTPUT = "output"

UNSUPPORTED_CONSTRUCT_KEYWORDS: frozenset[str] = frozenset()
