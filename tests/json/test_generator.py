"""
Test JSON schema generator: YANG AST -> JSON Schema (schema.yang.json).

Tests parse with uses expansion disabled so the AST contains uses/refine;
the generator expands uses when emitting JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from xyang.json import generate_json_schema, parse_json_schema, schema_to_yang_json
from xyang.parser.yang_parser import YangParser

if TYPE_CHECKING:
    from xyang.module import YangModule


_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
META_MODEL_YANG = _EXAMPLES_DIR / "meta-model.yang"


def _parse_without_expanding_uses() -> YangModule:
    """Parse meta-model.yang with uses/refine left unexpanded (generator will expand)."""
    parser = YangParser(expand_uses=False)
    return parser.parse_file(META_MODEL_YANG)


def test_generate_json_schema_from_yang_module():
    """Parse meta-model.yang (no uses expansion), generate JSON schema, assert structure."""
    assert META_MODEL_YANG.exists(), f"Missing {META_MODEL_YANG}"
    module = _parse_without_expanding_uses()
    data = generate_json_schema(module)
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "x-yang" in data
    assert data["x-yang"]["module"] == "meta-model"
    assert data["type"] == "object"
    assert "properties" in data
    assert "data-model" in data["properties"]
    assert "additionalProperties" in data
    assert data["additionalProperties"] is False
    assert "$defs" in data
    assert "entity-name" in data["$defs"]


def test_schema_to_yang_json_writes_file(tmp_path: Path):
    """schema_to_yang_json with output_path writes schema.yang.json."""
    assert META_MODEL_YANG.exists()
    module = _parse_without_expanding_uses()
    out_file = tmp_path / "schema.yang.json"
    text = schema_to_yang_json(module, output_path=out_file)
    assert out_file.exists()
    assert isinstance(text, str)
    loaded = json.loads(out_file.read_text())
    assert loaded["x-yang"]["module"] == "meta-model"


def test_roundtrip_yang_to_json_to_ast():
    """Parse YANG (no uses expansion) -> generate JSON (expands uses) -> parse JSON -> same module name and root container."""
    assert META_MODEL_YANG.exists()
    module = _parse_without_expanding_uses()
    data = generate_json_schema(module)
    module2 = parse_json_schema(data)
    assert module2.name == module.name
    assert len(module2.statements) == len(module.statements)
    # Root container present
    dm = module2.find_statement("data-model")
    assert dm is not None
