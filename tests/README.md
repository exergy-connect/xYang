# Tests

| Where | What | Runs in |
|---|---|---|
| [`tests/cases/`](cases/) | Shared conformance cases: a schema, instances, and the exact expected `(path, code)` errors ([format](cases/README.md)) | Python and TypeScript |
| `tests/test_*.py`, `tests/json/`, `tests/meta-model/`, `tests/parser/`, `tests/types/` | Python API, parser/AST, JSON Schema, CLI, example and tooling tests | Python |
| [`ts/test/`](../ts/test/) | The same kinds of TypeScript-specific tests | TypeScript |

Commands are in [`AGENTS.md`](../AGENTS.md#tests).

## Counting

```
python tests/inventory.py            # logical cases, runner items, expected failures, CI executions
python tests/inventory.py --by-file  # plus runtime-specific counts per file
```

The script reads the runners' own collection (`pytest --collect-only`, `vitest list`) and the
`case.json` files; there is no list to keep up to date. A shared instance counts once, although
both runtimes run it. Every other collected pytest item or vitest test counts once for its
runtime. CI prints the summary in the Python 3.13 job. Ontology tests are in that count and are
reported again as release-only executions, so they are not inside the per-PR total.

## Ontology example

Pull requests and pushes do not run these tests. The pytest matrix uses `-m "not ontology"`,
and `npm test` excludes `test/ontology_audit_example.test.ts`.

A published release runs them. The event is `release: published`, the same event as Publish to
PyPI, Publish to npm, Release TypeScript artifacts, Release Zig binaries, and Benchmark
([`.github/workflows/ontology-example.yml`](../.github/workflows/ontology-example.yml)). The
Python job installs `examples/ontology-hypergraph/requirements-tools.txt` and fails if any test
is skipped, so the pyang and OWL RL checks run. The TypeScript job runs `npm run test:ontology`.
A failure fails that workflow on the release. `workflow_dispatch` runs the same two jobs and
publishes nothing.

Locally, any time:

```bash
pytest -m ontology
pip install -r examples/ontology-hypergraph/requirements-tools.txt   # pyang and owlrl checks
cd ts && npm run test:ontology
```

## Adding a test

1. Behavior you can observe through `validate_detailed` / `validateDetailed` (a schema plus an
   instance and its errors, or a schema that must fail to load) goes in `tests/cases/`. Add an
   instance to the case that already has the schema; start a new case only for a new schema.
   Do not repeat a shared case as a Python or TypeScript test.
2. Write a runtime-specific test only for a contract the shared runner cannot express: a public
   API shape, AST or JSON Schema output, CLI exit code and streams, logging, caching, or
   non-mutation of inputs.
3. One scenario per test or instance. Use `parametrize` / `it.each` so each scenario shows up
   in the count; do not loop over unrelated inputs inside one test.
4. For a regression, add the smallest positive/negative pair that fails before the fix and cite
   the issue (`(#123)`) in the case `description` or the test docstring.
5. Keep boundaries (empty, zero, equal, min/max, first/last), prefix and namespace variants,
   and context and encoding variants. Drop permutations that run the same code path with the
   same kind of input and outcome.
6. Parse a model once per file (module-scoped fixture, `beforeAll`). Use one real subprocess
   per CLI contract and call the CLI in-process for the rest.
7. If your change raises `tests/inventory.py`'s logical count, say by how much in the PR and
   why the new cases are distinct. To delete a test, name the retained check that asserts the
   same behavior (see [the #154 record](../docs/test-consolidation-154.md)).
