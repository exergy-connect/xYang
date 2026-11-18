"""CLI --native-json accepts dict-style instance data. Library encoding: tests/cases/encoding/dict-style."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

MODULE = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type int64; }
    }
    leaf marker { type empty; }
  }
}
"""

NATIVE = {"top": {"interface": {"eth0": {"mtu": 1500}}, "marker": None}}


def test_cli_native_json_flag(tmp_path: Path):
    yang = tmp_path / "m.yang"
    data = tmp_path / "data.json"
    yang.write_text(MODULE, encoding="utf-8")
    data.write_text(json.dumps(NATIVE), encoding="utf-8")
    base = [sys.executable, "-m", "xyang", "validate", str(yang), str(data)]
    rejected = subprocess.run([*base, "--format", "json"], capture_output=True, text=True, check=False)
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["valid"] is False
    accepted = subprocess.run([*base, "--native-json", "--format", "json"], capture_output=True, text=True, check=False)
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["valid"] is True


def test_yaml_defaults_to_native_encoding_and_json_output(tmp_path: Path):
    pytest.importorskip("yaml")
    yang = tmp_path / "m.yang"
    data = tmp_path / "data.YAML"
    yang.write_text(MODULE, encoding="utf-8")
    data.write_text("top:\n  interface:\n    eth0:\n      mtu: 1500\n  marker: null\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "xyang", "validate", str(yang), str(data)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"valid": True, "errors": []}


def test_yaml_explicit_text_format_is_respected(tmp_path: Path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    from xyang.__main__ import main

    yang = tmp_path / "m.yang"
    data = tmp_path / "data.yml"
    yang.write_text(MODULE, encoding="utf-8")
    data.write_text("top:\n  marker: null\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["xyang", "validate", "--format", "text", str(yang), str(data)])
    assert main() == 0
    assert capsys.readouterr().out == "Valid.\n"


def test_yaml_invalid_result_is_json(tmp_path: Path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    from xyang.__main__ import main

    yang = tmp_path / "m.yang"
    data = tmp_path / "data.yml"
    yang.write_text(MODULE, encoding="utf-8")
    data.write_text("top:\n  unexpected: true\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["xyang", "validate", str(yang), str(data)])
    assert main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["errors"][0]["path"] == "/top/unexpected"


def test_yaml_rpc_uses_native_parameters(tmp_path: Path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    from xyang.__main__ import main

    yang = tmp_path / "m.yang"
    data = tmp_path / "params.yaml"
    yang.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      rpc run { input { leaf count { type int64; } } }
    }''', encoding="utf-8")
    data.write_text("count: 42\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["xyang", "validate", "--rpc", "run", str(yang), str(data)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "errors": []}


def test_json_file_keeps_text_and_rfc7951_defaults(tmp_path: Path, monkeypatch, capsys):
    from xyang.__main__ import main

    yang = tmp_path / "m.yang"
    data = tmp_path / "data.json"
    yang.write_text(MODULE, encoding="utf-8")
    data.write_text(json.dumps({"top": {"marker": [None]}}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["xyang", "validate", str(yang), str(data)])
    assert main() == 0
    assert capsys.readouterr().out == "Valid.\n"
