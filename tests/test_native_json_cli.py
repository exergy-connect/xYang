"""Default validation is RFC 7951. --native-json accepts the dict-style repro."""

import json
import subprocess
import sys
from pathlib import Path

from xyang import parse_yang_string, validate

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


def test_library_default_rejects_native_repro():
    module = parse_yang_string(MODULE)
    rejected = validate(module, NATIVE)
    assert rejected["valid"] is False
    accepted = validate(module, NATIVE, native_json=True)
    assert accepted["valid"] is True
    assert accepted["errors"] == []


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
