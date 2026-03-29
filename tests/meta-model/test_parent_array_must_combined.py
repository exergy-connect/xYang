"""
Test for parent_array must constraint on combined (consolidated) data model.

Reproduces the xFrame basecase scenario: when validating a combined model
(consolidated=True), the parent_array leafref must see the referenced field's
type/array branch. With path caching enabled, this can incorrectly fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.validator.document_validator import DocumentValidator


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def _str_field(name: str, description: str) -> dict:
    return {"name": name, "description": description, "type": {"primitive": "string"}}


def _combined_basecase_data():
    """Combined data model equivalent to xFrame basecase (company, department, employee)."""
    return {
        "data-model": {
            "name": "Base Case Test Model",
            "version": "25.11.29.1",
            "author": "Test",
            "description": "Hierarchical org sample.",
            "consolidated": True,
            "entities": [
                {
                    "name": "company",
                    "description": "Company root.",
                    "primary_key": "company_id",
                    "fields": [
                        _str_field("company_id", "Company PK."),
                        _str_field("company_name", "Name."),
                        {
                            "name": "departments",
                            "description": "Nested departments.",
                            "type": {"array": {"entity": "department"}},
                        },
                    ],
                },
                {
                    "name": "department",
                    "description": "Department under company.",
                    "primary_key": "department_id",
                    "fields": [
                        _str_field("department_id", "Dept PK."),
                        _str_field("department_name", "Dept name."),
                        {
                            "name": "company_id",
                            "description": "FK to company via departments array.",
                            "type": {
                                "primitive": "string",
                                "foreignKeys": [{"entity": "company", "parent_array": "departments"}],
                            },
                        },
                        {
                            "name": "employees",
                            "description": "Nested employees.",
                            "type": {"array": {"entity": "employee"}},
                        },
                    ],
                },
                {
                    "name": "employee",
                    "description": "Employee under department.",
                    "primary_key": "employee_id",
                    "fields": [
                        _str_field("employee_id", "Employee PK."),
                        _str_field("employee_name", "Employee name."),
                        {
                            "name": "manager_id",
                            "description": "Self-FK via reports array.",
                            "type": {
                                "primitive": "string",
                                "foreignKeys": [{"entity": "employee", "parent_array": "reports"}],
                            },
                        },
                        {
                            "name": "department_id",
                            "description": "FK to department via employees array.",
                            "type": {
                                "primitive": "string",
                                "foreignKeys": [{"entity": "department", "parent_array": "employees"}],
                            },
                        },
                        _str_field("email", "Email."),
                        {
                            "name": "reports",
                            "description": "Nested reports (employees).",
                            "type": {"array": {"entity": "employee"}},
                        },
                    ],
                },
            ],
        }
    }


def test_parent_array_must_combined_with_cache(meta_model):
    """Combined model with parent_array refs must validate when cache is enabled."""
    data = _combined_basecase_data()
    validator = YangValidator(meta_model)
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, (
        "Combined model with valid parent_array refs (company.departments, "
        "department.employees, employee.reports) should pass. "
        f"Errors: {errors}"
    )


def test_parent_array_must_combined_without_cache(meta_model):
    """Same combined model with cache disabled must validate."""
    data = _combined_basecase_data()
    doc_validator = DocumentValidator(meta_model)
    errors = doc_validator.validate(data, cache=False)
    assert not errors, (
        f"With cache=False, combined model should pass parent_array must. Errors: {errors}"
    )
