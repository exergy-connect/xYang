"""
Test for parent_array must constraint on combined (consolidated) data model.

Reproduces the xFrame basecase scenario: when validating a combined model
(consolidated=True), the must constraint

  /data-model/entities[name = ../entity]/fields[name = current()]/type = 'array'

must correctly resolve the referenced entity's field (e.g. company.departments,
department.employees, employee.reports) and see type 'array'. With path caching
enabled, this can incorrectly fail (cached path result from different context).
"""

import pytest
from pathlib import Path

from xyang import YangValidator, parse_yang_file
from xyang.validator.document_validator import DocumentValidator


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def _combined_basecase_data():
    """Combined data model equivalent to xFrame basecase (company, department, employee).

    Each parent_array references a field that exists on the referenced entity
    and has type 'array'.
    """
    return {
        "data-model": {
            "name": "Base Case Test Model",
            "version": "25.11.29.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "company",
                    "primary_key": "company_id",
                    "fields": [
                        {"name": "company_id", "type": "string"},
                        {"name": "company_name", "type": "string"},
                        {
                            "name": "departments",
                            "type": "array",
                            "item_type": {"entity": "department"},
                        },
                    ],
                },
                {
                    "name": "department",
                    "primary_key": "department_id",
                    "fields": [
                        {"name": "department_id", "type": "string"},
                        {"name": "department_name", "type": "string"},
                        {
                            "name": "company_id",
                            "type": "string",
                            "foreignKeys": [
                                {"entity": "company", "parent_array": "departments"}
                            ],
                        },
                        {
                            "name": "employees",
                            "type": "array",
                            "item_type": {"entity": "employee"},
                        },
                    ],
                },
                {
                    "name": "employee",
                    "primary_key": "employee_id",
                    "fields": [
                        {"name": "employee_id", "type": "string"},
                        {"name": "employee_name", "type": "string"},
                        {
                            "name": "manager_id",
                            "type": "string",
                            "foreignKeys": [
                                {"entity": "employee", "parent_array": "reports"}
                            ],
                        },
                        {
                            "name": "department_id",
                            "type": "string",
                            "foreignKeys": [
                                {"entity": "department", "parent_array": "employees"}
                            ],
                        },
                        {"name": "email", "type": "string"},
                        {
                            "name": "reports",
                            "type": "array",
                            "item_type": {"entity": "employee"},
                        },
                    ],
                },
            ],
        }
    }


def test_parent_array_must_combined_with_cache(meta_model):
    """Combined model with parent_array refs must validate when cache is enabled.

    Reproduces the xFrame failure: validation fails with
    'Parent array field must be of type array' when path cache is used, because
    the must path /data-model/entities[name=../entity]/fields[name=current()]/type
    is context-dependent (current(), ../entity) but cached by path string only.
    This test asserts that validation passes with cache=True once the bug is fixed.
    """
    data = _combined_basecase_data()
    validator = YangValidator(meta_model)
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, (
        "Combined model with valid parent_array refs (company.departments, "
        "department.employees, employee.reports) should pass. "
        f"Errors: {errors}"
    )


def test_parent_array_must_combined_without_cache(meta_model):
    """Same combined model with cache disabled must validate.

    Documents that the data is valid: with cache=False the parent_array must
    constraint evaluates correctly.
    """
    data = _combined_basecase_data()
    doc_validator = DocumentValidator(meta_model)
    errors = doc_validator.validate(data, cache=False)
    assert not errors, (
        "With cache=False, combined model should pass parent_array must. "
        f"Errors: {errors}"
    )
