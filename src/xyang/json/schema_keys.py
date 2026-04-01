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
    ONE_OF = "oneOf"
    PROPERTIES = "properties"
    REQUIRED = "required"
    DESCRIPTION = "description"
    TYPE = "type"
    ITEMS = "items"
    DEFAULT = "default"
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
    return f"{JSON_SCHEMA_DEFS_URI_PREFIX}{typedef_name}"


class XYangKey:
    """Keys inside the ``x-yang`` extension object (and root module metadata)."""

    TYPE = "type"
    BASE = "base"
    BASES = "bases"
    PATH = "path"
    REQUIRE_INSTANCE = "require-instance"
    WHEN = "when"
    MUST = "must"
    KEY = "key"
    PRESENCE = "presence"
    MANDATORY = "mandatory"
    CHOICE = "choice"
    MODULE = "module"
    YANG_VERSION = "yang-version"
    NAMESPACE = "namespace"
    PREFIX = "prefix"
    ORGANIZATION = "organization"
    CONTACT = "contact"


class XYangTypeValue:
    """Values for ``x-yang.type`` (e.g. merged leaf type for leafref)."""

    LEAFREF = "leafref"
    IDENTITY = "identity"
    IDENTITYREF = "identityref"
    INSTANCE_IDENTIFIER = "instance-identifier"


class XYangMustEntryKey:
    """Keys inside each element of ``x-yang.must``."""

    MUST = "must"
    ERROR_MESSAGE = "error-message"


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
