"""Explicit convert paths are exact, while the default keeps .yang.json (#228)."""
import json
import sys

import pytest

from xyang.__main__ import main


@pytest.mark.parametrize('output', [None, 'catalog.schema.json', 'without-suffix', 'nested/custom.jsonld'])
def test_convert_output_path(tmp_path, monkeypatch, output):
    source = tmp_path / 'demo.yang'
    source.write_text('module demo { namespace "urn:demo"; prefix d; leaf name { type string; } }')
    args = ['xyang', 'convert', str(source)]
    target = tmp_path / (output or 'demo.yang.json')
    if output is not None:
        args += ['-o', str(target)]
    monkeypatch.setattr(sys, 'argv', args)
    assert main() == 0
    assert json.loads(target.read_text())['x-yang']['module'] == 'demo'
