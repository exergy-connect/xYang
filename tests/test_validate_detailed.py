"""validate_detailed issue JSON matches the TypeScript validator for the same module (#79)."""

import json
from pathlib import Path

from xyang import YangValidator, parse_yang_file

CASE = Path(__file__).parent / "cases" / "structure" / "structured-errors"
MODULE = CASE / "m.yang"

# Identical to ts/test/validate_detailed.test.ts.
EXPECTED = {
    "range": [
        {
            "code": "range",
            "path": "/top/u8",
            "message": "Value 300 exceeds maximum 255",
            "severity": "error",
        }
    ],
    "unknown-field": [
        {
            "code": "unknown-field",
            "path": "/top/items/0/x",
            "message": "Unknown field 'x'",
            "severity": "error",
        }
    ],
    "must": [
        {
            "code": "must",
            "path": "/top/n",
            "message": "must constraint not satisfied on 'n'",
            "expression": ". >= 0",
            "severity": "error",
        }
    ],
}


def _errors(data):
    module = parse_yang_file(MODULE)
    result = YangValidator(module).validate_detailed(data)
    assert result["valid"] is False
    assert result["warnings"] == []
    return result["errors"]


def test_range_unknown_field_and_must_match_typescript():
    case = json.loads((CASE / "case.json").read_text())
    by_code = {inst["errors"][0]["code"]: inst["data"] for inst in case["instances"]}
    assert _errors(by_code["range"]) == EXPECTED["range"]
    assert _errors(by_code["unknown-field"]) == EXPECTED["unknown-field"]
    assert _errors(by_code["must"]) == EXPECTED["must"]
