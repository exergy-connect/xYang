"""Coverage for prefixed node names in non-refine path-bearing statements."""

from __future__ import annotations

import pytest

from xyang import parse_yang_string
from xyang.ast import YangLeafStmt
from xyang.errors import YangSyntaxError
from xyang.parser.yang_parser import YangParser
from xyang.xpath.ast import BinaryOpNode, FunctionCallNode, PathNode


def _collect_path_steps(ast_node) -> list[str]:
    """Collect all PathNode step names from an XPath AST subtree."""
    out: list[str] = []
    if ast_node is None:
        return out
    if isinstance(ast_node, PathNode):
        out.extend(seg.step for seg in ast_node.segments)
        for seg in ast_node.segments:
            if seg.predicate is not None:
                out.extend(_collect_path_steps(seg.predicate))
        return out
    if isinstance(ast_node, BinaryOpNode):
        out.extend(_collect_path_steps(ast_node.left))
        out.extend(_collect_path_steps(ast_node.right))
        return out
    if isinstance(ast_node, FunctionCallNode):
        for arg in ast_node.args:
            out.extend(_collect_path_steps(arg))
        return out
    return out


def test_leafref_prefixed_path_with_predicate_parses() -> None:
    yang = """
module prefixed_leafref_predicate {
  yang-version 1.1;
  namespace "urn:xyang:test:prefixed-leafref-predicate";
  prefix p;

  container top {
    list items {
      key id;
      leaf id { type string; }
      leaf value { type string; }
    }
  }

  container client {
    leaf id { type string; }
    leaf selected {
      type leafref {
        path "/p:top/p:items[p:id = current()/../p:id]/p:value";
      }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    client = mod.find_statement("client")
    assert client is not None
    selected = client.find_statement("selected")
    assert isinstance(selected, YangLeafStmt)
    assert selected.type is not None
    path_ast = selected.type.path
    assert isinstance(path_ast, PathNode)
    assert [seg.step for seg in path_ast.segments] == ["p:top", "p:items", "p:value"]
    assert path_ast.segments[1].predicate is not None
    pred_steps = _collect_path_steps(path_ast.segments[1].predicate)
    assert "p:id" in pred_steps


def test_must_and_when_with_prefixed_predicate_paths_parse() -> None:
    yang = """
module prefixed_must_when_predicate {
  yang-version 1.1;
  namespace "urn:xyang:test:prefixed-must-when-predicate";
  prefix p;

  container top {
    list items {
      key id;
      leaf id { type string; }
      leaf enabled { type boolean; }
    }
  }

  container client {
    leaf id { type string; }
    leaf guarded {
      type string;
      when "/p:top/p:items[p:id = current()/../p:id]";
      must "count(/p:top/p:items[p:id = current()/../p:id]) >= 1";
    }
  }
}
"""
    mod = parse_yang_string(yang)
    client = mod.find_statement("client")
    assert client is not None
    guarded = client.find_statement("guarded")
    assert isinstance(guarded, YangLeafStmt)
    assert guarded.when is not None
    when_steps = _collect_path_steps(guarded.when.ast)
    assert "p:top" in when_steps
    assert "p:id" in when_steps
    assert guarded.must_statements
    must_steps = _collect_path_steps(guarded.must_statements[0].ast)
    assert "p:top" in must_steps
    assert "p:id" in must_steps


def test_augment_with_existing_prefix_but_missing_top_level_node_raises() -> None:
    yang = """
module augment_existing_prefix_missing_node {
  yang-version 1.1;
  namespace "urn:xyang:test:augment-existing-prefix-missing";
  prefix p;

  container root {
    leaf present {
      type string;
    }
  }

  augment "/p:missing" {
    leaf extra {
      type string;
    }
  }
}
"""
    with pytest.raises(YangSyntaxError, match="no top-level schema node"):
        YangParser(expand_uses=True).parse_string(yang)


def test_augment_with_non_existing_prefix_raises() -> None:
    yang = """
module augment_non_existing_prefix {
  yang-version 1.1;
  namespace "urn:xyang:test:augment-non-existing-prefix";
  prefix p;

  container root {
    leaf present {
      type string;
    }
  }

  augment "/missing:root" {
    leaf extra {
      type string;
    }
  }
}
"""
    with pytest.raises(YangSyntaxError, match="unknown prefix"):
        YangParser(expand_uses=True).parse_string(yang)
