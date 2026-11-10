"""One-call xyang.validate returns validate_detailed's dict (#82)."""

from xyang import parse_yang_string, validate

_MODULE = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    leaf name { type string; }
  }
}
"""


def test_validate_path_accepts_valid_instance(tmp_path):
    yang = tmp_path / "m.yang"
    yang.write_text(_MODULE, encoding="utf-8")
    result = validate(yang, {"top": {"name": "example"}})
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []


def test_validate_module_reports_structured_error():
    module = parse_yang_string(_MODULE)
    result = validate(module, {"top": {"missing": 1}})
    assert result["valid"] is False
    assert result["warnings"] == []
    assert result["errors"] == [
        {
            "code": "unknown-field",
            "path": "/top/missing",
            "message": "Unknown field 'missing'",
            "severity": "error",
        }
    ]
