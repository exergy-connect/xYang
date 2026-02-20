# Meta-Model Test Failures Analysis

**Date**: 2026-02-20  
**Last Updated**: 2026-02-20  
**Total Failing Tests**: 10  
**Total Tests**: 84  
**Pass Rate**: 88.1%

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

## 2. Computed Fields - Operations - ✅ FIXED (7 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_computed_field_aggregation_operations_valid_minimum` - Valid minimum aggregation ✅
- `test_computed_field_aggregation_operations_valid_multiple` - Valid multiple aggregation ✅
- `test_computed_field_aggregation_operations_invalid_too_few` - Invalid: too few fields (should fail) ✅
- `test_computed_field_binary_operations_valid_exactly_two` - Valid: exactly 2 fields ✅
- `test_computed_field_binary_operations_valid_subtraction` - Valid subtraction operation ✅
- `test_computed_field_binary_operations_invalid_too_few` - Invalid: too few fields (should fail) ✅
- `test_computed_field_binary_operations_invalid_too_many` - Invalid: too many fields (should fail) ✅

**Root Cause (Fixed)**: The `must` constraints for computed field operation validation are now working correctly. The fix involved:
1. Adding `must_statements` attribute to `YangContainerStmt` to support `must` constraints on containers
2. Registering `container:must` handler in the parser
3. Fixing the path for computed field references from `../../../../fields` to `../../../../../fields`

**Solution**: Container `must` statements are now properly parsed and evaluated. The computed container's `must` constraints for field count validation (binary operations require exactly 2 fields, aggregation operations require 2+ fields) are now correctly evaluated.

**Files Modified**:
- `xYang/ast.py` - Added `must_statements` to `YangContainerStmt`
- `xYang/parser.py` - Registered `container:must` handler
- `xYang/statement_parsers.py` - Improved `parse_must` to handle unknown statements
- `examples/meta-model.yang` - Fixed path for computed field references

---

## 3. Computed Fields - References - ✅ FIXED (1 test)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_computed_field_reference_valid_same_entity` - Valid same-entity field reference ✅

**Root Cause (Fixed)**: The `must` constraint checking field existence in computed field references was using an incorrect path (`../../../../fields` instead of `../../../../../fields`).

**Solution**: Corrected the XPath path in `meta-model.yang` from `../../../../fields` to `../../../../../fields` to correctly reference the entity's fields list.

**Files Modified**:
- `examples/meta-model.yang` - Fixed XPath path for computed field references

---

## 4. Computed Fields - Cross-Entity - ✅ FIXED (3 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_computed_field_cross_entity_foreign_key_valid` - Valid cross-entity reference ✅
- `test_computed_field_cross_entity_foreign_key_invalid_no_foreign_key` - Invalid: no FK (should fail) ✅
- `test_computed_field_reference_valid_cross_entity` - Valid cross-entity reference ✅

**Root Cause (Fixed)**: The `must` constraint `count(../../../../../fields[foreignKey/entity = current()]) = 1` is now evaluating correctly after fixing the path and ensuring container `must` statements are properly parsed.

**Solution**: Fixed the XPath path and ensured container `must` statements are correctly parsed and evaluated.

**Files Modified**:
- `examples/meta-model.yang` - Fixed XPath path for cross-entity computed field references
- `xYang/ast.py`, `xYang/parser.py`, `xYang/statement_parsers.py` - Fixed container `must` parsing

---

## 5. Entity Field Limit - ✅ FIXED (5 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_entity_field_limit_valid_within_limit` - Valid: within limit ✅
- `test_entity_field_limit_valid_array_fields_excluded` - Valid: array fields excluded from 7-field limit ✅
- `test_entity_field_limit_valid_allow_unlimited_true` - Valid: allow_unlimited_fields=true ✅
- `test_entity_field_limit_invalid_exceeds_limit` - Invalid: exceeds limit (should fail) ✅
- `test_entity_field_limit_invalid_exceeds_limit_with_arrays` - Invalid: exceeds limit with arrays (should fail) ✅

**Root Cause (Fixed)**: The test data for `test_entity_field_limit_valid_array_fields_excluded` had 8 non-array fields, exceeding the limit of 7. The `allow_unlimited_fields` logic was working correctly.

**Solution**: Modified test data to have 7 non-array fields plus 1 array field, which correctly passes the validation.

**Files Modified**:
- `tests/meta-model/test_entity_field_limit.py` - Fixed test data for array field exclusion test

---

## 6. Name Underscore Limits - ✅ FIXED (8 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_entity_name_underscore_limit_valid` - Valid entity name ✅
- `test_entity_name_underscore_limit_valid_at_limit` - Valid at limit ✅
- `test_entity_name_underscore_limit_valid_custom_limit` - Valid with custom limit ✅
- `test_entity_name_underscore_limit_invalid_exceeds_default` - Invalid: exceeds limit (should fail) ✅
- `test_entity_name_underscore_limit_invalid_exceeds_custom` - Invalid: exceeds custom limit ✅
- `test_field_name_underscore_limit_valid` - Valid field name ✅
- `test_field_name_underscore_limit_valid_at_limit` - Valid at limit ✅
- `test_field_name_underscore_limit_invalid_exceeds_default` - Invalid: exceeds limit (should fail) ✅

**Root Cause (Fixed)**: The `must` constraint for field names was using an incorrect path (`../../../max_name_underscores` instead of `../../../../max_name_underscores`). From `entities[0]/fields[0]/name`, we need to go up 4 levels to reach `data-model`, not 3.

**Solution**: 
1. Fixed the XPath path in `meta-model.yang` from `../../../max_name_underscores` to `../../../../max_name_underscores` for field names
2. Fixed None handling consistency in comparison functions
3. Added default value retrieval from YANG schema (`_get_default_value_from_schema_path`)
4. Fixed field name tests to use correct `primary_key` values

**Files Modified**:
- `examples/meta-model.yang` - Fixed XPath path for field name underscore limit constraint
- `xYang/xpath/utils.py` - Fixed None handling consistency
- `xYang/xpath/path_evaluator.py` - Added default value retrieval from schema
- `tests/meta-model/test_field_name_underscore_limit.py` - Fixed primary_key values

---

## 7. Date Constraints - ✅ FIXED (10 tests)

**Status**: ✅ **FIXED** - All tests passing

### Tests:
- `test_mindate_valid_date_type` - Valid: minDate with date type ✅
- `test_mindate_valid_datetime_type` - Valid: minDate with datetime type ✅
- `test_mindate_valid_with_maxdate` - Valid: minDate <= maxDate ✅
- `test_mindate_invalid_wrong_type` - Invalid: wrong type (should fail) ✅
- `test_mindate_invalid_greater_than_maxdate` - Invalid: minDate > maxDate (should fail) ✅
- `test_maxdate_valid_date_type` - Valid: maxDate with date type ✅
- `test_maxdate_valid_datetime_type` - Valid: maxDate with datetime type ✅
- `test_maxdate_valid_with_mindate` - Valid: maxDate >= minDate ✅
- `test_maxdate_invalid_wrong_type` - Invalid: wrong type (should fail) ✅
- `test_maxdate_invalid_less_than_mindate` - Invalid: maxDate < minDate (should fail) ✅

**Root Cause (Fixed)**: The `must` constraints were using `number(.) <= number(../maxDate)` which converted date strings to `NaN`, making comparisons always fail. Additionally, field names in tests had underscores that exceeded the limit.

**Solution**:
1. Changed date comparison from `number(.) <= number(../maxDate)` to `. <= ../maxDate` (direct string comparison works for YYYY-MM-DD format)
2. Fixed field names in tests to remove underscores (`startdate`, `enddate`, `daterange` instead of `start_date`, `end_date`, `date_range`)
3. Enhanced NaN handling in comparison functions to handle date string comparisons

**Files Modified**:
- `examples/meta-model.yang` - Changed date comparison from `number()` to direct string comparison
- `xYang/xpath/utils.py` - Enhanced NaN handling for date comparisons
- `tests/meta-model/test_mindate_constraints.py` - Fixed field names
- `tests/meta-model/test_maxdate_constraints.py` - Fixed field names

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

1. **False Negatives Dominant**: All failures (10/10) are valid cases being incorrectly rejected
2. **XPath Evaluation Issues**: All failures involve complex XPath expressions with `deref()` and path navigation
3. **Parents Validation Critical**: 10 failures in parents/parent array validation suggest a systemic issue with parent relationship validation
4. **✅ FIXED**: Computed fields - all 11 tests now passing
5. **✅ FIXED**: Date constraints - all 10 tests now passing
6. **✅ FIXED**: Name underscore limits - all 8 tests now passing
7. **✅ FIXED**: Entity field limit - all 5 tests now passing

### Priority Areas

1. **High Priority**: Parents validation (8 failures) - all valid cases failing
2. **High Priority**: Parent array (2 failures) - all valid cases failing
3. **✅ FIXED**: Change ID reference - all 4 tests now passing
4. **✅ FIXED**: Computed fields - all 11 tests now passing (operations, references, cross-entity)
5. **✅ FIXED**: Date constraints - all 10 tests now passing
6. **✅ FIXED**: Name underscore limits - all 8 tests now passing
7. **✅ FIXED**: Entity field limit - all 5 tests now passing

### Root Causes (Hypothesized)

1. **XPath `deref()` evaluation**: Complex `deref()` chains may not be resolving correctly
2. **Path navigation**: Relative paths (`../../`, `../`) may not be navigating correctly after `deref()`
3. **Context management**: The evaluation context may not be set correctly for nested structures
4. **Constraint evaluation order**: Some constraints may be evaluated before required data is available

### Recent Fixes

**2026-02-20**: Fixed Date Constraints tests (Category 7)
- Issue: Date comparisons using `number(.) <= number(../maxDate)` converted date strings to `NaN`, causing all comparisons to fail. Also, field names in tests had underscores exceeding the limit.
- Solution: 
  - Changed date comparison from `number()` to direct string comparison (`. <= ../maxDate`) in `meta-model.yang`
  - Fixed field names in tests to remove underscores
  - Enhanced NaN handling in comparison functions
- Files Modified: 
  - `examples/meta-model.yang` - Changed date comparison expressions
  - `xYang/xpath/utils.py` - Enhanced NaN handling for date comparisons
  - `tests/meta-model/test_mindate_constraints.py` - Fixed field names
  - `tests/meta-model/test_maxdate_constraints.py` - Fixed field names
- Result: All 10 date constraint tests now passing

**2026-02-20**: Fixed Name Underscore Limits tests (Category 6)
- Issue: Field name constraint path was incorrect (`../../../max_name_underscores` instead of `../../../../max_name_underscores`), and default value retrieval wasn't working for field names
- Solution:
  - Fixed XPath path in `meta-model.yang` from `../../../` to `../../../../` for field names
  - Fixed None handling consistency in comparison functions
  - Added default value retrieval from YANG schema
  - Fixed field name tests to use correct `primary_key` values
- Files Modified:
  - `examples/meta-model.yang` - Fixed XPath path for field name underscore limit
  - `xYang/xpath/utils.py` - Fixed None handling consistency
  - `xYang/xpath/path_evaluator.py` - Added default value retrieval from schema
  - `tests/meta-model/test_field_name_underscore_limit.py` - Fixed primary_key values
- Result: All 8 name underscore limit tests now passing

**2026-02-20**: Fixed None handling consistency in comparison functions
- Issue: `compare_equal` and `compare_less_equal` handled `None` differently (`None == None` returned `True`, but `None <= None` returned `False`)
- Solution: Made both functions consistent - both return `False` when either operand is `None`, aligning with XPath semantics where empty sequences don't compare
- Files Modified: `xYang/xpath/utils.py` - Fixed `compare_equal` to check for `None` before fast path
- Result: Consistent None handling across all comparison operators

**2026-02-20**: Added default value retrieval from YANG schema
- Issue: When `max_name_underscores` is missing from data, path evaluation returns `None` instead of using schema default (2)
- Solution: Added `_get_default_value_from_schema_path` method to retrieve default values from YANG schema when paths return `None`
- Files Modified: `xYang/xpath/path_evaluator.py` - Added default value lookup in `get_path_value`
- Result: Default values are now correctly retrieved from schema when paths are missing in data

**2026-02-20**: Fixed Entity Field Limit tests (Category 5)
- Issue: Test data incorrectly had 8 non-array fields, exceeding the limit of 7
- Solution: Modified test data to have 7 non-array fields plus 1 array field
- Result: All 5 entity field limit tests now passing (including `allow_unlimited_fields` test)

**2026-02-20**: Fixed Computed Fields tests (Categories 2, 3, 4)
- Issue: Container `must` statements were not being parsed, and XPath paths for computed field references were incorrect
- Solution: 
  - Added `must_statements` attribute to `YangContainerStmt` in `ast.py`
  - Registered `container:must` handler in `parser.py`
  - Improved `parse_must` to handle unknown statements in `statement_parsers.py`
  - Fixed XPath path from `../../../../fields` to `../../../../../fields` in `meta-model.yang`
- Result: All 11 computed field tests now passing (operations, references, cross-entity)

**2026-02-20**: Fixed Change ID Reference tests (Category 1)
- Issue: Predicate `[id = current()]` was being applied to intermediate lists instead of final list
- Solution: Modified `_evaluate_path_with_predicate` to try complete path first
- Result: All 4 change ID reference tests now passing

### Next Steps

1. **Focus on parents validation**: Investigate parents validation (10 failures - all remaining failures)
   - Review `deref_evaluator.py` for `deref()` evaluation issues
   - Check path navigation after `deref()` in `evaluator.py`
   - Verify context management in `constraint_validator.py`
   - Add debug logging to trace constraint evaluation for failing cases
2. **Investigate parent array validation**: Review parent array `must` constraints
   - Check `deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]` evaluation
   - Check `deref(current())/../type = 'array'` evaluation

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
