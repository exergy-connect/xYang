"""
Pattern substatement metadata (RFC 7950 §9.4.6): error-message, error-app-tag.

Parsed on ``YangTypeStmt``, surfaced in validation errors and in JSON Schema ``x-yang``.
"""

from __future__ import annotations

from xyang import parse_yang_string, YangValidator
from xyang.json import generate_json_schema, parse_json_schema
from xyang.json.schema_keys import JsonSchemaKey, XYangKey


def test_parse_stores_pattern_error_message_and_app_tag():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[0-9]+' {
        error-message "Must be decimal digits.";
        error-app-tag "t:bad-id";
      }
    }
  }
  container data-model {
    leaf x { type id; }
  }
}
"""
    module = parse_yang_string(yang)
    td = module.typedefs["id"]
    assert td.type is not None
    assert len(td.type.patterns) == 1
    assert td.type.patterns[0].pattern == "[0-9]+"
    assert td.type.patterns[0].error_message == "Must be decimal digits."
    assert td.type.patterns[0].error_app_tag == "t:bad-id"


def test_validate_uses_pattern_error_message_and_app_tag():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[0-9]+' {
        error-message "Must be decimal digits.";
        error-app-tag "t:bad-id";
      }
    }
  }
  container data-model {
    leaf x { type id; }
  }
}
"""
    module = parse_yang_string(yang)
    v = YangValidator(module)
    ok, errors, _warnings = v.validate({"data-model": {"x": "abc"}})
    assert not ok
    assert len(errors) >= 1
    joined = " ".join(errors)
    assert "Must be decimal digits." in joined
    assert "error-app-tag: t:bad-id" in joined


def test_json_schema_x_yang_carries_pattern_metadata():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[0-9]+' {
        error-message "Must be decimal digits.";
        error-app-tag "t:bad-id";
      }
    }
  }
  container data-model {
    leaf x { type id; }
  }
}
"""
    module = parse_yang_string(yang)
    schema = generate_json_schema(module)
    id_def = schema["$defs"]["id"]
    xy = id_def[JsonSchemaKey.X_YANG]
    assert xy[XYangKey.PATTERN_ERROR_MESSAGE] == "Must be decimal digits."
    assert xy[XYangKey.PATTERN_ERROR_APP_TAG] == "t:bad-id"


def test_json_roundtrip_restores_pattern_metadata_on_typedef():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[0-9]+' {
        error-message "Must be decimal digits.";
        error-app-tag "t:bad-id";
      }
    }
  }
  container data-model {
    leaf x { type id; }
  }
}
"""
    module = parse_yang_string(yang)
    schema = generate_json_schema(module)
    module2 = parse_json_schema(schema)
    td = module2.typedefs["id"]
    assert td.type is not None
    assert len(td.type.patterns) == 1
    assert td.type.patterns[0].error_message == "Must be decimal digits."
    assert td.type.patterns[0].error_app_tag == "t:bad-id"


def test_parse_stores_pattern_modifier_and_multiple_pattern_entries():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' {
        modifier invert-match;
        error-message "digits forbidden";
        error-app-tag "t:forbidden-digits";
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    td = module.typedefs["id"]
    assert td.type is not None
    assert len(td.type.patterns) == 2
    assert td.type.patterns[0].pattern == "[a-z]+"
    assert td.type.patterns[0].invert_match is False
    assert td.type.patterns[1].pattern == "[0-9]+"
    assert td.type.patterns[1].invert_match is True
    assert td.type.patterns[1].error_message == "digits forbidden"
    assert td.type.patterns[1].error_app_tag == "t:forbidden-digits"


def test_json_schema_emits_allof_and_string_patterns_for_invert_match():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' {
        modifier invert-match;
        error-message "digits forbidden";
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    schema = generate_json_schema(module)
    id_def = schema["$defs"]["id"]
    assert "allOf" in id_def
    xy = id_def[JsonSchemaKey.X_YANG]
    assert XYangKey.STRING_PATTERNS in xy
    assert len(xy[XYangKey.STRING_PATTERNS]) == 2
    assert xy[XYangKey.STRING_PATTERNS][1]["invert-match"] is True
    assert xy[XYangKey.STRING_PATTERNS][1]["pattern"] == "[0-9]+"


def test_json_roundtrip_restores_pattern_modifier_entries():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef id {
    type string {
      pattern '[a-z]+';
      pattern '[0-9]+' {
        modifier invert-match;
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    module2 = parse_json_schema(generate_json_schema(module))
    td = module2.typedefs["id"]
    assert td.type is not None
    assert len(td.type.patterns) == 2
    assert td.type.patterns[0].invert_match is False
    assert td.type.patterns[1].invert_match is True
