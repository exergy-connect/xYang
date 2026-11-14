"""
Shared string keys for JSON Schema output and ``x-yang`` annotations.

Used by ``generator`` (emit) and ``parser`` (consume) so keyword names stay in sync.
"""

from __future__ import annotations


class JsonSchemaKey:
    """Property names on JSON Schema objects (draft 2020-12 + extensions)."""

    REF = "$ref"
    DEFS = "$defs"
    SCHEMA = "$schema"
    ID = "$id"
    ALL_OF = "allOf"
    NOT = "not"
    ONE_OF = "oneOf"
    PROPERTIES = "properties"
    REQUIRED = "required"
    DESCRIPTION = "description"
    TYPE = "type"
    ITEMS = "items"
    DEFAULT = "default"
    EXAMPLES = "examples"
    ENUM = "enum"
    PATTERN = "pattern"
    MIN_LENGTH = "minLength"
    MAX_LENGTH = "maxLength"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MAX_PROPERTIES = "maxProperties"
    MULTIPLE_OF = "multipleOf"
    X_FRACTION_DIGITS = "x-fraction-digits"
    MIN_ITEMS = "minItems"
    MAX_ITEMS = "maxItems"
    ADDITIONAL_PROPERTIES = "additionalProperties"
    X_YANG = "x-yang"
    # Common root container name in xFrame meta-model instances (not required by the parser).
    DATA_MODEL = "data-model"
    NAME = "name"


JSON_SCHEMA_DEFS_URI_PREFIX = f"#/{JsonSchemaKey.DEFS}/"


def json_schema_defs_uri(typedef_name: str) -> str:
    """JSON Pointer-style URI for a local ``$defs`` entry (e.g. ``#/$defs/foo``)."""
    from urllib.parse import quote

    key = typedef_name.replace("~", "~0").replace("/", "~1")
    return f"{JSON_SCHEMA_DEFS_URI_PREFIX}{quote(key, safe='~')}"


class XYangKey:
    """Keys inside the ``x-yang`` extension object (and root module metadata)."""

    TYPE = "type"
    BASE = "base"
    BASES = "bases"
    PATH = "path"
    REQUIRE_INSTANCE = "require-instance"
    WHEN = "when"
    MUST = "must"
    BITS = "bits"
    KEY = "key"
    UNIQUE = "unique"
    PRESENCE = "presence"
    MANDATORY = "mandatory"
    CONFIG = "config"
    CHOICE = "choice"
    IF_FEATURES = "if-features"
    MODULE = "module"
    YANG_VERSION = "yang-version"
    NAMESPACE = "namespace"
    PREFIX = "prefix"
    ORGANIZATION = "organization"
    CONTACT = "contact"
    #: Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name.
    RPCS = "rpcs"
    #: Actions of a container or list (RFC 7950 §7.15), keyed by action name; same shape as ``rpcs``.
    ACTIONS = "actions"
    #: From ``pattern { error-message "..."; }`` (RFC 7950 §9.4.6), echoed on string JSON Schema.
    PATTERN_ERROR_MESSAGE = "pattern-error-message"
    PATTERN_ERROR_APP_TAG = "pattern-error-app-tag"
    #: List of all YANG pattern entries for round-trip (regex + invert + optional metadata).
    STRING_PATTERNS = "string-patterns"
    #: RFC 7950 §7.21.4 ``units`` (e.g. ``"kbit/s"``).
    UNITS = "units"
    #: ``{prefix: module}`` for the prefixed steps of a leafref ``path``, ``must`` or ``when``,
    #: resolved in the module that wrote it (RFC 7950 §6.4.1). The JSON form has no imports.
    XPATH_PREFIXES = "xpath-prefixes"
    #: ``{key: module stub}``: the imported modules the identities of this module derive from
    #: (RFC 7950 §7.18.2), so the form needs no ``import`` resolution at load time. A stub has
    #: ``module``, ``namespace``, ``prefix``, its own ``imports`` and its ``identities``.
    IMPORTS = "imports"
    IDENTITIES = "identities"
    #: Extension definitions (RFC 7950 §7.19) of this module, keyed by name. An imported
    #: extension this module invokes is the same object on that import's stub.
    EXTENSION = "extension"
    #: Invocations of an extension on this node, in source order. Each entry is
    #: ``{name, argument?, description?, reference?, body?}``. ``name`` is ``prefix:ext``.
    EXTENSIONS = "extensions"
    ARGUMENT = "argument"
    YIN_ELEMENT = "yin-element"
    REFERENCE = "reference"
    #: Nested statements of an extension invocation, in source order. An entry is
    #: ``{"extension": <invocation>}`` or ``{"node": <member name>, "schema": <node schema>}``.
    BODY = "body"
    #: Declared ``feature`` names of this module (RFC 7950 §7.20.1). Values are ``{}`` or
    #: ``{"if-features": [...]}`` when the feature itself has ``if-feature``.
    FEATURES = "features"
    #: Absolute schema path of the ``sx:augment-structure`` that added this node (RFC 8791).
    AUGMENT_STRUCTURE = "augment-structure"


class XYangTypeValue:
    """Values for ``x-yang.type`` (e.g. merged leaf type for leafref)."""

    LEAFREF = "leafref"
    IDENTITY = "identity"
    IDENTITYREF = "identityref"
    INSTANCE_IDENTIFIER = "instance-identifier"
    BITS = "bits"
    ANYDATA = "anydata"
    ANYXML = "anyxml"
    RPC = "rpc"
    ACTION = "action"
    INPUT = "input"
    OUTPUT = "output"


class XYangMustEntryKey:
    """Keys inside each element of ``x-yang.must``."""

    MUST = "must"
    ERROR_MESSAGE = "error-message"
    ERROR_APP_TAG = "error-app-tag"


class XYangWhenEntryKey:
    """Keys inside ``x-yang.when`` when encoded as an object (condition + optional description)."""

    CONDITION = "condition"


__all__ = [
    "JSON_SCHEMA_DEFS_URI_PREFIX",
    "JsonSchemaKey",
    "XYangKey",
    "XYangMustEntryKey",
    "XYangWhenEntryKey",
    "XYangTypeValue",
    "json_schema_defs_uri",
]
