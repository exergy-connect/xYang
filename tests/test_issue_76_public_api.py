"""Public exports and CLI errors from #76."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

from xyang.__main__ import _CLI_ERRORS, _load_instance_data, main


def test_package_exports_syntax_error_and_json_schema() -> None:
    import xyang
    from xyang import YangSyntaxError, generate_json_schema, parse_json_schema

    assert YangSyntaxError.__name__ == "YangSyntaxError"
    assert "YangSyntaxError" in xyang.__all__
    assert "generate_json_schema" in xyang.__all__
    assert "parse_json_schema" in xyang.__all__
    assert callable(generate_json_schema)
    assert callable(parse_json_schema)
    assert xyang.YangSyntaxError is YangSyntaxError
    assert xyang.generate_json_schema is generate_json_schema
    assert xyang.parse_json_schema is parse_json_schema


def test_cli_errors_do_not_include_typeerror_or_importerror() -> None:
    assert TypeError not in _CLI_ERRORS
    assert ImportError not in _CLI_ERRORS


def test_typeerror_during_parse_propagates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    yang = tmp_path / "m.yang"
    yang.write_text(
        'module m {\n  yang-version 1.1;\n  namespace "urn:m";\n  prefix m;\n}\n',
        encoding="utf-8",
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise TypeError("programming bug")

    monkeypatch.setattr("xyang.parse_yang_file", boom)
    monkeypatch.setattr(sys, "argv", ["xyang", "parse", str(yang)])
    with pytest.raises(TypeError, match="programming bug"):
        main()


def test_missing_pyyaml_is_a_valueerror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = tmp_path / "inst.yaml"
    data.write_text("a: 1\n", encoding="utf-8")
    real_import = builtins.__import__

    def guarded(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[no-untyped-def]
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("no pyyaml")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "yaml", raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(ValueError, match="pip install PyYAML") as excinfo:
        _load_instance_data(data)
    assert str(excinfo.value) == ("Reading .yaml or .yml requires PyYAML. Install it with: pip install PyYAML")
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_yaml_loader_reads_yaml_when_pyyaml_is_installed(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    data = tmp_path / "inst.yaml"
    data.write_text("a: 1\n", encoding="utf-8")
    assert _load_instance_data(data) == {"a": 1}
