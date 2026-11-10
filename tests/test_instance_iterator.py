"""The same instance yields the same iterator tree in RFC 7951 and native mode, except pointers."""

from xyang import parse_yang_string
from xyang.encoding.instance import iter_instance

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

RFC = {"m:top": {"interface": [{"name": "eth0", "mtu": "1500"}], "marker": [None]}}
NATIVE = {"top": {"interface": {"eth0": {"mtu": 1500}}, "marker": None}}


def _shape(node):
    value = node.value if node.kind in ("leaf", "leaf-list-item", "anydata") else None
    return (
        node.kind,
        None if node.stmt is None else node.stmt.name,
        value,
        tuple(_shape(child) for child in node.children),
    )


def _pointers(node):
    found = [node.pointer]
    for child in node.children:
        found.extend(_pointers(child))
    return found


def _leaf(nodes, name):
    for node in nodes:
        if node.kind == "leaf" and node.stmt is not None and node.stmt.name == name:
            return node
        found = _leaf(node.children, name)
        if found is not None:
            return found
    return None


def test_repro_trees_match_except_pointer():
    module = parse_yang_string(MODULE)
    rfc = list(iter_instance(RFC, module, native_json=False))
    native = list(iter_instance(NATIVE, module, native_json=True))
    assert [_shape(node) for node in rfc] == [_shape(node) for node in native]
    assert _pointers(rfc[0]) != _pointers(native[0])
    assert _leaf(rfc, "mtu").value == 1500
    assert _leaf(native, "mtu").value == 1500
    assert _leaf(rfc, "name").value == "eth0"
    assert _leaf(native, "name").value == "eth0"
    assert _leaf(rfc, "marker").value is None
    assert _leaf(native, "marker").value is None
    assert _leaf(rfc, "mtu").pointer == "/m:top/interface/0/mtu"
    assert _leaf(native, "mtu").pointer == "/top/interface/eth0/mtu"
