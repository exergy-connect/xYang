"""Walk-local member names must reflect schema edits between validations (#263)."""

from xyang import parse_yang_string
from xyang.validator.document_validator import DocumentValidator


def test_member_name_cache_is_refreshed_between_walks():
    module = parse_yang_string('module m { namespace "urn:m"; prefix m; leaf old { type string; } }')
    validator = DocumentValidator(module)
    assert not validator.validate({'old': 'value'})
    module.find_statement('old').name = 'new'
    assert not validator.validate({'new': 'value'})
    assert any(error.code == 'unknown-field' for error in validator.validate({'old': 'value'}))


def test_absent_checks_are_refreshed_between_walks():
    module = parse_yang_string('module m { namespace "urn:m"; prefix m; leaf value { type string; } }')
    validator = DocumentValidator(module)
    assert not validator.validate({})
    module.find_statement('value').mandatory = True
    assert any(error.code == 'mandatory' for error in validator.validate({}))


def test_feature_results_are_reused_and_refreshed_for_json_schema(monkeypatch):
    """A restored schema evaluates each feature guard once per walk (#263)."""
    from xyang.json import generate_json_schema, parse_json_schema
    import xyang.validator.document_validator as document_validator

    source = parse_yang_string('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m; feature f;
      list item { key id; leaf id { type string; }
        leaf guarded { if-feature f; type string; }
      }
    }''')
    module = parse_json_schema(generate_json_schema(source).schema)
    validator = DocumentValidator(module, enabled_features_by_module={'m': set()})
    original = document_validator.stmt_if_features_satisfied
    calls = []

    def count(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(document_validator, 'stmt_if_features_satisfied', count)
    data = {'item': [{'id': 'a', 'guarded': 'x'}, {'id': 'b', 'guarded': 'y'}]}
    assert [error.code for error in validator.validate(data)] == ['if-feature', 'if-feature']
    assert len(calls) == 1
    module.find_statement('item').find_statement('guarded').if_features = ['not f']
    assert not validator.validate(data)
    assert len(calls) == 2


def test_compiled_plan_reuses_member_keys_for_list_entries(monkeypatch):
    """Member keys are compiled once per schema parent, not once per entry (#263)."""
    import xyang.validator.document_validator as document_validator

    module = parse_yang_string('''module m { namespace "urn:m"; prefix m;
      list item { key id; leaf id { type string; } leaf value { type string; } }
    }''')
    validator = DocumentValidator(module)
    original = document_validator.member_keys_cached
    calls = []

    def count(stmt, parent):
        calls.append((stmt.name, parent))
        return original(stmt, parent)

    monkeypatch.setattr(document_validator, 'member_keys_cached', count)
    assert not validator.validate({'item': [{'id': str(i), 'value': 'v'} for i in range(20)]})
    assert calls.count(('value', 'm')) == 1
    assert calls.count(('id', 'm')) == 1


def test_valid_leaf_does_not_build_diagnostic_path(monkeypatch):
    """A successful scalar check needs no error path; failures retain their pointer."""
    from xyang.validator.path_builder import PathBuilder

    module = parse_yang_string('module m { namespace "urn:m"; prefix m; leaf n { type uint8; } }')
    validator = DocumentValidator(module)
    calls = []
    original = PathBuilder.child

    def child(path, name, key=None):
        calls.append(name)
        return original(path, name, key)

    monkeypatch.setattr(PathBuilder, 'child', child)
    assert not validator.validate({'n': 1})
    assert calls == []
    errors = validator.validate({'n': 300})
    assert [(error.code, error.pointer) for error in errors] == [('range', '/n')]
    assert calls == ['n']
