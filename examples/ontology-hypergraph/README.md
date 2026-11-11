# Distributed ontology hypergraph: an audit engagement

One YANG model covers a whole fictional audit engagement: the client's facts (employees, accounts, terminations, account sign-ins, privileged changes), the controls under test, the evidence those facts came from, the assessments, the findings, and the reviews. Every conclusion must agree with the facts in the same tree. Four parties publish their parts as RFC 7951 JSON over HTTP; a collector merges them and xYang validates the result.

All names, people, systems, and records are synthetic. *Larkspur & Reed* is not a real firm, *Alder Ridge Logistics* is not a real client, and nothing here describes any firm's methodology.

**Validity is not a clean opinion, and it is not truth.** The sample engagement is valid *because* it reports a real breach: account `jmarsh` was used after its owner's termination took effect, and the record says so. Claiming the control worked, hiding the breach, or reporting a breach the facts do not show makes the record invalid. What the model cannot know is whether the exported facts are themselves true.

## The engagement

| Publisher | Document | Contents |
| --- | --- | --- |
| Firm methodology desk | [`documents/catalogue.json`](documents/catalogue.json) | Engagement scope and reference times, controls with their rules, the team, term definitions |
| Collection agent | [`documents/evidence.json`](documents/evidence.json) | Client systems; evidence records (collection time, export SHA-256); facts extracted from those exports; collection records |
| Assessment agent and senior | [`documents/assessments.json`](documents/assessments.json) | One assessment per control, one finding, a workpaper bundle |
| Independent reviewers | [`documents/reviews.json`](documents/reviews.json) (seed) | Sign-off on each assessment |

The synthetic exports are in [`documents/exports/`](documents/exports/). [`build_fixtures.py`](build_fixtures.py) produces the CSV rows and the structured facts from the same tables.

### Facts

| Account | Owner | Owner's termination takes effect | Sign-in | `breach` |
| --- | --- | --- | --- | --- |
| `rvance` | E1031 | 2026-07-03T17:00:00Z | 2026-07-02T08:00:00Z | `no` (before) |
| `jmarsh` | E1043 | 2026-08-14T17:00:00Z | 2026-08-26T09:12:44Z | **`yes`** |
| `tquill` | E1058 | 2026-09-22T17:00:00Z | 2026-09-22T17:00:00Z | `no` (same second) |
| `apatel` | E0977 | none | 2026-09-29T16:03:10Z | `no` |
| `lchen` | E0912 | none | 2026-09-30T08:41:55Z | `no` |

| Change | Implementer | Approver | Approved | Deployed | `breach` |
| --- | --- | --- | --- | --- | --- |
| CHG-2207 | A. Patel | L. Chen | 2026-08-03T10:15:00Z | 2026-08-03T18:30:00Z | `no` |
| CHG-2241 | L. Chen | A. Patel | 2026-09-11T19:45:00Z | 2026-09-11T19:45:00Z | `no` (same second) |

The engagement covers 2026-07-01T00:00:00Z to 2026-09-30T23:59:59Z, with as-of 2026-10-08T00:00:00Z and a maximum evidence age of 30 days.

### Conclusions

| Control | Rule | Outcome | Why it must be this |
| --- | --- | --- | --- |
| **AC-01** No account is used after its owner's termination | `leaver-access` | **exception**, finding `fd-ac-01` (violation: the `jmarsh` sign-in) | One account-use fact has `breach: yes` |
| **CM-02** Privileged changes are approved by someone else no later than deployment | `change-approval` | **supported** | No change fact has `breach: yes` |
| **AC-04** Quarterly user access review | `manual-review` | **insufficient-evidence** | No facts in the model decide it, and nothing was cited |

All three assessments are approved by a reviewer who did not assess them.

## Run it

From the repository root, with Python 3.11 or newer:

```bash
pip install -e .
python -m http.server 8765 --bind 127.0.0.1 --directory examples/ontology-hypergraph   # terminal 1
python examples/ontology-hypergraph/collector.py \
  http://127.0.0.1:8765/documents/reviews.json -o /tmp/audit-projected.json   # terminal 2
```

The collector exits 0 and writes 4 documents, 47 nodes, and 11 hyperedges. The checked-in projections validate with either CLI:

```bash
M=examples/ontology-hypergraph/models
xyang validate --include-path $M $M/example-audit@2026-11-10.yang examples/ontology-hypergraph/fixtures/valid.json
xyang-ts validate --format json --include-path $M $M/example-audit@2026-11-10.yang \
  examples/ontology-hypergraph/fixtures/invalid/supported-despite-breach.json
```

Tests: `pytest -m ontology` and `cd ts && npm run test:ontology`. Both assert the exact errors in [`fixtures/expected-errors.json`](fixtures/expected-errors.json). Pull-request CI does not run them. A published release does, with `requirements-tools.txt` installed so the pyang and OWL RL checks are not skipped (`workflow_dispatch` on Ontology example runs the same jobs).

## How the model makes this expressible

Three representation choices make every rule a plain `must` in xYang's XPath 1.0 subset, with the same result in Python and TypeScript.

**Times are numbers.** Every time is a `uint32` count of seconds since 1970-01-01T00:00:00Z (typedef `epoch-seconds`), encoded as a JSON number. XPath compares and adds these exactly, because every `uint32` is an exact double, and it does so through 2106. ISO strings would compare only as text, which XPath 1.0 cannot order. The README and the generator show the ISO form; the model stores only one time value per fact, so the two forms cannot disagree.

**Facts are structured and explicitly linked.** A termination names its employee. An account names its owner. A sign-in names its account. A change names its implementer and approver. Each fact names the evidence record it came from. All of these are `leafref`s with type checks, so a fact cannot point at the wrong kind of node.

**Each fact declares whether it breaches a control, and the model checks that declaration.** XPath 1.0 has no variables, and `current()` is always the node the `must` is attached to. A condition that pairs a sign-in with its owner's termination therefore has to be written with the sign-in as `current()`. So each sign-in declares `breach: yes|no`, and a `must` on that leaf requires the declaration to equal the computed condition:

```xpath
(. = 'yes') = boolean(../../../node/termination
    [employee = ../../node[id = current()/../account]/account/owner]
    [effective-at < current()/../at])
```

This matches only a termination of *this account's owner*, so another employee's termination cannot satisfy it. Assessments and findings then refer to these checked declarations, not to raw times.

## What each `must` guarantees

| Requirement | Where and how | Invalid fixture |
| --- | --- | --- |
| A sign-in is a breach exactly when the owner's termination took effect strictly earlier | `account-use/breach`: declaration equals the per-owner join above | `breach-declared-no`, `breach-claimed-for-unterminated-owner`, `breach-claimed-at-termination-second` |
| A change is a breach exactly when it is unapproved, self-approved, or approved after deployment | `change/breach`: `(. = 'yes') = boolean(not(../approver) or ../approver = ../implementer or ../approved-at > ../deployed-at)` | `self-approved-change-declared-no`, `change-approved-after-deployment-declared-no` |
| A leaver-access outcome is `exception` exactly when some sign-in is a breach | assessment: `(result/outcome = 'exception') = boolean(../node/account-use[breach = 'yes'])`, gated on the control's `rule` | `supported-despite-breach` |
| The same for change-approval and change facts | assessment, same pattern | `exception-without-breach` |
| Every breach is reported by a finding | `breach` leaf: some finding has a `violation` incidence pointing at this fact | `missing-exception-finding` |
| A finding's violations are breaches, of the kind its control's rule covers | `violation` incidence: target's `breach = 'yes'`, and its kind matches the basis control's `rule` | `unsupported-finding`, `finding-on-supported-assessment` |
| A finding cites the evidence its violation was taken from | `violation` incidence: cited-evidence includes the fact's `source` | test case |
| A finding is based on an exception assessment that has an approved review | finding | `finding-on-supported-assessment`, `finding-without-approved-review` |
| Supported or exception outcomes cite evidence of a type the control accepts | assessment and `cited-evidence` incidence | `assessment-without-evidence`, `evidence-type-not-accepted` |
| Cited evidence was produced by a collection in the same engagement | `cited-evidence` incidence: a collection with this record and the same engagement exists | `evidence-not-collected-for-engagement` |
| Cited evidence was collected no later than the assessment, and is at most `max-evidence-age` older than `as-of` | `cited-evidence` incidence: `collected-at <= ../recorded-at` and `collected-at + max-evidence-age >= as-of` | `evidence-collected-after-assessment`, `stale-evidence` |
| A review is recorded no earlier than its assessment and no later than `as-of`; assessments no later than `as-of` | review and assessment | `review-before-assessment`, `review-after-as-of` |
| The reviewer did not assess what they review | review | `reviewer-is-assessor` |
| Role cardinality and participant kinds per relation type | `count()` and `derived-from-or-self()` | `review-with-two-reviewers`, test cases |
| Sign-ins and deployments fall within the engagement period | `at` and `deployed-at` | `use-outside-period` |
| References resolve | `leafref` | `dangling-evidence` |

**Equal times.** Each boundary sits on the permitted side, and a test checks every one:

- a sign-in at the same second the termination takes effect is not a breach (`<`);
- approval at the same second as deployment is prior enough (`>` defines a breach);
- evidence collected at the same second as the assessment, a review recorded at the same second as its assessment, and a review at exactly `as-of` are all allowed;
- evidence exactly `max-evidence-age` old is still fresh.

Rules are written as counts and joins, never as "this list is present": XPath sees an absent list and `[]` the same way.

## What the model does not decide

- **Whether the facts are true.** A digest match proves the export bytes are the declared bytes. The structured facts are the collection agent's reading of those exports. The generator derives both from the same rows, but the model does not parse CSV files.
- **Authenticity, authorization, and judgment.** Who published a record, whether they were entitled to, sampling, materiality, and the audit opinion are outside the model.
- **Consistency across fetches.** Publications fetched at different times are not a transaction.

The collector fetches documents and export bytes, resolves URLs, and checks versions and digests. It computes no outcome; every audit rule is in [`models/example-audit@2026-11-10.yang`](models/example-audit@2026-11-10.yang).

## Model layout

- [`example-hypergraph`](models/example-hypergraph@2026-11-10.yang) is the generic core: documents, nodes, hyperedges, role-labelled incidences, attributes, attachments, and provenance. It has no audit or BFO dependency.
- [`example-audit`](models/example-audit@2026-11-10.yang) instantiates the core. It defines node kinds (engagement, control, evidence record, source system, employee, account, termination, account use, change, team members) with typed detail containers, and relation kinds (collection, assessment, review, finding). A `refine` adds the relation rules, and the fact containers carry their own rules.
- [`example-bfo`](models/example-bfo@2026-11-10.yang) is optional context: a small Basic Formal Ontology (BFO) alignment vocabulary. Audit node kinds derive from those tags (events from process, people from material entity, others from continuant). This is a tag hierarchy, not OWL axioms.

## Collection contract

Each publication contains exactly one `document` record with its URL, version, the shared ontology-suite version, and the revision and SHA-256 of each model.

The collector:

1. fetches the seed, then follows `requires`, incidence targets, and fact references (owner, employee, account, implementer, approver, sources), across origins, once each;
2. requires the same suite version and module set everywhere, and checks each model's revision and digest against the bundled YANG and the published bytes;
3. resolves every URI-valued field against its publication's URL;
4. fetches each evidence export and compares its SHA-256 with the record;
5. rejects elements claimed by another publication, duplicate IDs, version mismatches, and unknown members;
6. validates the merged tree with xYang, rejecting warnings too.

A single publication is a partial tree. Only the merged tree must satisfy the schema.

## Optional tools

- `check_tools.py` runs `pyang --lint` and validates the projection independently with Yangson. The tests also confirm that Yangson rejects every invalid fixture.
- `semantic_check.py` builds a partial RDF view and runs OWL RL over the BFO subclass and disjointness subset.

Install both with `pip install -r examples/ontology-hypergraph/requirements-tools.txt`; their tests are skipped without them. [`TRACEABILITY.md`](TRACEABILITY.md) maps mechanisms to RFC sections.

## Regenerate

YANG is the source. After editing it, run `python examples/ontology-hypergraph/build_fixtures.py`. This rewrites the publications, the exports, the valid and invalid projections, and both schema inventories. [`fixtures/expected-errors.json`](fixtures/expected-errors.json) is maintained by hand: update it only when a rule's intended errors change.

## Limits

- HTTP(S) only. No redirects, authentication, signatures, content negotiation, or graph database.
- The demo collector trusts its publishers: it allows cross-origin fetches, caps each fetch at 2 MB and the graph at 32 documents, and times out after 10 seconds.
- One engagement per tree: assessments count every fact in the graph, and period checks use the engagement present.
- Times end in 2106 (`uint32`).
- Single-valued fact references are used deliberately. Python currently resolves a relative `leafref` path on a `leaf-list` one level too high, while TypeScript resolves it correctly, so this example avoids leaf-list references.
