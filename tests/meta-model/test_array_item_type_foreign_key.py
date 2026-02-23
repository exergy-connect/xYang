"""
Test for array item_type foreignKey constraints.

Note: The YANG model's item_type/foreignKeys only has an 'entity' leaf, not a 'field' leaf.
The constraints for field existence and primary key matching are not currently enforced
for item_type foreignKeys. These tests verify the current behavior.
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_array_item_type_foreign_key_valid(meta_model):
    """Test that array item_type foreignKey with valid field and primary key passes."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {
                            "name": "parents",
                            "type": "array",
                            "item_type": {
                                "entity": "parent",
                                "foreignKeys": [{"entity": "parent"}]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Array item_type foreignKey with valid reference should pass. Errors: {errors}"


