"""Exported annotation policy agrees with validation, including optional choices (#225)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from xyang import YangValidator, generate_json_schema, parse_json_schema, parse_yang_string, validate
from xyang.json import schema_to_yang_json


@pytest.fixture(scope='module')
def module():
    return parse_yang_string('''module m { namespace "urn:m"; prefix m;
      leaf name { type string; mandatory true; }
      container top { list items { key id; leaf id { type string; } } }
      container mode { choice mode { leaf a { type string; } leaf b { type string; } } }
    }''')


@pytest.mark.parametrize('allow_jsonld,allow_json_schema', [(True,True), (False,True), (True,False), (False,False)])
def test_annotation_export_policy(module, allow_jsonld, allow_json_schema):
    jsonschema = pytest.importorskip('jsonschema')
    opts = dict(allow_jsonld=allow_jsonld, allow_json_schema=allow_json_schema)
    schema = generate_json_schema(module, **opts).schema
    expected = ({'^@[A-Za-z]+$'} if allow_jsonld else set()) | ({r'^\$[A-Za-z]+$'} if allow_json_schema else set())
    nodes = [schema, schema['properties']['top'], schema['properties']['top']['properties']['items']['items']]
    for node in nodes:
        assert set(node.get('patternProperties', {})) == expected
        assert node['additionalProperties'] is False
    data = {'name':'ok','@context':{},'$schema':None,'top':{'items':[{'id':'a','@id':7,'$id':{}}]},'mode':{'@id':'urn:mode','$comment':False}}
    assert jsonschema.Draft202012Validator(schema).is_valid(data) == (allow_jsonld and allow_json_schema)
    # The annotation-only optional choice selects the empty branch.
    assert jsonschema.Draft202012Validator(schema).is_valid({'name':'ok','mode':{'@id':'urn:mode'}}) == allow_jsonld
    assert generate_json_schema(parse_json_schema(schema), **opts).schema == schema
    assert json.loads(schema_to_yang_json(module, **opts)) == schema


def test_validation_options_are_per_call_and_do_not_mutate(module):
    data = {'name':'ok','@context':{'opaque':{'missing':'not walked'}}}
    before = json.dumps(data)
    validator = YangValidator(module)
    assert validator.validate(data)[0]
    assert not validator.validate_detailed(data, allow_jsonld=False)['valid']
    assert validator.validate_detailed(data)['valid']
    assert not validate(module, data, allow_jsonld=False)['valid']
    assert json.dumps(data) == before


def test_annotation_tables_are_current():
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, str(root/'tools/generate_annotation_families.py'), '--check'], check=True)
