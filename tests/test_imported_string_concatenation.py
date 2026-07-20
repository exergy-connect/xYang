"""Regression coverage for RFC 7950 string concatenation in imported modules."""

from pathlib import Path

from xyang import parse_yang_file
from xyang.parser.tokenizer import YangTokenizer


def test_imported_module_accepts_concatenated_description(tmp_path: Path) -> None:
    (tmp_path / "dependency.yang").write_text(
        '''module dependency {
  yang-version 1.1;
  namespace "urn:dependency";
  prefix dep;
  typedef label {
    type string;
    description "first "
              + "second";
  }
}
''',
        encoding="utf-8",
    )
    root = tmp_path / "root.yang"
    root.write_text(
        '''module root {
  yang-version 1.1;
  namespace "urn:root";
  prefix root;
  import dependency { prefix dep; }
  leaf value { type dep:label; }
}
''',
        encoding="utf-8",
    )

    module = parse_yang_file(root, include_path=(tmp_path,))

    imported = module.import_prefixes["dep"]
    assert imported.typedefs["label"].description == "first second"


def test_tokenizer_normalizes_quoted_string_concatenation() -> None:
    stream = YangTokenizer().tokenize('description "first " + "second";')

    assert stream.tokens == ["description", "first second", ";"]

    unquoted = YangTokenizer().tokenize('description "first " + second;')
    assert unquoted.tokens == ["description", "first ", "+", "second", ";"]
