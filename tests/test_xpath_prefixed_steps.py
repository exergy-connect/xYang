"""Prefixed XPath steps resolve by module, also after the native JSON round trip (issue #152).

Shared cases: tests/cases/xpath/prefixed-*, tests/cases/references/leafref-prefixed.
"""

import copy
import json
from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_string
from xyang.errors import YangSyntaxError
from xyang.json import generate_json_schema, parse_json_schema
from xyang.parser.yang_parser import YangParser

CASES_DIR = Path(__file__).parent / "cases"
CASE = CASES_DIR / "xpath" / "prefixed-steps"
ROUND_TRIP_CASES = ["xpath/prefixed-steps", "xpath/prefixed-definition-site", "xpath/prefixed-table", "references/leafref-prefixed"]


def _load_case(case_dir: Path = CASE):
    spec = json.loads((case_dir / "case.json").read_text())
    parser = YangParser(include_path=(case_dir,))
    primary = (case_dir / spec["module"]).resolve()
    module = parser.parse_file(primary)
    parser._module_cache[primary] = module
    for sibling in sorted(case_dir.glob("*.yang")):
        if sibling.resolve() != primary:
            parser.parse_file(sibling)
    return module


@pytest.fixture(scope="module")
def schema():
    return generate_json_schema(_load_case())


def _round_trip_params():
    for case in ROUND_TRIP_CASES:
        for inst in json.loads((CASES_DIR / case / "case.json").read_text())["instances"]:
            yield pytest.param(case, inst, id=f"{case}:{inst['name']}")


def test_json_records_prefix_modules_and_qualifies_augmented_members(schema):
    sys_props = schema["properties"]["sys"]["properties"]
    assert {"name", "ext:name", "ext:tag", "ext:iref"} <= set(sys_props)
    assert sys_props["ext:tag"]["x-yang"]["must"][0]["xpath-prefixes"] == {"e": "ext", "mm": "m"}
    assert sys_props["ext:iref"]["x-yang"]["xpath-prefixes"] == {"mm": "m"}
    assert generate_json_schema(parse_json_schema(copy.deepcopy(schema))) == schema


@pytest.mark.parametrize("case,inst", list(_round_trip_params()))
def test_round_tripped_module_validates_like_the_yang(case, inst):
    schema = generate_json_schema(_load_case(CASES_DIR / case))
    assert generate_json_schema(parse_json_schema(copy.deepcopy(schema))) == schema
    result = YangValidator(parse_json_schema(copy.deepcopy(schema))).validate_detailed(
        inst["data"], native_json=inst.get("encoding") == "native"
    )
    assert sorted((e["path"], e["code"]) for e in result["errors"]) == sorted(
        (e["path"], e["code"]) for e in inst.get("errors", [])
    )
    assert result["valid"] is inst["valid"]


def test_json_without_a_recorded_map_binds_only_the_own_prefix():
    module = parse_yang_string(
        'module m { yang-version 1.1; namespace "urn:m"; prefix m;'
        " container top { leaf a { type string; must \"/m:top/m:b = 'y'\"; } leaf b { type string; } } }"
    )
    schema = generate_json_schema(module)
    must = schema["properties"]["top"]["properties"]["a"]["x-yang"]["must"][0]
    del must["xpath-prefixes"]
    assert YangValidator(parse_json_schema(copy.deepcopy(schema))).validate_detailed({"m:top": {"a": "x", "b": "y"}})[
        "valid"
    ]
    must["must"] = "/x:top/x:b = 'y'"
    with pytest.raises(YangSyntaxError, match="unknown prefix 'x'"):
        parse_json_schema(schema)


def test_prefixed_paths_failed_before_binding():
    """The regression: ``/m:top/m:x`` used to find nothing, so the leafref and must failed."""
    module = parse_yang_string(
        'module m { yang-version 1.1; namespace "urn:m"; prefix m; container top { leaf x { type string; }'
        ' leaf r { type leafref { path "/m:top/m:x"; } } leaf q { type string; must "/m:top/m:x = \'a\'"; } } }'
    )
    assert YangValidator(module).validate_detailed({"top": {"x": "a", "r": "a", "q": "z"}})["errors"] == []
