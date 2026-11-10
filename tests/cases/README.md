# Shared conformance cases

Language-neutral test cases that every xYang implementation runs. A case is data only
(YANG modules, JSON instances, expected results), so the same files test Python, TypeScript
and, later, a standalone CLI binary.

| Runner | Command |
|---|---|
| Python | `pytest tests/test_cases.py` ([`tests/test_cases.py`](../test_cases.py)) |
| TypeScript | `cd ts && npx vitest run test/cases.test.ts` ([`ts/test/cases.test.ts`](../../ts/test/cases.test.ts)) |
| CLI binary | `XYANG_CLI=/path/to/xyang pytest tests/test_cases.py -k cli:` (see [CLI protocol](#cli-protocol)) |

CI runs the Python and TypeScript runners on every push and pull request
([`.github/workflows/conformance.yml`](../../.github/workflows/conformance.yml)).

## Layout

```
tests/cases/
  <area>/<case-name>/
    case.json                 the case
    m.yang                    primary module (name given in case.json)
    other.yang                imported / included modules; the case directory is the include path
```

Areas: `syntax`, `types`, `structure`, `choice`, `conditions`, `xpath`, `references`, `reuse`,
`modules`, `encoding`. One case directory per schema; put several instances in one case
when they share the schema.

## `case.json`

```json
{
  "description": "must inside a list entry; current() is the leaf",
  "module": "m.yang",
  "features": { "m": ["f1"] },
  "xfail": { "ts": "why TypeScript fails every instance of this case" },
  "instances": [
    { "name": "positive value", "data": { "top": { "items": [{ "id": "a", "v": 1 }] } }, "valid": true },
    { "name": "negative value", "data": { "top": { "items": [{ "id": "a", "v": -1 }] } }, "valid": false,
      "errors": [{ "path": "/top/items/0/v", "code": "must", "message": "v must be positive" }],
      "xfail": { "python": "why Python fails this instance" } }
  ]
}
```

| Field | Meaning |
|---|---|
| `description` | What the case checks; cite the RFC section when behavior is subtle. |
| `module` | Primary module file in the case directory. |
| `features` | Optional. Module name -> enabled feature names. Omitted: every declared feature is enabled. A module missing from the map keeps all its features. |
| `schema_error` | Optional. `true` means loading the module must fail; the case then has no `instances`. Optional `code` is a substring the load error must contain, the same in every implementation. |
| `xfail` | Optional, on the case or on an instance (instance entries override case entries). Implementation id (`python`, `ts`, `cli`) -> reason. |
| `instances[].data` | The JSON instance document (RFC 7951). |
| `instances[].valid` | Whether the implementation must report no errors. |
| `instances[].errors` | Expected errors when `valid` is `false`. |

### Expected errors

An error is `{ "path", "code", "message"? }`:

- **`path`** is a [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) into `data`: list entries
  and leaf-list items by position (`/top/items/1/v`, `/top/tags/0`), member names exactly as they
  appear in the JSON (`/m:top/a`). The document root is `""`. Errors about a missing node point at
  where it would be (`/top/name`). `choice` and `case` are not data nodes, so their errors point
  at the parent data node (`/top`).
- **`code`** is one of `range`, `length`, `pattern`, `enum`, `union`, `type`, `must`, `when`,
  `if-feature`, `mandatory`, `mandatory-choice`, `choice-multiple-cases`, `min-elements`,
  `max-elements`, `duplicate-key`, `unknown-field`, `leafref`, `identityref`,
  `instance-identifier`, `fraction-digits`, `bits`, `xpath-error`, `xpath-unknown-function`.
  Both validators emit the code; add it in both places when you need a new one.
- **`message`** (optional) must be a substring of the reported message. Use it for
  `error-message` from the module; free-text wording is otherwise not compared.

Runners call `validate_detailed` / `validateDetailed` and compare the **set** of `(path, code)`
pairs exactly: no missing errors, no extra errors. Duplicate pairs count once. `path` is the
JSON Pointer on the issue, not the legacy display string from `validate()`.

### Expected failures

Mark a known divergence with an `xfail` reason instead of weakening the expectation. Expected
failures are strict: when an implementation starts passing, its runner fails until the `xfail`
entry is removed. Write the expectation the RFC (or the documented xYang behavior) requires,
not what one implementation happens to do.

## Adding a case

1. Create `tests/cases/<area>/<case-name>/` with `m.yang` (`module m`, prefix `m`, namespace
   `urn:m` unless the case is about names) and `case.json`.
2. Keep it focused: one behavior, a valid instance and the smallest invalid ones.
3. Run both runners. If one implementation disagrees, decide which is right, then fix it or add
   an `xfail` reason for the wrong one.
4. When a shared case fully covers a per-language test, delete that test in both languages.

Instance data uses xYang's simple (unqualified) top-level member names, which both libraries
accept today. The RFC 7951 qualified form is covered in `encoding/qualified-names`.

## CLI protocol

The Python runner adds a `cli` implementation when
`XYANG_CLI` is set and calls, per instance:

```
$XYANG_CLI validate --format json <case-dir>/<module> <instance.json> \
    --include-path <case-dir> --features '<features as JSON, or null>'
```

and expects stdout to be `{"valid": bool, "errors": [{"path": "<JSON Pointer>", "code": "<code>", "message": "..."}]}`,
with the error codes listed above. Schema errors exit non-zero without that JSON.
`xfail` entries keyed `cli` apply to the Python CLI (they mirror `python`). When
`XYANG_CLI` is the TypeScript CLI (`*.js` or `xyang-ts`), the `ts` entries apply
instead, because that binary follows the TypeScript library.

## Known divergences

Each `xfail` entry in the cases is a known bug or gap. List them with:

```
rg -n '"(python|ts)": "' tests/cases --glob case.json
```
