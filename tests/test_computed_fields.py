"""
Standalone tests for computed field validation.

Uses an inline subset of the meta-model YANG: only the parts needed for
computed fields (data-model, entities, fields, computed, foreignKeys).
Same structure and must expressions as the meta-model; no external file.
"""

import pytest
from xyang import parse_yang_string, YangValidator


# Minimal YANG for computed-field tests only: entities, fields, computed, foreignKeys.
META_MODEL_SUBSET = """
module meta-model {
  yang-version 1.1;
  namespace "urn:xframe:meta-model";
  prefix "mm";

  typedef field-type {
    type enumeration {
      enum string; enum integer; enum number; enum boolean; enum array;
      enum datetime; enum date; enum composite;
    }
  }

  container data-model {
    leaf consolidated { type boolean; default false; }
    leaf allow_unlimited_fields { type boolean; default false; }
    list entities {
      key name;
      min-elements 1;
      leaf name { type string; mandatory true; }
      leaf primary_key {
        type string;
        mandatory true;
        must "../fields[name = current()]" {
          error-message "primary_key must reference an existing field";
        }
      }
      list fields {
        key name;
        min-elements 1;
        leaf name { type string; mandatory true; }
        leaf type { type field-type; mandatory true; }
        list foreignKeys {
          key entity;
          leaf entity {
            type leafref { path "/data-model/entities/name"; require-instance true; }
            mandatory true;
            must "/data-model/consolidated = false() or /data-model/entities[name = string(current())]" {
              error-message "Foreign key entity must exist in the data model";
            }
          }
        }
        container computed {
          presence " ";
          leaf operation {
            type enumeration {
              enum add; enum subtraction; enum multiplication; enum division;
              enum min; enum max;
            }
            mandatory true;
          }
          list fields {
            key field;
            min-elements 2;
            max-elements 100;
            leaf field {
              type string;
              mandatory true;
              must "/data-model/consolidated = false() or ((not(../entity) and count(../../../../../fields[name = current()]) = 1) or (../entity and count(deref(../entity)/../fields[name = current()]) = 1))" {
                error-message "Computed field reference must exist in the specified entity (or current entity if not specified)";
              }
            }
            leaf entity {
              type leafref { path "/data-model/entities/name"; require-instance true; }
              must "/data-model/consolidated = false() or count(../../../../../fields[foreignKeys/entity = current()]) = 1" {
                error-message "Cross-entity computed field references require a foreign key field in the current entity that references the target entity";
              }
            }
          }
          must "count(fields) >= 2" {
            error-message "Computed operation requires at least 2 field references";
          }
        }
      }
      must "/data-model/consolidated = true() or ../../allow_unlimited_fields = 'true' or ../../allow_unlimited_fields = true() or count(fields[type != 'array']) <= 7" {
        error-message "Entity has more than 7 non-array fields.";
      }
    }
  }
}
"""


def _validator():
    return YangValidator(parse_yang_string(META_MODEL_SUBSET))


def test_computed_field_missing_field_same_entity():
    """Computed field referencing non-existent field in same entity should fail."""
    validator = _validator()
    invalid_data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "test_entity",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "integer"},
                        {
                            "name": "invalid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"field": "field1"},
                                    {"field": "nonexistent"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Validation should fail for missing field reference"
    assert any("exist" in e.lower() or "field" in e.lower() for e in errors), f"Errors: {errors}"


def test_computed_field_valid_same_entity():
    """Valid computed field with fields in same entity should pass."""
    validator = _validator()
    valid_data = {
        "data-model": {
            "entities": [
                {
                    "name": "test_entity",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "integer"},
                        {"name": "field2", "type": "integer"},
                        {
                            "name": "valid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"field": "field1"},
                                    {"field": "field2"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Valid data should pass. Errors: {errors}"


def test_computed_field_missing_field_cross_entity():
    """Computed field referencing non-existent field in cross-entity should fail."""
    validator = _validator()
    invalid_data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "integer"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "entity1_id", "type": "integer", "foreignKeys": [{"entity": "entity1"}]},
                        {
                            "name": "invalid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"entity": "entity1", "field": "nonexistent"},
                                    {"field": "field1"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Validation should fail for missing field in cross-entity reference"


def test_computed_field_cross_entity_no_foreign_key():
    """Cross-entity computed field reference without foreign key should fail."""
    validator = _validator()
    invalid_data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "field1", "type": "integer"}]
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "invalid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"entity": "entity1", "field": "field1"},
                                    {"field": "field1"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid


def test_computed_field_cross_entity_with_foreign_key():
    """Valid cross-entity computed field with foreign key should pass."""
    validator = _validator()
    valid_data = {
        "data-model": {
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "field1", "type": "integer"}]
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "entity1_id", "type": "integer", "foreignKeys": [{"entity": "entity1"}]},
                        {
                            "name": "valid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"entity": "entity1", "field": "field1"},
                                    {"field": "entity1_id"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Valid data should pass. Errors: {errors}"


def test_computed_field_wrong_field_count_binary():
    """Binary operation with wrong field count should fail."""
    validator = _validator()
    invalid_data = {
        "data-model": {
            "entities": [
                {
                    "name": "e1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a", "type": "integer"},
                        {
                            "name": "bad",
                            "type": "integer",
                            "computed": {"operation": "subtraction", "fields": [{"field": "a"}]}
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Validation should fail for binary operation with wrong field count"
    assert any("2" in e or "binary" in e.lower() or "field" in e.lower() for e in errors), f"Errors: {errors}"


def test_computed_field_valid_aggregation():
    """Valid aggregation (e.g. max) with multiple fields should pass."""
    validator = _validator()
    valid_data = {
        "data-model": {
            "entities": [
                {
                    "name": "e1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "f1", "type": "integer"},
                        {"name": "f2", "type": "integer"},
                        {"name": "f3", "type": "integer"},
                        {
                            "name": "valid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "max",
                                "fields": [
                                    {"field": "f1"},
                                    {"field": "f2"},
                                    {"field": "f3"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Valid aggregation should pass. Errors: {errors}"
