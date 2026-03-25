"""Tests for examples/generic-field.yang (recursive generic-field model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang.errors import YangCircularUsesError
from xyang.parser.yang_parser import YangParser

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "generic-field.yang"


def test_generic_field_yang_parses_with_expand_uses_disabled():
    """Recursive ``uses generic-field`` under ``list fields`` cannot be fully expanded (cycle)."""
    parser = YangParser(expand_uses=False)
    module = parser.parse_file(EXAMPLE)
    assert module.name == "generic-field"
    assert module.namespace == "urn:xyang:example:generic-field"


def test_generic_field_yang_reports_circular_uses_when_expanding():
    """Default parser expands ``uses``; this example has a ``generic-field`` ↔ grouping cycle."""
    parser = YangParser(expand_uses=True)
    with pytest.raises(YangCircularUsesError) as exc:
        parser.parse_file(EXAMPLE)
    assert "generic-field" in str(exc.value)
