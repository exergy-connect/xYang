"""Schema resource IDs are independent of YANG namespaces (#227)."""
import json
import sys

import pytest

from xyang import generate_json_schema, parse_json_schema, parse_yang_string
from xyang.json import schema_to_yang_json
from xyang.__main__ import main


@pytest.fixture(scope='module')
def module():
    return parse_yang_string('module m { namespace "urn:m"; prefix m; leaf name { type string; } }')


@pytest.mark.parametrize('schema_id', [None, 'https://example.invalid/m.schema.json', ''])
def test_schema_id(module, schema_id):
    schema = generate_json_schema(module, schema_id=schema_id).schema
    assert schema['$id'] == ('urn:m' if schema_id is None else schema_id)
    assert schema['x-yang']['namespace'] == 'urn:m'
    assert parse_json_schema(schema).namespace == 'urn:m'
    assert json.loads(schema_to_yang_json(module, schema_id=schema_id)) == schema
    assert generate_json_schema(module).schema['$id'] == 'urn:m'


def test_cli_schema_id(tmp_path, monkeypatch):
    source = tmp_path / 'm.yang'
    source.write_text('module m { namespace "urn:m"; prefix m; }')
    target = tmp_path / 'published.json'
    monkeypatch.setattr(sys, 'argv', ['xyang', 'convert', str(source), '-o', str(target),
                                    '--schema-id', 'https://example.invalid/m.json'])
    assert main() == 0
    schema = json.loads(target.read_text())
    assert schema['$id'] == 'https://example.invalid/m.json'
    assert schema['x-yang']['namespace'] == 'urn:m'
