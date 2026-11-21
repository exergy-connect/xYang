# xYang

xYang parses YANG modules, validates RFC 7951 JSON instance data, and exports JSON Schema.

Key learnings for agents: [`docs/KEY-LEARNINGS.md`](docs/KEY-LEARNINGS.md).

## Native JSON format

Treat `.yang` as the source and the native JSON as its reversible, canonical form. Never hand-edit one without the other being reproducible. Prefer the native JSON for fast, unambiguous processing. Any lossy or non-reversible change in the transform is a bug: raise a loud error and do not silently drop it.

## Install

`pip install xyang` · `npm i @exergy-connect/xyang`

## CLI

`xyang` and `xyang-ts` each implement `parse`, `validate`, and `convert`.

Run `xyang --help` or `xyang-ts --help`, or `<command> --help` / `-h`, to list the commands, options, defaults, and examples this revision implements. Help exits 0 and writes to stdout. It does not read a YANG module, a data file, or stdin.

`xyang -V` / `xyang --version` prints the Python package version. `xyang-ts` has no version flag. `xyang convert` writes `<stem>.yang.json` or `-o PATH`. `xyang-ts convert` prints JSON Schema to stdout and has no `-o`.

## Validate

```python
from xyang import parse_yang_file, YangValidator
module = parse_yang_file("examples/meta-model.yang")
validator = YangValidator(module)
data = {"data-model": {"name": "example", "entities": []}}
is_valid, errors, warnings = validator.validate(data)
```

```typescript
import { parseYangFile, YangValidator } from "@exergy-connect/xyang";
const module = parseYangFile("examples/meta-model.yang");
const validator = new YangValidator(module);
const data = { "data-model": { name: "example", entities: [] } };
const result = validator.validate(data);
```

Shared behavior lives in [`tests/cases/`](tests/cases/) ([README](tests/cases/README.md)).

## Tests

`pytest -q` · `cd ts && npm test`

Case runners: `pytest tests/test_cases.py` · `cd ts && npx vitest run test/cases.test.ts`

Test count: `python tests/inventory.py`. Before adding a test, read [`tests/README.md`](tests/README.md): prefer a shared case, one scenario per test. Ontology example tests are not part of `pytest -q` in CI or `npm test`; run them with `pytest -m ontology` and `cd ts && npm run test:ontology`. A published release runs both.

A pull request head commit may carry the trailer line `Local-Tests: passed`. Add it only after `pytest -q`, `pytest tests/test_cases.py -q -rxX`, and `cd ts && npm test` have all passed locally (`npm test` runs `tsc --noEmit` first through `pretest`; Vitest alone does not type-check, which let #207 break `main`). CI then skips the Python matrix, the Node minimum and latest LTS jobs, and the conformance cases. Pushes to `main`, tags, and releases always run the full suite. Do not use `[skip ci]`.

## Releases

- A release PR only bumps the version and moves changelog entries. It does not run the test suites (main is already verified) and carries no `Local-Tests` trailer.
- Bump the version in `pyproject.toml`, `ts/package.json`, and both root entries of `ts/package-lock.json` (same version for Python and TypeScript; patch bump unless the maintainer says otherwise).
- In `CHANGELOG.md` and `ts/CHANGELOG.md`, move the `[Unreleased]` entries under `## [X.Y.Z] — YYYY-MM-DD`, leave an empty `## [Unreleased]`, and update the compare links at the bottom. Do not rewrite entries; the TS changelog lists every change that affects the npm package.
- Title the PR `Release xYang X.Y.Z`; squash-merge it.
- Publish a GitHub release with tag `vX.Y.Z` on the merge commit, titled `xYang X.Y.Z`. Notes start with 'Python `xyang` and TypeScript `@exergy-connect/xyang` are now version X.Y.Z.', then Highlights, any breaking changes with the replacement, Fixed / Changed / Removed with issue links, and end with links to both changelogs at the tag.
- Publishing the release runs the benchmark, `zig-release.yml` (Zig binaries, `xyang.wasm`, `xyang.mjs`), `release-artifacts.yml`, and the ontology tests. Approve and merge the generated benchmark README PR; its merge triggers `publish-pypi.yml` and `publish-npm.yml` after verifying the measured release and README. Check that all workflows succeed.

Author models with [`skills/xyang-model/SKILL.md`](skills/xyang-model/SKILL.md). Validate instances and integrate xYang in scripts or CI with [`skills/xyang-validate/SKILL.md`](skills/xyang-validate/SKILL.md).
