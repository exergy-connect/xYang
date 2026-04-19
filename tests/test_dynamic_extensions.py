"""Dynamic extension parsing and capability-based semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import parse_yang_file, parse_yang_string
from xyang.ast import (
    YangExtensionInvocationStmt,
    YangExtensionStmt,
    YangLeafStmt,
)
from xyang.errors import YangSyntaxError
from xyang.validator.document_validator import DocumentValidator


def test_extension_definition_and_generic_prefixed_invocation_parsed() -> None:
    mod = parse_yang_string(
        """
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;

  extension custom {
    argument name;
    description "custom extension";
  }

  ex:custom "payload" {
    leaf foo { type string; }
  }
}
"""
    )

    ext = mod.get_extension("custom")
    assert isinstance(ext, YangExtensionStmt)
    assert ext.argument_name == "name"

    invocations = [s for s in mod.statements if isinstance(s, YangExtensionInvocationStmt)]
    assert len(invocations) == 1
    inv = invocations[0]
    assert inv.name == "ex:custom"
    assert inv.prefix == "ex"
    assert inv.argument == "payload"
    assert inv.resolved_module is mod
    assert inv.resolved_extension is ext
    assert any(isinstance(s, YangLeafStmt) and s.name == "foo" for s in inv.statements)


def test_extension_invocation_resolution_failure_is_parse_error() -> None:
    with pytest.raises(YangSyntaxError):
        parse_yang_string(
            """
module ex-bad {
  yang-version 1.1;
  namespace "urn:ex:bad";
  prefix ex;

  ex:missing "x";
}
"""
        )


def test_rfc8791_capability_maps_and_merges_augment_structure(tmp_path: Path) -> None:
    sx = tmp_path / "ietf-yang-structure-ext.yang"
    sx.write_text(
        """
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;

  extension structure { argument name; }
  extension augment-structure { argument target; }
}
""",
        encoding="utf-8",
    )

    demo = tmp_path / "demo.yang"
    demo.write_text(
        """
module demo {
  yang-version 1.1;
  namespace "urn:demo";
  prefix d;

  import ietf-yang-structure-ext { prefix sx; }

  sx:structure msg {
    leaf a { type string; }
  }

  sx:augment-structure "/d:msg" {
    leaf b { type string; }
  }
}
""",
        encoding="utf-8",
    )

    mod = parse_yang_file(demo)
    sx_mod = mod.import_prefixes["sx"]
    structure_ext = sx_mod.get_extension("structure")
    assert isinstance(structure_ext, YangExtensionStmt)
    assert structure_ext.apply_callback is not None
    augment_ext = sx_mod.get_extension("augment-structure")
    assert isinstance(augment_ext, YangExtensionStmt)
    assert augment_ext.apply_callback is not None
    structs = [
        s
        for s in mod.statements
        if isinstance(s, YangExtensionInvocationStmt)
        and s.name == "sx:structure"
    ]
    assert len(structs) == 1
    msg = structs[0]
    names = {s.name for s in msg.statements if isinstance(s, YangLeafStmt)}
    assert names == {"a", "b"}
    assert not any(
        isinstance(s, YangExtensionInvocationStmt)
        and s.name == "sx:augment-structure"
        for s in mod.statements
    )


def test_rfc8791_resolver_works_with_non_default_extension_prefix(tmp_path: Path) -> None:
    sx = tmp_path / "ietf-yang-structure-ext.yang"
    sx.write_text(
        """
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;

  extension structure { argument name; }
  extension augment-structure { argument target; }
}
""",
        encoding="utf-8",
    )

    demo = tmp_path / "demo-prefix.yang"
    demo.write_text(
        """
module demo-prefix {
  yang-version 1.1;
  namespace "urn:demo:prefix";
  prefix d;

  import ietf-yang-structure-ext { prefix extx; }

  extx:structure msg {
    leaf a { type string; }
  }

  extx:augment-structure "/d:msg" {
    leaf b { type string; }
  }
}
""",
        encoding="utf-8",
    )

    mod = parse_yang_file(demo)
    msg = next(
        s
        for s in mod.statements
        if isinstance(s, YangExtensionInvocationStmt)
        and s.name == "extx:structure"
    )
    names = {s.name for s in msg.statements if isinstance(s, YangLeafStmt)}
    assert names == {"a", "b"}


def test_rfc8791_augment_structure_merges_when_and_if_feature_semantics(
    tmp_path: Path,
) -> None:
    sx = tmp_path / "ietf-yang-structure-ext.yang"
    sx.write_text(
        """
module ietf-yang-structure-ext {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-structure-ext";
  prefix sx;

  extension structure { argument name; }
  extension augment-structure { argument target; }
}
""",
        encoding="utf-8",
    )

    demo = tmp_path / "demo-sem.yang"
    demo.write_text(
        """
module demo-sem {
  yang-version 1.1;
  namespace "urn:demo:sem";
  prefix d;

  import ietf-yang-structure-ext { prefix sx; }
  feature f;

  sx:structure msg {
    leaf a { type string; }
    leaf enabled { type string; }
    leaf mode { type string; }
  }

  sx:augment-structure "/d:msg" {
    if-feature "f";
    when "enabled = 'true'";
    leaf b {
      type string;
      when "mode = 'x'";
    }
  }
}
""",
        encoding="utf-8",
    )

    mod = parse_yang_file(demo)
    structs = [
        s
        for s in mod.statements
        if isinstance(s, YangExtensionInvocationStmt)
        and s.name == "sx:structure"
        and (s.argument or "").strip() == "msg"
    ]
    assert len(structs) == 1
    msg = structs[0]
    leaf_b = next(
        s for s in msg.statements if isinstance(s, YangLeafStmt) and s.name == "b"
    )

    # RFC 8791 semantics in this implementation mirror uses/augment root merge:
    # if-feature on augment-structure is prepended onto added roots.
    assert leaf_b.if_features == ["f"]
    # when on augment-structure is AND-merged with child when and evaluated
    # with parent context.
    assert leaf_b.when is not None
    assert leaf_b.when.condition == "(enabled = 'true') and (mode = 'x')"
    assert leaf_b.when.evaluate_with_parent_context is True

    # Data validation semantics: merged when controls whether b is allowed.
    v = DocumentValidator(msg)
    ok_errors = v.validate({"enabled": "true", "mode": "x", "b": "ok"})
    assert ok_errors == []

    bad_errors = v.validate({"enabled": "true", "mode": "y", "b": "bad"})
    assert bad_errors, "Expected when-false violation for leaf b"
    assert any("when" in e.message.lower() and "false" in e.message.lower() for e in bad_errors)
