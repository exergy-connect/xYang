"""Tests for examples/generic-field.yang (recursive generic-field model)."""

from __future__ import annotations

from pathlib import Path

from xyang.parser.yang_parser import YangParser

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "generic-field.yang"


def test_generic_field_yang_parses_with_expand_uses_disabled():
    """Example module parses when ``uses`` expansion is disabled."""
    parser = YangParser(expand_uses=False)
    module = parser.parse_file(EXAMPLE)
    assert module.name == "generic-field"
    assert module.namespace == "urn:xyang:example:generic-field"


def test_generic_field_yang_parses_with_default_expand():
    """Current example uses a simpler schema (no recursive ``uses``); default expand completes."""
    parser = YangParser(expand_uses=True)
    module = parser.parse_file(EXAMPLE)
    assert module.name == "generic-field"
    assert module.namespace == "urn:xyang:example:generic-field"
