# JSON-LD exports

The Python APIs `generate_jsonld_context(module)` and `generate_jsonld_vocab(module)` (TypeScript: `generateJsonldContext` / `generateJsonldVocab`) project the canonical native schema into JSON-LD 1.1. Zig exposes `xyang.jsonld.generate`, returning both documents. Export does not mutate the module or fetch remote contexts.

From the repository root:

```bash
PYTHONPATH=src python -m xyang convert --help
PYTHONPATH=src python -m xyang convert --jsonld examples/jsonld/catalog.yang -o examples/jsonld/catalog.context.jsonld
PYTHONPATH=src python -m xyang convert --jsonld-vocab examples/jsonld/catalog.yang -o examples/jsonld/catalog.vocab.jsonld
```

Without `-o`, Python and Zig use `<stem>.context.jsonld` or `<stem>.vocab.jsonld`. TypeScript's `xyang-ts convert --jsonld` / `--jsonld-vocab` write to stdout. These two modes are mutually exclusive and cannot be combined with JSON Schema export options (`--schema-id`, `--native-json`, or the annotation opt-outs).

The checked-in output files are generated from `catalog.yang`; `xyang-jsonld.yang` declares the portable extensions. Import it alongside your model (or use `--include-path examples/jsonld`). No extension callback registration is needed. Definitions and invocations already survive native JSON round trips.

| Extension | Meaning |
| --- | --- |
| `jl:iri "https://schema.org/name"` | Map the property to an absolute IRI. `schema:`, `rdf:`, `rdfs:`, `skos:`, and `wd:` compact prefixes are also accepted. `@id` / `@type` make a leaf a JSON-LD keyword alias. |
| `jl:iri-value` | Add `@type: @id` to the term definition, for URI-valued leaves. |
| `jl:class "schema:Organization"` | Add a class link as `rdfs:range` on the vocabulary property. It does not inject an `@type` into instance data. |
| `jl:close-match "wd:Q1094444"` | Add a `skos:closeMatch` IRI to the vocabulary; repeatable. |
| `jl:unit-code "OHM"` | Add `schema:unitCode` to the vocabulary; otherwise the YANG `units` value is used. |

For existing models, the local extension names `schema-org-property`, `schema-org-class`, `wikidata`, and `unit-code` are also recognized regardless of their defining module. Bare schema.org names become `https://schema.org/<name>`, Wikidata `Q` IDs become entity IRIs, and the schema.org `url` property also enables IRI values. Other extensions are left uninterpreted. The generic `iri`, `iri-value`, `class`, and `close-match` names are recognized only from the defining module `xyang-jsonld`.

Default term IRIs append the local data-node name to its module namespace. A namespace ending with `#`, `/`, or `:` is used directly; other namespaces gain `#`. Containers and list entries have property-scoped contexts, so `seller/name` can map to `schema:name` while `series/name` maps to `schema:model`. Choice/case and grouping names do not become instance terms. Vocabulary records are sorted by IRI and merge metadata for repeated IRIs. Constraints such as `must`, cardinality, and list keys remain in YANG/native JSON Schema; the RDF vocabulary is a projection, not a reversible model format.

Use bare instance member names when applying external IRI mappings. JSON-LD treats `module:member` as a compact IRI and forbids redefining it to an unrelated IRI. Module prefix definitions support namespace-based qualified names; an explicit external mapping on an already qualified schema property fails loudly rather than producing invalid JSON-LD. Conflicting mappings, unresolved references, and invalid IRIs are also export errors. Scoped contexts and these compact-IRI restrictions follow [JSON-LD 1.1](https://www.w3.org/TR/json-ld11/).

For example, attach the generated context to this accepted xYang instance:

```json
{
  "@context": "catalog.context.jsonld",
  "seller": {"name": "Alice", "url": "https://example.invalid/alice"},
  "series": [{"name": "Series A", "resistance": "4.32"}]
}
```

The Python tests expand the document and vocabulary with PyLD (a development dependency), checking that the two `name` terms and the URL value have the intended RDF meanings. Both language suites compare the generated documents with these same example files; Python/Zig CLI parity also covers default and explicit filenames.
