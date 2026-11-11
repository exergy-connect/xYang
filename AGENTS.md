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

A pull request head commit may carry the trailer line `Local-Tests: passed`. Add it only after `pytest -q`, `pytest tests/test_cases.py -q -rxX`, and `cd ts && npm test` have all passed locally. CI then skips the Python matrix, the Node minimum and latest LTS jobs, and the conformance cases. Pushes to `main`, tags, and releases always run the full suite. Do not use `[skip ci]`.

Author models with [`skills/xyang-model/SKILL.md`](skills/xyang-model/SKILL.md). Validate instances and integrate xYang in scripts or CI with [`skills/xyang-validate/SKILL.md`](skills/xyang-validate/SKILL.md).
