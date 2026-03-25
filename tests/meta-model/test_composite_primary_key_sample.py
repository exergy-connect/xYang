"""Validate composite primary key + FK sample (tests/data/composite_primary_key_sample.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_META_MODEL_YANG = REPO_ROOT / "examples" / "new-meta-model.yang"
SAMPLE_YAML = REPO_ROOT / "tests" / "data" / "composite_primary_key_sample.yaml"


@pytest.fixture
def new_meta_model_module():
    assert NEW_META_MODEL_YANG.is_file(), f"Missing {NEW_META_MODEL_YANG}"
    return parse_yang_file(str(NEW_META_MODEL_YANG))


def _load_sample() -> dict:
    yaml = pytest.importorskip("yaml", reason="pip install -e '.[dev]' (PyYAML)")
    assert SAMPLE_YAML.is_file(), f"Missing {SAMPLE_YAML}"
    tree = yaml.safe_load(SAMPLE_YAML.read_text(encoding="utf-8"))
    assert isinstance(tree, dict)
    return {"data-model": tree}


def test_composite_primary_key_sample_validates(new_meta_model_module):
    """Full YAML validates against new-meta-model.yang."""
    data = _load_sample()
    validator = YangValidator(new_meta_model_module)
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"errors={errors} warnings={warnings}"


def test_composite_primary_key_points_at_composite_field(new_meta_model_module):
    """primary_key references a field whose type resolves to composite (xFrame-style)."""
    data = _load_sample()
    validator = YangValidator(new_meta_model_module)
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, errors

    entities = {e["name"]: e for e in data["data-model"]["entities"]}
    loc = entities["location"]
    assert loc["primary_key"] == "location_key"

    loc_fields = {f["name"]: f for f in loc["fields"]}
    assert loc_fields["location_key"]["type"]["definition"] == "location_key_ref"

    defs = {d["name"]: d for d in loc["field_definitions"]}
    assert defs["location_key_ref"]["type"]["composite"][0]["name"] == "region_code"
    assert defs["location_key_ref"]["type"]["composite"][1]["name"] == "location_id"

    wh = entities["warehouse"]
    assert wh["primary_key"] == "warehouse_id"
    wh_fields = {f["name"]: f for f in wh["fields"]}
    at_loc = wh_fields["at_location"]["type"]
    assert at_loc["definition"] == "location_key_ref"
    assert at_loc["foreignKeys"][0]["entity"] == "location"
