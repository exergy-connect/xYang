"""Regression: relative leafref ../../fields/name from entities/parents/child_fk.

Dangling relative leafref require-instance coverage: tests/cases/references/leafref.
"""

from pathlib import Path

from xyang import parse_yang_file, YangValidator


def test_leafref_relative_path_resolution():
    """../../fields/name from entities/parents/child_fk resolves to entities/fields/name."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)

    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [
                {
                    "name": "parent_entity",
                    "primary_key": "parent_id",
                    "fields": [
                        {"name": "parent_id", "type": "string"},
                        {"name": "children", "type": "array", "item_type": {"entity": "child_entity"}},
                    ],
                },
                {
                    "name": "child_entity",
                    "primary_key": "child_id",
                    "fields": [
                        {"name": "child_id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKeys": [{"entity": "parent_entity"}],
                        },
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "children",
                        }
                    ],
                },
            ],
        }
    }

    is_valid, errors, _ = validator.validate(data)

    leafref_errors = [e for e in errors if "no target instance" in e or "Relative path resolution" in e]
    assert len(leafref_errors) == 0, (
        f"Should not have leafref resolution errors. Leafref errors: {leafref_errors}. "
        f"All errors: {errors}"
    )

    if not is_valid:
        non_leafref_errors = [
            e for e in errors if "no target instance" not in e and "Relative path resolution" not in e
        ]
        print(f"Validation failed but leafref resolution worked. Other errors: {non_leafref_errors}")


def test_leafref_relative_path_multiple_entities():
    """Relative path resolves to the current entity's fields, not another entity's."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)

    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id1",
                    "fields": [
                        {"name": "id1", "type": "string"},
                        {"name": "field1", "type": "string"},
                    ],
                },
                {
                    "name": "entity2",
                    "primary_key": "id2",
                    "fields": [
                        {"name": "id2", "type": "string"},
                        {
                            "name": "fk_field",
                            "type": "string",
                            "foreignKeys": [{"entity": "entity1"}],
                        },
                        {"name": "children", "type": "array", "item_type": {"entity": "entity3"}},
                    ],
                    "parents": [
                        {
                            "child_fk": "fk_field",
                            "parent_array": "children",
                        }
                    ],
                },
                {
                    "name": "entity3",
                    "primary_key": "id3",
                    "fields": [{"name": "id3", "type": "string"}],
                },
            ],
        }
    }

    is_valid, errors, _ = validator.validate(data)

    leafref_errors = [e for e in errors if "no target instance" in e or "Relative path resolution" in e]
    assert len(leafref_errors) == 0, (
        f"Should not have leafref resolution errors. Leafref errors: {leafref_errors}. "
        f"All errors: {errors}"
    )

    if not is_valid:
        non_leafref_errors = [
            e for e in errors if "no target instance" not in e and "Relative path resolution" not in e
        ]
        print(f"Validation failed but leafref resolution worked. Other errors: {non_leafref_errors}")
