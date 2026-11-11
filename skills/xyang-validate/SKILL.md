---
name: xyang-validate
description: Validate JSON instance data against YANG with xYang and consume the results in code, scripts, or CI. Use when checking instances, reading machine-readable errors (--format json, validate_detailed / validateDetailed), choosing RFC 7951 vs native JSON or 64-bit encodings, enabling features, or running xYang from the PyPI/npm packages, the xyang-ts GitHub Action, the browser bundle, or a QuickJS binary.
---

# xyang-validate

Check JSON instances against a YANG module and act on the result. To write or change the model itself, use [`skills/xyang-model/SKILL.md`](../xyang-model/SKILL.md).

## When to use

- A script, agent, or CI job must decide valid / invalid and read each error's location and code.
- Instance data has 64-bit numbers, `empty` leaves, or keyed lists and you must pick an encoding.
- The module uses `if-feature`, `import`, or `anydata`.
- You need xYang without a Python or Node install (GitHub Action, QuickJS binary) or in a browser.

## Pick a runtime

| Need | Use |
|---|---|
| Python library or CLI | `pip install xyang` → `xyang` |
| Node library or CLI | `npm i @exergy-connect/xyang` → `xyang-ts`, or one-off `npx -p @exergy-connect/xyang xyang-ts …` |
| Another repo's GitHub workflow | `exergy-connect/xYang/.github/actions/xyang-ts` (downloads the release's `xyang-ts.mjs`; needs no install) |
| Browser | `@exergy-connect/xyang/browser` (ESM) or the `xyang.umd.min.js` release asset (global `xYang`). Parse from strings only: there is no filesystem, so `import` must be resolvable without files |
| No runtime at all | QuickJS `xyang-ts-<platform>` binaries, same flags as `xyang-ts`. They exist only on releases whose QuickJS workflow succeeded: check `gh release view <tag> -R exergy-connect/xYang --json assets` first |

The Python and TypeScript CLIs take the same `validate` flags and give the same JSON output and exit codes.

## Recipe: validate from a shell and branch on the result

```bash
xyang validate --format json [--include-path DIR]... module.yang data.json
# xyang-ts validate --format json …   (same flags)
# data from stdin: pass - (or omit the data file)
```

- Exit status: **0** valid, **1** invalid, **2** usage error or a module that does not parse.
- On 0 or 1, stdout is `{"valid": bool, "errors": [{"path", "code", "message"}]}`. `path` is a JSON Pointer into the instance (`/topology/links/0`). Warnings go to stderr.
- On 2, stdout is empty and the reason is on stderr (for example `yang-version argument must be '1' or '1.1', got '2'`). Do not parse stdout then.
- Without `--format json` the output is `Valid.`, or `Validation failed:` followed by one line per error with a data path and the `must` expression; that text is for people, not parsers.

Example from the xyang-model skill assets (a link whose `source` equals `target`):

```text
{"valid": false, "errors": [{"path": "/topology/links/0", "code": "must", "message": "A link cannot connect a node to itself."}]}
```

## Recipe: validate from code

```python
from xyang import validate, parse_yang_file, YangValidator, YangSyntaxError

result = validate("module.yang", data, features=None, include_path=())  # one call
# result == {"valid": bool, "errors": [...], "warnings": [...]}
# each issue: {"code", "path", "message", "severity"} plus "expression" for must/when

validator = YangValidator(parse_yang_file("module.yang"))  # reuse for many documents
detailed = validator.validate_detailed(data)               # same dict as above
ok, messages, warnings = validator.validate(data)          # human-readable strings
```

```typescript
import { validate, parseYangFile, YangValidator, YangSyntaxError } from "@exergy-connect/xyang";

const result = validate("module.yang", data, { features: null, includePath: [] });
const validator = new YangValidator(parseYangFile("module.yang"));
const detailed = validator.validateDetailed(data);   // { valid, errors, warnings }
const summary = validator.validate(data);            // { isValid, errors: string[], warnings }
```

A module that fails to parse raises `YangSyntaxError` (or `YangSemanticError`); catch it separately from an invalid instance. `schema` may also be an already parsed module.

## Recipe: pick the instance encoding

**RFC 7951 is the default and is strict.** There is no fallback between encodings.

| Value | RFC 7951 (default) | Native (`--native-json`, `native_json=True`, `{ nativeJson: true }`) |
|---|---|---|
| `int64`, `uint64`, `decimal64` | JSON string `"9007199254740993"`; a number is a `type` error | JSON number (TypeScript reports a `type` error past 2^53) |
| 8/16/32-bit integers | JSON number; a string is a `type` error | JSON number |
| `empty` | `[null]` | `null` |
| list | array of entry objects | single-key list may be an object keyed by the key value |

An absent list and `[]` both count as zero entries: `min-elements 1` rejects both, and `[]` is otherwise accepted. Module-qualified member names (`module:name`) are accepted where RFC 7951 requires them, for example for augmented nodes.

## Recipe: features, imports, anydata

- `--features '{"mod": ["feat"]}'` enables only the listed features per module; `null` (the default) enables every declared feature. Data under a disabled `if-feature` is an `if-feature` error. Library: `features=` / `{ features }`.
- `--include-path DIR` (repeatable) adds import / include search directories after the module's own directory.
- `--anydata-validation complete|candidate` with `--anydata-module PATH` validates RFC 7951 members inside `anydata`. `examples/ietf-yang-push/README.md` has a worked command.
- To infer which features an instance needs: `infer_required_features(module, data)` / `inferRequiredFeatures(module, data)` (README, "Infer required YANG features").

## Recipe: CI in another repository

```yaml
- uses: exergy-connect/xYang/.github/actions/xyang-ts@v1.0.0
  with:
    version: v1.0.0          # release tag whose xyang-ts.mjs asset to download, or latest
    command: validate
    yang-file: models/module.yang
    data-file: data/sample.json
    include-path: |
      models
```

The step fails when validation fails. The action has no `--format` input: omit `command` to only put `xyang-ts` on `PATH`, then run `xyang-ts validate --format json …` yourself.

## Reading the parsed model (TypeScript)

Modules and statements are typed objects: `module.findStatement("top")`, then `stmt.keyword`, `stmt.name`, `stmt.statements`, `stmt.type`, `stmt.mandatory`. There is no `.data` property.

Integer bounds and other built-in type facts live in the type registry: Python `from xyang.types.registry import YANG_INTEGER_BOUNDS` (the old `xyang.json.integer_bounds` module was removed in 1.0.0). In TypeScript the registry is `ts/src/types/registry.ts` in the repository; the npm package does not export it.

## Limits to keep in mind

- `deviate add|replace|delete` and `action` are skipped with a warning; see the RFC deviations table in `FEATURES.md`.
- `must` / `when` use xYang's XPath 1.0 subset (`FEATURES.md`).
- Per-language known differences: `rg -n '"(python|ts)": "' tests/cases --glob case.json`.
