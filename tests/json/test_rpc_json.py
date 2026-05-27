"""Round-trip module-level ``rpc`` / ``input`` / ``output`` in yang.json (generate → parse)."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangInputStmt, YangLeafStmt, YangOutputStmt, YangRpcStmt
from xyang.json import generate_json_schema, parse_json_schema, schema_to_yang_json
from xyang.json.schema_keys import XYangTypeValue


_RPC_YANG = """
module example-rpc {
  yang-version 1.1;
  namespace "urn:example:rpc";
  prefix erpc;

  rpc reboot {
    input {
      leaf delay-seconds {
        type uint16;
      }
    }
    output {
      leaf status-message {
        type string;
      }
    }
  }
}
"""


def test_rpc_emitted_under_x_yang_rpcs_and_round_trips():
    mod = parse_yang_string(_RPC_YANG)
    schema = generate_json_schema(mod)

    rpcs = schema["x-yang"]["rpcs"]
    assert "reboot" in rpcs
    reboot = rpcs["reboot"]
    assert reboot["x-yang"]["type"] == XYangTypeValue.RPC

    delay = reboot["input"]["properties"]["delay-seconds"]
    assert delay["x-yang"]["type"] == "leaf"
    assert "builtin-type" not in delay["x-yang"]
    assert delay["type"] == "integer"
    assert delay["minimum"] == 0
    assert delay["maximum"] == 65535

    msg = reboot["output"]["properties"]["status-message"]
    assert msg["x-yang"]["type"] == "leaf"
    assert msg["type"] == "string"

    mod2 = parse_json_schema(schema)
    reboot2 = mod2.find_statement("reboot")
    assert isinstance(reboot2, YangRpcStmt)
    assert reboot2.name == "reboot"

    inp = reboot2.find_statement("input")
    assert isinstance(inp, YangInputStmt)
    delay_leaf = inp.find_statement("delay-seconds")
    assert isinstance(delay_leaf, YangLeafStmt)
    assert delay_leaf.type is not None
    assert delay_leaf.type.name == "uint16"

    out = reboot2.find_statement("output")
    assert isinstance(out, YangOutputStmt)
    msg_leaf = out.find_statement("status-message")
    assert isinstance(msg_leaf, YangLeafStmt)
    assert msg_leaf.type is not None
    assert msg_leaf.type.name == "string"


def test_schema_to_yang_json_includes_rpcs(tmp_path):
    mod = parse_yang_string(_RPC_YANG)
    out_file = tmp_path / "example-rpc.yang.json"
    text = schema_to_yang_json(mod, output_path=out_file)
    assert out_file.exists()
    assert '"rpcs"' in text
    loaded = parse_json_schema(out_file.read_text())
    assert loaded.find_statement("reboot") is not None
