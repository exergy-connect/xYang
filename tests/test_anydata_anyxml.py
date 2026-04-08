"""anydata / anyxml: parse, validate arbitrary JSON values, JSON Schema round-trip."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangAnydataStmt, YangAnyxmlStmt
from xyang.json import generate_json_schema, parse_json_schema
from xyang.validator.document_validator import DocumentValidator


def _module():
    return parse_yang_string(
        """
module adax {
  yang-version 1.1;
  namespace "urn:adax";
  prefix adax;
  container data-model {
    anydata payload { description "free-form"; }
    anyxml legacy { mandatory true; }
    leaf tag { type string; }
  }
}
"""
    )


def test_parse_anydata_anyxml_ast():
    m = _module()
    dm = m.find_statement("data-model")
    assert dm is not None
    names = {s.name: type(s).__name__ for s in dm.statements}
    assert names["payload"] == "YangAnydataStmt"
    assert names["legacy"] == "YangAnyxmlStmt"
    legacy = next(s for s in dm.statements if s.name == "legacy")
    assert isinstance(legacy, YangAnyxmlStmt)
    assert legacy.mandatory is True


def test_validate_accepts_arbitrary_json_under_anydata_anyxml():
    m = _module()
    v = DocumentValidator(m)
    data = {
        "data-model": {
            "payload": {"nested": [1, 2, None], "ok": True},
            "legacy": "plain string is fine",
            "tag": "x",
        }
    }
    assert v.validate(data) == []


def test_validate_mandatory_anyxml_missing():
    m = _module()
    v = DocumentValidator(m)
    data = {"data-model": {"tag": "x"}}
    errs = v.validate(data)
    assert len(errs) == 1
    assert "anyxml" in errs[0].message.lower()
    assert "legacy" in errs[0].message


def test_generate_parse_json_schema_roundtrip_kinds():
    m = _module()
    schema = generate_json_schema(m)
    dm_prop = schema["properties"]["data-model"]
    props = dm_prop["properties"]
    assert props["payload"]["x-yang"]["type"] == "anydata"
    assert props["legacy"]["x-yang"]["type"] == "anyxml"
    assert "type" in props["payload"]
    assert isinstance(props["payload"]["type"], list)

    m2 = parse_json_schema(schema)
    dm2 = m2.find_statement("data-model")
    assert dm2 is not None
    by_name = {s.name: s for s in dm2.statements}
    assert isinstance(by_name["payload"], YangAnydataStmt)
    assert isinstance(by_name["legacy"], YangAnyxmlStmt)
    assert by_name["legacy"].mandatory is True
