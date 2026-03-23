# Meta-Model YANG Constraint Tests

This directory contains comprehensive test files for all `must` statement constraints in `meta-model.yang`.

## Test Files

Each test file covers a specific `must` constraint with both positive (valid) and negative (invalid) test cases:

1. **test_entity_name_underscore_limit.py** - Entity name underscore limit constraint
2. **test_primary_key_reference.py** - Primary key must reference existing field
3. **test_entity_field_limit.py** - Entity field limit (7 non-array fields max)
4. **test_field_name_underscore_limit.py** - Field name underscore limit constraint
5. **test_foreign_key_field_exists.py** - Foreign key field must exist in referenced entity
6. **test_foreign_key_references_primary_key.py** - Foreign key must reference primary key
7. **test_mindate_constraints.py** - minDate type and range constraints
8. **test_maxdate_constraints.py** - maxDate type and range constraints
9. **test_required_field_no_default.py** - Required field cannot have default
10. **test_array_item_type_foreign_key.py** - Array item_type foreignKey constraints
11. **test_computed_field_reference.py** - Computed field reference existence
12. **test_computed_field_cross_entity_foreign_key.py** - Cross-entity computed field requires foreign key
13. **test_must.py** (`test_computed_*_two_fields_*`) - Computed `fields` list: at least 2 entries (`count(fields) >= 2`, plus list `min-elements 2`)
14. **test_parents_child_fk_foreign_key.py** - Parents child_fk must have foreignKey
15. **test_parents_foreign_key_entity_exists.py** - Parents foreign key entity must exist
16. **test_parents_foreign_key_field_exists.py** - Parents foreign key field must exist
17. **test_parents_primary_key_exists.py** - Parent entity must have primary key
18. **test_parents_foreign_key_references_primary_key.py** - Parents foreign key must reference primary key
19. **test_parents_field_name_matching.py** - Parents field name matching for cross-entity
20. **test_parents_type_matching.py** - Parents type matching constraint
21. **test_parent_array_type.py** - Parent array must be array type
22. **test_parent_array_exists.py** - Parent array must exist in parent entity
23. **test_change_id_reference.py** - Change ID (c and m) must reference valid change

## Test Structure

Each test file follows this pattern:
- Uses a `meta_model` fixture that loads the meta-model.yang file
- Contains `test_*_valid` functions for positive test cases
- Contains `test_*_invalid` functions for negative test cases
- Each test validates both the constraint passing and failing scenarios

## Running Tests

Run all meta-model tests:
```bash
pytest tests/meta-model/ -v
```

Run a specific test file:
```bash
pytest tests/meta-model/test_entity_name_underscore_limit.py -v
```

Run with coverage:
```bash
pytest tests/meta-model/ --cov=xYang.validators --cov-report=term-missing
```
