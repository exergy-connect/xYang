"""Plain JSON Schema (no x-yang) is rejected instead of an empty module (#80)."""

from __future__ import annotations

import re

import pytest

from xyang.json import parse_json_schema

ROOT_MESSAGE = (
    'JSON Schema has no root "x-yang" annotation; xYang needs a .yang.json '
    'produced by "xyang convert" (see design/json-schema-xyang-profile.md)'
)
PROPERTY_MESSAGE = 'JSON Schema property "city" has no "x-yang" annotation'

_PLAIN = {"type": "object", "properties": {"city": {"type": "string"}}}
_BARE_PROPERTY = {
    "type": "object",
    "x-yang": {"module": "example", "namespace": "urn:example", "prefix": "ex"},
    "properties": {"city": {"type": "string"}},
}


def test_plain_schema_without_root_x_yang_raises():
    with pytest.raises(ValueError, match=re.escape(ROOT_MESSAGE)):
        parse_json_schema(_PLAIN)


def test_root_x_yang_with_bare_property_raises():
    with pytest.raises(ValueError, match=re.escape(PROPERTY_MESSAGE)):
        parse_json_schema(_BARE_PROPERTY)
