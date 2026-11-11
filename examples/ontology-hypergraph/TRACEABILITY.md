# Standards traceability and evidence limits

This matrix separates ontology obligations from transport choices. **No ISO conformity claim is made.** The implementation demonstrates how ontology fragments and evidence can be carried and checked. Neither a valid YANG tree nor an empty OWL RL error report proves conformity to ISO/IEC 21838-1 or ISO/IEC 21838-2.

The ISO sources reviewed here are the publishers' public scope descriptions, together with the BFO project's public formal artifacts. A complete clause-by-clause review of the normative ISO texts has **not** been performed. Consequently, the ISO rows below identify review areas and supporting mechanisms, not verified satisfaction of unnamed normative requirements. No invented clause numbers or requirement quotations are used. The RFC rows identify concrete sections and executable checks.

## ISO ontology review matrix

| Standard and review area | Applicability and representation | Available evidence | Remaining evidence / status |
| --- | --- | --- | --- |
| ISO/IEC 21838-1:2021 — top-level hub ontology | BFO is the selected TLO; generic hypergraph machinery is domain-neutral transport | Separate `example-hypergraph` and `example-bfo` modules; ISO Part 2 identifies BFO as conformant to Part 1 | The ISO statement about BFO is not transferred to this reduced YANG vocabulary or local domain ontology. Full normative assessment remains open. |
| Part 1 — relationship between top-level and domain ontologies | Lab identities specialize material entity and process tags; domain term records carry BFO class IRIs | `example-bfo`, `example-lab`, and `documents/terms.json` | Requires review of the complete domain ontology and its formal alignment, not merely a tag inheritance test. Partial support. |
| Part 1 — TLO terms in lower-level definitions and axioms | Domain universal records include labels, textual definitions, and BFO alignment | `term-description` grouping; specimen and assay records; explicit domain subclass mappings in `semantic_check.py` | Text presence is checked; adequacy, noncircularity, and equivalence of definitions to the intended concepts are not established. Open normative review. |
| Part 1 — exchange and integration purpose | Ontology identifiers, observations, and source records are collected across URLs | HTTP collector test; stable absolute IDs within the publication location; leafref integrity after projection | Supports an interoperability purpose. This engineering mechanism is not evidence that all TLO requirements are met. |
| Part 1 — formal ontology semantics | Preserve external formal artifacts as attachments; evaluate an explicitly selected class subset separately | Generic attachment mechanism; RDF/OWL RL evaluation view; upstream BFO artifacts | YANG identities and `must` statements do not supply the full formal ontology. Full axiomatization and interpretation need a separate normative audit. |
| ISO/IEC 21838-2:2021 — BFO-2020 terms | Five selected BFO class alignments use canonical BFO identifiers | Identity descriptions and the `ALIGNMENTS` table in `semantic_check.py` | A subset alignment is not an implementation of all normative BFO definitions. Partial support. |
| Part 2 — BFO axiomatizations in OWL 2 and Common Logic | Reasoning stays outside structural validation | Optional external OWL RL reasoner; reference to upstream OWL and Common Logic artifacts | Complete BFO axioms are not bundled or verified. OWL RL is incomplete for full OWL 2/CL semantics. Open. |
| Part 2 — requirements for domain modules in a BFO-hub suite | Lab domain concepts have nearest selected BFO alignments; individual and universal records are distinguished by `term` presence | Two documented term records; published term URLs remain class identifiers in the optional view | Requires complete domain definitions, axioms, and review against the actual normative domain-module requirements. Not established. |
| Part 2 — continuant/occurrent distinction | YANG checks allowed classification tags; optional OWL RL evaluates selected disjointness | A structurally valid sample with an additional occurrent classification produces a semantic error | Demonstrates one class consistency check, not global ontology consistency or an ISO conformity verdict. |
| Part 2 — relation and temporal semantics | N-ary observations have role-labelled occurrences; these are not asserted as normative BFO relations | Generic incidence structure; laboratory reaction constraints | Temporalized BFO participation and relational axioms are outside the demonstrated semantic view. Open. |

Version metadata, permanent URI conventions, provenance, JSON encoding, and URL collection are deliberate application choices. The [Part 1 public scope](https://www.iso.org/standard/71954.html) explicitly excludes URI identifier rules, maintenance/versioning, reasoning methods, and translation methods from its specification. These mechanisms therefore must not be presented as ISO requirements satisfied by this example.

For an actual conformity assessment, obtain the normative editions, enumerate each applicable requirement and its clause, identify the ontology artifact/version being assessed, attach formal definitions and axioms, record the evaluator/tool and evidence for each row, and report every unmet or inapplicable requirement with justification. This example provides structure for such evidence, not that completed assessment.

## YANG and JSON implementation matrix

| Source | Mechanism | Executable evidence / limit |
| --- | --- | --- |
| RFC 7950 §§7.1.5, 7.1.9 | Standard imports and dated revisions; revision-qualified source filenames | pyang lint and xYang parsing; collector verifies advertised revisions and model source digests |
| RFC 7950 §§7.12–7.13 | Generic groupings, host-module instantiation, refinement | Relative leafrefs bind in `example-lab`; reaction constraints are added by standard `refine` |
| RFC 7950 §7.17 | Same-module and cross-module augments | Optional term/experiment containers; independent evidence-provider `reviewed` leaf |
| RFC 7950 §§7.18, 9.10 | Extensible identities and identityrefs | Derived domain kinds and incidence roles; unrelated kinds and module-prefix identityref values are rejected |
| RFC 7950 §§7.5.3, 7.8, 7.9, 7.21.5, 10.4 | `must`, occurrence list keys, exclusive participant choice, `when`, identity functions | Repeated targets retain distinct incidence IDs; invalid roles/types/counts and experiment-on-bundle fail |
| RFC 7950 §9.9 | `leafref` with required target instances | Origins, dependencies, node participants, and nested hyperedge participants resolve in the merged tree; deleted targets fail |
| RFC 7951 §§4, 5.4, 6.3, 6.8 | Module-qualified root and cross-module members; arrays; JSON booleans; module-name identityrefs | Collector boundary and xYang tests; Yangson independently rejects invalid encodings. The narrow boolean boundary check compensates for current xYang leniency. |
| RFC 8407 §§4.8, 4.10 and model documentation guidance | Revision references, example namespaces, descriptions, explicit presence root, documented operational limits | `pyang --lint` over all source modules; this README documents URI, schema, and trust assumptions. Lint is not an IETF review. |
| RFC 8525 §§3–4 | Published module-set/schema inventory and content-derived inventory identifier | Generated `yang-library.json`; per-document model manifests are checked against trusted sources. No NMDA datastore service, notifications, or full discovery implementation. |
| RFC 7895 compatibility | Older module inventory input for independent tooling | Generated `yangson-library.json` loads the same four modules in Yangson; not confused with the modern publication inventory |

## Primary references

- [ISO/IEC 21838-1:2021 publisher scope](https://www.iso.org/standard/71954.html).
- [ISO/IEC 21838-2:2021 publisher scope](https://www.iso.org/standard/74572.html).
- [BFO-2020 formal artifacts, pinned implementation snapshot](https://github.com/BFO-ontology/BFO-2020/tree/bd1fb61c5fa4e358fc9690f0d214b1ac63fae594/21838-2). This repository snapshot is not evidence of exact correspondence to every normative ISO annex.
- [RFC 7950 — YANG 1.1](https://www.rfc-editor.org/rfc/rfc7950.html).
- [RFC 7951 — JSON encoding](https://www.rfc-editor.org/rfc/rfc7951.html).
- [RFC 8407 — YANG model authoring guidelines](https://www.rfc-editor.org/rfc/rfc8407.html).
- [RFC 8525 — YANG Library](https://www.rfc-editor.org/rfc/rfc8525.html).
