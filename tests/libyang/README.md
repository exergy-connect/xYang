# Libyang Tests

This directory contains libyang versions of failing tests to compare behavior between our XPath evaluator and libyang's implementation.

## Setup

Install libyang-python:
```bash
pip install libyang
```

Note: libyang also requires the libyang C library to be installed on the system.

## Running Tests

```bash
cd tests/libyang
python3 test_parents_child_fk_foreign_key.py
```

## Test Files

- `test_parents_child_fk_foreign_key.py` - Tests the `deref(current())/../foreignKey` constraint
  - Corresponds to `test_parents_child_fk_foreign_key_valid` in the meta-model tests
  - Validates that child_fk field has a foreignKey definition
  - Status: ✅ Both libyang and xYang pass

- `test_parents_type_matching.py` - Tests the type matching constraint
  - Constraint: `deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type`
  - Corresponds to `test_parents_type_matching_valid` in the meta-model tests
  - Validates that child FK field type matches parent PK field type
  - Involves: nested deref() calls, path navigation with predicates, comparison operations
  - Status: ✅ Both libyang and xYang pass

## Purpose

These tests help identify whether:
1. Our XPath evaluator has bugs (if libyang passes but we fail)
2. The YANG schema constraints are correct (if both fail or both pass)
3. There are differences in how libyang and our evaluator interpret XPath expressions
