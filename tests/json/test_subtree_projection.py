"""A TypeScript subtree projection is not a reversible native JSON module."""
import pytest

from xyang import parse_json_schema


def test_rejects_subtree_projection():
    with pytest.raises(ValueError, match="projection"):
        parse_json_schema({"type": "object", "x-yang": {"subtree-path": "/m:topology"}})
