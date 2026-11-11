"""Meta-model foreignKeys list must constraints (examples/meta-model.yang).

Standalone must-on-list-with-leafref, concat(), and deref type-match coverage
lives in tests/cases/xpath/must-leafref-list, must-concat, and deref-type-match.
"""

from pathlib import Path

from xyang import parse_yang_file, YangValidator


def test_must_on_foreignkeys_list_valid():
    """must on foreignKeys list (meta-model) with matching FK types."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)

    data = {
        "data-model": {
            "name": "Test Model",
            "version": "26.03.29.1",
            "author": "Test",
            "description": "FK list must test.",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "description": "Parent entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {"name": "name", "description": "Name.", "type": {"primitive": "string"}},
                    ],
                },
                {
                    "name": "child",
                    "description": "Child entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {
                            "name": "parent_id",
                            "description": "FK to parent PK.",
                            "type": {
                                "primitive": "integer",
                                "foreignKeys": [{"entity": "parent"}],
                            },
                        },
                    ],
                },
            ],
        }
    }

    is_valid, errors, _ = validator.validate(data)
    assert is_valid, f"Valid foreign key reference should pass. Errors: {errors}"


def test_must_on_foreignkeys_list_invalid():
    """must on foreignKeys list (meta-model) when FK type mismatches PK type."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)

    data = {
        "data-model": {
            "name": "Test Model",
            "version": "26.03.29.1",
            "author": "Test",
            "description": "FK mismatch test.",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "description": "Parent entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {"name": "name", "description": "Name.", "type": {"primitive": "string"}},
                    ],
                },
                {
                    "name": "child",
                    "description": "Child entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {
                            "name": "parent_name",
                            "description": "String FK to parent (type mismatch vs int PK).",
                            "type": {
                                "primitive": "string",
                                "foreignKeys": [{"entity": "parent"}],
                            },
                        },
                    ],
                },
            ],
        }
    }

    is_valid, errors, _ = validator.validate(data)
    if not is_valid:
        assert any("type" in err.lower() or "primary key" in err.lower() for err in errors), (
            f"Error should mention type or primary key. Errors: {errors}"
        )
