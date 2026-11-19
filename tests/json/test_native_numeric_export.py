"""Native export describes numeric 64-bit values without losing YANG types (#226)."""
import json
import sys

import pytest

from xyang import generate_json_schema, parse_json_schema
from xyang.parser import YangParser
from xyang.json import schema_to_yang_json
from xyang.__main__ import main

YANG = '''module m { namespace "urn:m"; prefix m;
  typedef resistance { type decimal64 { fraction-digits 3; range "0..100"; } }
  leaf signed { type int64; }
  leaf unsigned { type uint64; }
  leaf ohms { type decimal64 { fraction-digits 3; range "0..100"; } default "4.32"; }
  leaf slots { type int64 { range "1..3 | 10"; } }
  leaf alias { type resistance; }
  leaf-list values { type resistance; }
  leaf mixed { type union { type int64; type boolean; } }
  leaf ref { type leafref { path "/signed"; require-instance false; } }
}'''


@pytest.fixture(scope='module')
def module():
    return YangParser(expand_uses=False).parse_string(YANG)


@pytest.fixture(scope='module', params=[False, True], ids=['rfc7951', 'native'])
def exported(module, request):
    return request.param, generate_json_schema(module, native_json=request.param).schema


@pytest.mark.parametrize('name,value', [('signed',42),('unsigned',42),('ohms',4.32),('slots',10),
                                       ('alias',4.32),('values',[4.32]),('mixed',42),('ref',42)])
def test_numeric_encoding(module, exported, name, value):
    jsonschema = pytest.importorskip('jsonschema')
    native, schema = exported
    validator = jsonschema.Draft202012Validator(schema)
    encoded = value if native else ([str(x) for x in value] if isinstance(value,list) else str(value))
    assert validator.is_valid({name:encoded})
    other = ([str(x) for x in value] if isinstance(value,list) else str(value)) if native else value
    assert not validator.is_valid({name:other})
    assert generate_json_schema(parse_json_schema(schema), native_json=native).schema == schema
    assert json.loads(schema_to_yang_json(module, native_json=native)) == schema
    assert generate_json_schema(module).schema['properties']['signed']['type'] == 'string'


@pytest.mark.parametrize('name,value', [('unsigned',-1),('ohms',4.3211),('ohms',101),('slots',5)])
def test_native_numeric_constraints(module, name, value):
    jsonschema = pytest.importorskip('jsonschema')
    assert not jsonschema.Draft202012Validator(generate_json_schema(module,native_json=True).schema).is_valid({name:value})


def test_cli_native_export(tmp_path, monkeypatch):
    source = tmp_path/'m.yang'
    source.write_text(YANG)
    target = tmp_path/'native.json'
    monkeypatch.setattr(sys,'argv',['xyang','convert','--native-json',str(source),'-o',str(target)])
    assert main() == 0
    schema = json.loads(target.read_text())
    assert schema['properties']['signed']['type'] == 'integer'
    assert schema['properties']['ohms']['multipleOf'] == 0.001
