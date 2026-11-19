"""JSON-LD scoped terms, vocabulary links, and safe failures (#229)."""

import json
from pathlib import Path
import sys

import pytest

from xyang import (
    generate_jsonld_context,
    generate_jsonld_vocab,
    generate_json_schema,
    parse_json_schema,
    parse_yang_file,
    parse_yang_string,
)
from xyang.__main__ import main
from xyang.errors import YangExportError

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/jsonld"


@pytest.fixture(scope="module")
def module():
    return parse_yang_file(EXAMPLE / "catalog.yang")


@pytest.mark.parametrize("kind", ["context", "vocab"])
def test_jsonld_example_and_native_round_trip(module, kind):
    build = generate_jsonld_context if kind == "context" else generate_jsonld_vocab
    original = generate_json_schema(module).schema
    expected = json.loads((EXAMPLE / f"catalog.{kind}.jsonld").read_text())
    assert build(module) == expected
    assert build(parse_json_schema(original)) == expected
    assert generate_json_schema(module).schema == original


def test_jsonld_context_expands_scoped_names_and_uri_values(module):
    from pyld import jsonld

    document = {
        **generate_jsonld_context(module),
        "seller": {"name": "Alice", "url": "https://example.invalid/alice"},
        "series": [{"name": "Series A"}],
    }
    assert jsonld.expand(document) == [
        {
            "https://schema.org/seller": [
                {
                    "https://schema.org/name": [{"@value": "Alice"}],
                    "https://schema.org/url": [{"@id": "https://example.invalid/alice"}],
                }
            ],
            "https://schema.org/hasPart": [{"https://schema.org/model": [{"@value": "Series A"}]}],
        }
    ]


def test_jsonld_vocabulary_is_valid_linked_data(module):
    from pyld import jsonld

    expanded = jsonld.expand(generate_jsonld_vocab(module))
    part = next(node for node in expanded if node["@id"] == "https://schema.org/hasPart")
    assert part["http://www.w3.org/2000/01/rdf-schema#range"] == [{"@id": "https://schema.org/ProductModel"}]
    assert part["http://www.w3.org/2004/02/skos/core#closeMatch"] == [
        {"@id": "http://www.wikidata.org/entity/Q1094444"}
    ]
    ohms = next(node for node in expanded if node["@id"].endswith("#resistance"))
    assert ohms["https://schema.org/unitCode"] == [{"@value": "OHM"}]


@pytest.mark.parametrize(
    "namespace,base",
    [
        ("urn:m", "urn:m#"),
        ("urn:m:", "urn:m:"),
        ("https://example.invalid/m#", "https://example.invalid/m#"),
        ("https://example.invalid/m/", "https://example.invalid/m/"),
    ],
)
def test_namespace_join(namespace, base):
    m = parse_yang_string(f'module m {{ namespace "{namespace}"; prefix m; leaf name {{ type string; }} }}')
    assert generate_jsonld_context(m)["@context"]["name"] == {"@id": base + "name"}


def test_legacy_extension_convention():
    m = parse_yang_string("""module m { namespace "urn:m"; prefix m;
      extension schema-org-property { argument name; } extension schema-org-class { argument name; }
      extension wikidata { argument id; } extension unit-code { argument code; }
      leaf url { type string; m:schema-org-property "url"; m:schema-org-class "URL"; m:wikidata "Q1"; m:unit-code "C62"; }
    }""")
    assert generate_jsonld_context(m)["@context"]["url"] == {"@id": "https://schema.org/url", "@type": "@id"}
    node = generate_jsonld_vocab(m)["@graph"][0]
    assert node["rdfs:range"] == {"@id": "https://schema.org/URL"}
    assert node["skos:closeMatch"] == [{"@id": "http://www.wikidata.org/entity/Q1"}]
    assert node["schema:unitCode"] == "C62"


def test_keyword_alias():
    from pyld import jsonld

    m = parse_yang_string("""module xyang-jsonld { namespace "urn:jl"; prefix jl;
      extension iri { argument value; } leaf id { type string; jl:iri "@id"; }
    }""")
    doc = {**generate_jsonld_context(m), "id": "https://example.invalid/id", "@type": "Thing"}
    assert jsonld.expand(doc) == [{"@id": "https://example.invalid/id", "@type": ["urn:jl#Thing"]}]
    assert generate_jsonld_vocab(m)["@graph"] == []


@pytest.mark.parametrize(
    "mapping",
    ['jl:iri "";', 'jl:iri "relative";', 'jl:iri "https://example.invalid/a"; jl:iri "https://example.invalid/b";'],
)
def test_invalid_mapping_fails_loudly(mapping):
    m = parse_yang_string("""module xyang-jsonld { namespace "urn:jl"; prefix jl;
      extension iri { argument value; } leaf name { type string; """ + mapping + " } }")
    with pytest.raises(YangExportError, match="JSON-LD"):
        generate_jsonld_context(m)


@pytest.mark.parametrize("kind", ["context", "vocab"])
def test_jsonld_cli(tmp_path, monkeypatch, kind):
    target = tmp_path / f"{kind}.jsonld"
    flag = "--jsonld" if kind == "context" else "--jsonld-vocab"
    monkeypatch.setattr(sys, "argv", ["xyang", "convert", flag, str(EXAMPLE / "catalog.yang"), "-o", str(target)])
    assert main() == 0
    assert json.loads(target.read_text()) == json.loads((EXAMPLE / f"catalog.{kind}.jsonld").read_text())


@pytest.mark.parametrize("flags", [["--jsonld", "--jsonld-vocab"], ["--jsonld", "--native-json"]])
def test_incompatible_jsonld_options_fail_before_reading(monkeypatch, flags):
    monkeypatch.setattr(sys, "argv", ["xyang", "convert", *flags, "missing.yang"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_grouping_and_choice_are_not_data_terms():
    m = parse_yang_string("""module m { namespace "urn:m"; prefix m;
      grouping named { leaf name { type string; } }
      container top { uses named; choice pick { leaf x { type string; } leaf y { type string; } } }
    }""")
    terms = generate_jsonld_context(m)["@context"]["top"]["@context"]
    assert set(terms) == {"name", "x", "y"}


def test_vocabulary_merges_repeated_iri_labels_and_descriptions():
    m = parse_yang_string("""module xyang-jsonld { namespace "urn:jl"; prefix jl;
      extension iri { argument value; }
      leaf a { type string; description "First"; jl:iri "schema:name"; }
      leaf b { type string; description "Second"; jl:iri "schema:name"; }
    }""")
    assert generate_jsonld_vocab(m)["@graph"] == [
        {
            "@id": "https://schema.org/name",
            "@type": "rdf:Property",
            "rdfs:label": ["a", "b"],
            "rdfs:comment": ["First", "Second"],
        }
    ]
