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
