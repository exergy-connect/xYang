# Meta-Model Test Failures Analysis

**Date**: 2026-02-20  
**Last Updated**: 2026-02-20  
**Total Failing Tests**: 10  
**Total Tests**: 74  
**Pass Rate**: 86.5% (64 passing, 10 failing)

## Overview

This document clusters and analyzes the failing test cases in the meta-model test suite. All failures are **false negatives** - valid data being incorrectly rejected by the validator, rather than invalid data being incorrectly accepted.

All 10 failing tests are related to **parents/parent array validation**, indicating a systemic issue with parent relationship validation that has been partially addressed but still needs fixes for predicates and comparisons.

---

## Clustered Test Failures

### Category 1: Parents - Path Navigation with Predicates (5 tests)

**Status**: 🔄 **IN PROGRESS** - 0 passing, 5 failing

**Root Cause**: Path navigation with predicates (e.g., `fields[name = ...]`, `primary_key[. = ...]`) is not working correctly when navigating from nodes returned by `deref()`.

#### Tests:
- `test_parents_foreign_key_field_exists_valid` - Valid: FK field exists
  - Constraint: `deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]`
  - Issue: Predicate `[name = ...]` not evaluating correctly
  
- `test_parents_foreign_key_references_primary_key_valid` - Valid: FK references PK
  - Constraint: `deref(deref(current())/../foreignKey/entity)/../primary_key[. = deref(current())/../foreignKey/field]`
  - Issue: Predicate `[. = ...]` not evaluating correctly
  
- `test_parents_primary_key_exists_valid` - Valid: parent PK exists
  - Constraint: `deref(deref(current())/../foreignKey/entity)/../primary_key`
  - Issue: Path navigation after nested `deref()` may not be working correctly
  
- `test_parents_foreign_key_entity_exists_valid` - Valid: FK entity exists
  - Constraint: `deref(deref(current())/../foreignKey/entity)`
  - Issue: May be related to predicate evaluation in other constraints
  
- `test_parents_child_fk_foreign_key_valid` - Valid: child FK has foreignKey
  - Constraint: `deref(current())/../foreignKey`
  - Issue: May be failing due to other constraint failures

**Expected Behavior**: All valid parent relationship validations should pass.

**Progress Made**:
- ✅ Fixed `deref(current())/../foreignKey` - path navigation from field node works
- ✅ Fixed nested `deref()` calls - `deref(deref(current())/../foreignKey/entity)` resolves entity nodes
- ✅ Fixed path navigation from `deref()` nodes - `../field` is treated as `./field`
- ❌ Still need to fix predicate evaluation: `fields[name = ...]` and `primary_key[. = ...]`

---

### Category 2: Parents - Comparison Operations (3 tests)

**Status**: 🔄 **IN PROGRESS** - 0 passing, 3 failing

**Root Cause**: Comparison operations in constraints (e.g., `=`, `!=`) are not working correctly, especially when comparing values from `deref()` nodes or in predicate contexts.

#### Tests:
- `test_parents_type_matching_valid` - Valid: type matching
  - Constraint: `deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type`
  - Issue: Comparison `=` between field types not working correctly
  
- `test_parents_field_name_matching_valid_cross_entity_matching` - Valid: cross-entity field name matching
  - Constraint: `deref(current())/../foreignKey/entity = ../../name or current() = deref(deref(current())/../foreignKey/entity)/../primary_key[1]`
  - Issue: Comparison operations in `or` expression not working correctly
  
- `test_parents_field_name_matching_valid_self_referential` - Valid: self-referential field name matching
  - Constraint: `deref(current())/../foreignKey/entity = ../../name or current() = deref(deref(current())/../foreignKey/entity)/../primary_key[1]`
  - Issue: Comparison operations in `or` expression not working correctly

**Expected Behavior**: All valid comparison operations should pass.

**Progress Made**:
- ✅ Fixed `None` handling in comparisons - `None` comparisons return `False`
- ❌ Still need to fix comparison operations with values from `deref()` nodes
- ❌ Still need to fix comparison operations in predicate contexts

---

### Category 3: Parent Array - Path Navigation with Predicates (2 tests)

**Status**: 🔄 **IN PROGRESS** - 0 passing, 2 failing

**Root Cause**: Parent array constraints depend on `child_fk` constraints being fully working, and also involve path navigation with predicates.

#### Tests:
- `test_parent_array_exists_valid` - Valid: parent array exists
  - Constraint: `deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]`
  - Issue: Predicate `[name = current()]` not evaluating correctly
  
- `test_parent_array_type_valid` - Valid: parent array type
  - Constraint: `deref(current())/../type = 'array'`
  - Issue: May be related to path navigation or comparison

**Expected Behavior**: Valid parent array references should pass validation.

**Progress Made**:
- ✅ Fixed `None` handling - when `deref()` returns `None`, path navigation returns `[]`
- ✅ Fixed path navigation from `deref()` nodes - `../field` is treated as `./field`
- ❌ Still need to fix predicate evaluation: `fields[name = current()]`
- ❌ Depends on `child_fk` constraints being fully working

---

## Summary

### Key Patterns

1. **False Negatives Dominant**: All failures (10/10) are valid cases being incorrectly rejected
2. **XPath Evaluation Issues**: All failures involve complex XPath expressions with `deref()`, path navigation, and predicates/comparisons
3. **Parents Validation Critical**: All 10 failures are in parents/parent array validation
4. **✅ FIXED**: Computed fields - all 11 tests now passing
5. **✅ FIXED**: Date constraints - all 10 tests now passing
6. **✅ FIXED**: Name underscore limits - all 8 tests now passing
7. **✅ FIXED**: Entity field limit - all 5 tests now passing
8. **✅ FIXED**: Change ID reference - all 4 tests now passing
9. **🔄 IN PROGRESS**: Parents validation - 0 passing, 8 failing (nested deref() fixed, predicates/comparisons remaining)
10. **🔄 IN PROGRESS**: Parent array - 0 passing, 2 failing (depends on parents validation)

### Priority Areas

1. **High Priority**: Parents validation - Path navigation with predicates (5 failures)
   - Fix predicate evaluation: `fields[name = ...]` and `primary_key[. = ...]`
   - Ensure `current()` in predicates refers to correct context
   
2. **High Priority**: Parents validation - Comparison operations (3 failures)
   - Fix comparison operations with values from `deref()` nodes
   - Fix comparison operations in predicate contexts
   
3. **High Priority**: Parent array (2 failures)
   - Depends on parents validation being fully working
   - Fix predicate evaluation: `fields[name = current()]`

### Root Causes (Identified)

1. **✅ FIXED**: XPath `deref()` evaluation - Nested `deref()` calls now resolve correctly
2. **✅ FIXED**: Path navigation - Relative paths (`../`) now navigate correctly after `deref()` (treated as `./` when navigating from a node)
3. **🔄 IN PROGRESS**: Predicate evaluation - Path navigation with predicates (e.g., `fields[name = ...]`) still needs fixes
4. **🔄 IN PROGRESS**: Comparison operations - Comparison operations in constraints (e.g., `primary_key[. = ...]`) still need fixes
5. **Context management**: The evaluation context may not be set correctly for predicates and comparisons

### Recent Fixes

**2026-02-20**: Fixed nested `deref()` calls and path navigation (Parents validation - partial fix)
- Issue: Nested `deref()` calls like `deref(deref(current())/../foreignKey/entity)` were not resolving entity nodes correctly. Path navigation from `deref()` nodes (e.g., `../primary_key`) was not working correctly.
- Solution:
  - Fixed nested `deref()` to handle string values from path navigation - when `deref(current())/../foreignKey/entity` returns a string, `deref()` now correctly resolves it using the leafref path from the schema
  - Fixed path navigation from `deref()` nodes - `../field` is now treated as `./field` when navigating from a node (whether or not `stored_path` is set)
  - Fixed `None` handling - when `deref()` returns `None`, path navigation with `/` now returns `[]` (empty node-set) instead of `None`
  - Enhanced path evaluation to try evaluating from the node itself as data first, then fall back to stored_path navigation
- Files Modified:
  - `xYang/xpath/deref_evaluator.py` - Added handling for string values from path navigation in nested `deref()` calls
  - `xYang/xpath/evaluator.py` - Fixed path navigation from `deref()` nodes to treat `../field` as `./field`, added `None` handling for path navigation
- Result: 
  - `deref(current())/../foreignKey` - ✅ FIXED
  - `deref(deref(current())/../foreignKey/entity)` - ✅ FIXED (nested deref working)
  - `deref(deref(current())/../foreignKey/entity)/../primary_key` - ✅ FIXED
  - Path navigation with predicates (e.g., `fields[name = ...]`) - ❌ Still needs fixes
  - Comparison operations in constraints - ❌ Still needs fixes

**2026-02-20**: Fixed Date Constraints tests
- Issue: Date comparisons using `number(.) <= number(../maxDate)` converted date strings to `NaN`, causing all comparisons to fail.
- Solution: Changed date comparison from `number()` to direct string comparison (`. <= ../maxDate`) in `meta-model.yang`
- Result: All 10 date constraint tests now passing

**2026-02-20**: Fixed Name Underscore Limits tests
- Issue: Field name constraint path was incorrect and default value retrieval wasn't working.
- Solution: Fixed XPath path in `meta-model.yang` and added default value retrieval from YANG schema
- Result: All 8 name underscore limit tests now passing

**2026-02-20**: Fixed Entity Field Limit tests
- Issue: Test data incorrectly had 8 non-array fields, exceeding the limit of 7
- Solution: Modified test data to have 7 non-array fields plus 1 array field
- Result: All 5 entity field limit tests now passing

**2026-02-20**: Fixed Computed Fields tests
- Issue: Container `must` statements were not being parsed, and XPath paths for computed field references were incorrect
- Solution: Added `must_statements` attribute to `YangContainerStmt`, registered `container:must` handler, fixed XPath paths
- Result: All 11 computed field tests now passing

**2026-02-20**: Fixed Change ID Reference tests
- Issue: Predicate `[id = current()]` was being applied to intermediate lists instead of final list
- Solution: Modified `_evaluate_path_with_predicate` to try complete path first
- Result: All 4 change ID reference tests now passing

### Next Steps

1. **Fix predicate evaluation**: Investigate path navigation with predicates (e.g., `fields[name = ...]`)
   - Review `path_evaluator.py` for predicate evaluation issues
   - Check if predicates are correctly evaluated when navigating from `deref()` nodes
   - Verify that `current()` in predicates refers to the correct context
   - Test cases: `test_parents_foreign_key_field_exists_valid`, `test_parents_foreign_key_references_primary_key_valid`, `test_parent_array_exists_valid`

2. **Fix comparison operations**: Investigate comparison operations in constraints (e.g., `primary_key[. = ...]`)
   - Review comparison evaluation in `comparison_evaluator.py`
   - Check if comparisons work correctly with values from `deref()` nodes
   - Verify type coercion for comparisons
   - Test cases: `test_parents_type_matching_valid`, `test_parents_field_name_matching_valid_*`

3. **Fix parent array validation**: Review parent array `must` constraints
   - Check `deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]` evaluation
   - Check `deref(current())/../type = 'array'` evaluation
   - These depend on parents validation being fully working

---

## Test Execution

To run all meta-model tests:
```bash
pytest tests/meta-model/ -v
```

To run a specific test:
```bash
pytest tests/meta-model/test_parents_primary_key_exists.py::test_parents_primary_key_exists_valid -v
```

To run tests for a specific category:
```bash
# All parents tests
pytest tests/meta-model/test_parents_*.py -v

# All parent array tests
pytest tests/meta-model/test_parent_array_*.py -v
```

---

## Detailed Constraint Analysis

### Parents Validation Constraints

All constraints are in `list parents` → `leaf child_fk`:

1. **`deref(current())/../foreignKey`** ✅ FIXED
   - Validates that the child_fk field has a foreignKey definition
   - Status: Working correctly

2. **`deref(deref(current())/../foreignKey/entity)`** ✅ FIXED
   - Validates that the foreignKey entity exists
   - Status: Nested deref() now working correctly

3. **`deref(deref(current())/../foreignKey/entity)/../primary_key`** ✅ FIXED
   - Validates that the parent entity has a primary key
   - Status: Path navigation from entity node working correctly

4. **`deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]`** ❌ FAILING
   - Validates that the foreignKey field exists in the parent entity
   - Issue: Predicate `[name = ...]` not evaluating correctly

5. **`deref(deref(current())/../foreignKey/entity)/../primary_key[. = deref(current())/../foreignKey/field]`** ❌ FAILING
   - Validates that the foreignKey field references the parent's primary key
   - Issue: Predicate `[. = ...]` not evaluating correctly

6. **`deref(current())/../foreignKey/entity = ../../name or current() = deref(deref(current())/../foreignKey/entity)/../primary_key[1]`** ❌ FAILING
   - Validates field name matching for cross-entity relationships
   - Issue: Comparison operations in `or` expression not working correctly

7. **`deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type`** ❌ FAILING
   - Validates that child FK field type matches parent PK field type
   - Issue: Comparison `=` between field types not working correctly

### Parent Array Constraints

All constraints are in `list parents` → `leaf parent_array`:

1. **`deref(current())/../type = 'array'`** ❌ FAILING
   - Validates that the parent_array field is of type 'array'
   - Issue: May be related to path navigation or comparison

2. **`deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]`** ❌ FAILING
   - Validates that parent_array field exists in the parent entity
   - Issue: Predicate `[name = current()]` not evaluating correctly
