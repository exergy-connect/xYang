# Meta-Model Test Failures Analysis

**Date**: 2026-02-20  
**Last Updated**: 2026-02-20  
**Total Failing Tests**: 27  
**Total Tests**: 74  
**Pass Rate**: 63.5%

## Overview

This document clusters and analyzes the failing test cases in the meta-model test suite. Most failures appear to be **false negatives** - valid data being incorrectly rejected by the validator, rather than invalid data being incorrectly accepted.

---

## 1. Change ID Reference - ✅ FIXED (4 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_change_id_c_reference_valid` - Valid change ID in `c` field ✅
- `test_change_id_m_reference_valid` - Valid change IDs in `m` list ✅
- `test_change_id_c_reference_invalid` - Invalid change ID in `c` field should fail ✅
- `test_change_id_m_reference_invalid` - Invalid change ID in `m` list should fail ✅

**Root Cause (Fixed)**: The `must` constraints checking `../../changes[id = current()]` were applying the predicate to intermediate lists (like `entities`) instead of the final list (`changes`). The predicate `[id = current()]` was being evaluated on the wrong list, causing valid cases to fail and invalid cases to pass.

**Solution**: Modified `_evaluate_path_with_predicate` in `path_evaluator.py` to try the complete path first before trying individual steps. This ensures the predicate is applied to the final list (`changes`) rather than intermediate lists. Also fixed `_navigate_from_result` to handle empty predicate results correctly (return empty list instead of raising IndexError).

**Files Modified**:
- `xYang/xpath/path_evaluator.py` - Fixed predicate application order and empty result handling

---

## 2. Computed Fields - Operations - 7 tests

**Issue**: Valid computed field operations are being rejected, and invalid operations are not being caught.

### Tests:
- `test_computed_field_aggregation_operations_valid_minimum` - Valid minimum aggregation
- `test_computed_field_aggregation_operations_valid_multiple` - Valid multiple aggregation  
- `test_computed_field_aggregation_operations_invalid_too_few` - Invalid: too few fields (should fail)
- `test_computed_field_binary_operations_valid_exactly_two` - Valid: exactly 2 fields
- `test_computed_field_binary_operations_valid_subtraction` - Valid subtraction operation
- `test_computed_field_binary_operations_invalid_too_few` - Invalid: too few fields (should fail)
- `test_computed_field_binary_operations_invalid_too_many` - Invalid: too many fields (should fail)

**Root Cause**: The `must` constraints for computed field operation validation are not working correctly:
- Binary operations (add, subtraction) require exactly 2 fields
- Aggregation operations (min, max) require 2+ fields

**Expected Behavior**:
- Valid operations with correct field counts should pass
- Invalid operations with wrong field counts should fail

---

## 3. Computed Fields - References - 1 test

**Issue**: Valid computed field references are being rejected.

### Tests:
- `test_computed_field_reference_valid_same_entity` - Valid same-entity field reference

**Root Cause**: The `must` constraint checking field existence in computed field references is failing for valid cases.

**Expected Behavior**: Valid field references within the same entity should pass.

---

## 4. Computed Fields - Cross-Entity - 3 tests

**Issue**: Valid cross-entity computed field references are being rejected, and invalid cases are not being caught.

### Tests:
- `test_computed_field_cross_entity_foreign_key_valid` - Valid cross-entity reference
- `test_computed_field_cross_entity_foreign_key_invalid_no_foreign_key` - Invalid: no FK (should fail)
- `test_computed_field_reference_valid_cross_entity` - Valid cross-entity reference

**Root Cause**: The `must` constraint `count(../../../../fields[foreignKey/entity = current()]) = 1` is not evaluating correctly, or the foreign key relationship is not being found.

**Expected Behavior**:
- Valid cross-entity references with proper foreign keys should pass
- Invalid cross-entity references without foreign keys should fail

---

## 5. Entity Field Limit - 1 test

**Issue**: Valid entity with array fields excluded from count is being rejected.

### Tests:
- `test_entity_field_limit_valid_array_fields_excluded` - Valid: array fields excluded from 7-field limit

**Root Cause**: The `must` constraint `count(fields[type != 'array']) <= 7` is not correctly excluding array fields, or the `allow_unlimited_fields` check is not working.

**Expected Behavior**: Entities with 7 non-array fields plus array fields should pass (array fields excluded from count).

---

## 6. Name Underscore Limits - 4 tests

**Issue**: Valid names are being rejected, and invalid names are not being caught.

### Tests:
- `test_entity_name_underscore_limit_invalid_exceeds_default` - Invalid: exceeds limit (should fail)
- `test_field_name_underscore_limit_valid` - Valid field name
- `test_field_name_underscore_limit_valid_at_limit` - Valid at limit
- `test_field_name_underscore_limit_invalid_exceeds_default` - Invalid: exceeds limit (should fail)

**Root Cause**: The `must` constraint using `string-length(.) - string-length(translate(., '_', '')) <= ../../../max_name_underscores` is not evaluating correctly, or the path to `max_name_underscores` is incorrect.

**Expected Behavior**:
- Names within the underscore limit should pass
- Names exceeding the limit should fail

---

## 7. Date Constraints - 2 tests

**Issue**: Valid date constraint combinations are being rejected.

### Tests:
- `test_maxdate_valid_with_mindate` - Valid: maxDate with minDate
- `test_mindate_valid_with_maxdate` - Valid: minDate with maxDate

**Root Cause**: The `must` constraints checking date relationships (`minDate <= maxDate`) are failing for valid cases.

**Expected Behavior**: Valid date ranges where minDate <= maxDate should pass.

---

## 8. Parent Array - 2 tests

**Issue**: Valid parent array configurations are being rejected.

### Tests:
- `test_parent_array_exists_valid` - Valid: parent array exists
- `test_parent_array_type_valid` - Valid: parent array type

**Root Cause**: The `must` constraints for parent array validation are not evaluating correctly:
- `deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]` - checking array exists
- `deref(current())/../type = 'array'` - checking array type

**Expected Behavior**: Valid parent array references should pass.

---

## 9. Parents - All Valid Cases - 8 tests

**Issue**: **ALL** valid parents cases are failing. This is the largest cluster of failures.

### Tests:
- `test_parents_child_fk_foreign_key_valid` - Valid child FK
- `test_parents_field_name_matching_valid_cross_entity_matching` - Valid cross-entity matching
- `test_parents_field_name_matching_valid_self_referential` - Valid self-referential
- `test_parents_foreign_key_entity_exists_valid` - Valid FK entity exists
- `test_parents_foreign_key_field_exists_valid` - Valid FK field exists
- `test_parents_foreign_key_references_primary_key_valid` - Valid FK references PK
- `test_parents_primary_key_exists_valid` - Valid parent PK exists
- `test_parents_type_matching_valid` - Valid type matching

**Root Cause**: Multiple `must` constraints in the `list parents` definition are failing:
- `deref(current())/../foreignKey` - checking FK exists
- `deref(deref(current())/../foreignKey/entity)` - checking FK entity exists
- `deref(deref(current())/../foreignKey/entity)/../fields[name = ...]` - checking FK field exists
- `deref(deref(current())/../foreignKey/entity)/../primary_key` - checking parent PK exists
- `deref(deref(current())/../foreignKey/entity)/../primary_key[. = ...]` - checking FK references PK
- Type matching constraints

**Expected Behavior**: All valid parent relationships should pass validation.

---

## Summary

### Key Patterns

1. **False Negatives Dominant**: Most failures (23/27) are valid cases being incorrectly rejected
2. **XPath Evaluation Issues**: Many failures involve complex XPath expressions with `deref()` and path navigation
3. **Parents Validation Critical**: 8 failures in parents validation suggest a systemic issue with parent relationship validation
4. **Computed Fields Issues**: 11 failures related to computed fields suggest issues with field reference resolution

### Priority Areas

1. **High Priority**: Parents validation (8 failures) - all valid cases failing
2. **High Priority**: Computed fields (11 failures) - operations, references, cross-entity
3. **Medium Priority**: Name underscore limits (4 failures) - validation logic
4. **✅ FIXED**: Change ID reference - all 4 tests now passing

### Root Causes (Hypothesized)

1. **XPath `deref()` evaluation**: Complex `deref()` chains may not be resolving correctly
2. **Path navigation**: Relative paths (`../../`, `../`) may not be navigating correctly after `deref()`
3. **Context management**: The evaluation context may not be set correctly for nested structures
4. **Constraint evaluation order**: Some constraints may be evaluated before required data is available

### Recent Fixes

**2026-02-20**: Fixed Change ID Reference tests (Category 1)
- Issue: Predicate `[id = current()]` was being applied to intermediate lists instead of final list
- Solution: Modified `_evaluate_path_with_predicate` to try complete path first
- Result: All 4 change ID reference tests now passing

### Next Steps

1. Investigate XPath `deref()` evaluation in `deref_evaluator.py`
2. Review path navigation after `deref()` in `evaluator.py`
3. Check context management in `constraint_validator.py`
4. Add debug logging to trace constraint evaluation for failing cases
5. Focus on parents validation first (largest cluster - 8 failures)

---

## Test Execution

To run all meta-model tests:
```bash
pytest tests/meta-model/ -v
```

To run a specific test:
```bash
pytest tests/meta-model/test_parents_type_matching.py::test_parents_type_matching_valid -v
```

To run tests for a specific category:
```bash
# All parents tests
pytest tests/meta-model/test_parents_*.py -v

# All computed field tests
pytest tests/meta-model/test_computed_field_*.py -v
```
