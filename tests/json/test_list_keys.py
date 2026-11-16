"""List key requirements survive native JSON round trips without mandatory (#224)."""
import pytest

from xyang import generate_json_schema, parse_json_schema, parse_yang_string


@pytest.mark.parametrize("extra", [
    "",
    "leaf value { type string; mandatory true; }",
    "choice mode { leaf enabled { type boolean; } leaf label { type string; } }",
], ids=["keys-only", "mandatory-sibling", "choice-sibling"])
def test_list_keys_required_without_explicit_mandatory(extra):
    module = parse_yang_string('''module m {
      namespace "urn:m"; prefix m;
      list items { key "a b";
        leaf a { type string; } leaf b { type uint8; }
    ''' + extra + ' } }')
    schema = generate_json_schema(module)
    items = schema['properties']['items']['items']
    branches = items.get('oneOf', [items])
    for branch in branches:
        assert {'a', 'b'} <= set(items.get('required', []) + branch.get('required', []))
    restored = parse_json_schema(schema)
    assert generate_json_schema(restored) == schema
    lst = restored.statements[0]
    for leaf in lst.statements:
        if leaf.name in ('a', 'b'):
            assert not leaf.mandatory
