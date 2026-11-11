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
`modules`, `encoding`, `operations`. One case directory per schema; put several instances in one case
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
| `json_form` | Optional. `true`: every instance must also give the same result against the module reloaded from its native JSON form (convert, serialise, `parse_json_schema` / `parseJsonSchema` with no include path), and `expected.yang.json` in the case directory is the form both libraries must generate (compared as JSON). The case may not rely on another module augmenting the primary one. |
| `export_error` | Optional. A substring of the error that exporting the primary module to its native JSON form must raise (no `instances`). `convert` exits 2. |
| `xfail` | Optional, on the case or on an instance (instance entries override case entries). Implementation id (`python`, `ts`, `cli`) -> reason. |
| `instances[].data` | The JSON instance document. |
| `instances[].valid` | Whether the implementation must report no errors. |
| `instances[].errors` | Expected errors when `valid` is `false`. |
| `instances[].rpc` | Optional. Validate `data` as an instance of this rpc (`validate_detailed(rpc=)` / `{ rpc }`, CLI `--rpc`). |
| `instances[].action` | Optional. Validate `data` as an instance of the action at this RFC 8040 §3.5.3 path (`action=` / `{ action }`, CLI `--action`). Needs `context`. |
| `instances[].direction` | Optional, with `rpc` or `action`: `"input"` (default) or `"output"` (CLI `--output`). |
| `instances[].context` | Optional, with `rpc` or `action`: server data (`context=` / `{ context }`, CLI `--context FILE`). Same encoding as `data`. Validated first. |
| `instances[].usage_error` | Optional. Instead of `valid` and `errors`: the call itself must be rejected (Python `ValueError`, TypeScript throw with the text as a substring of the message, CLI exit 2 with empty stdout). |

### Expected errors

An error is `{ "path", "code", "message"?, "document"? }`. `document: "context"` marks an issue about an rpc's or action's context; its `path` points into the context, and runners compare it as `context:<path>`:

- **`path`** is a [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) into the input as written.
  RFC 7951 lists use array indexes (`/m:top/interface/0/mtu`). A native keyed list uses the dict
  key (`/top/interface/eth0/mtu`). Member names are the ones in the JSON (`/m:top/a`, not a
  rewritten `/top/a`). The document root is `""`. Errors about a missing node point at where it
  would be (`/top/name`). `choice` and `case` are not data nodes, so their errors point at the
  parent data node (`/top`).
- **`code`** is one of `range`, `length`, `pattern`, `enum`, `union`, `type`, `must`, `when`,
  `if-feature`, `mandatory`, `mandatory-choice`, `choice-multiple-cases`, `min-elements`,
  `max-elements`, `duplicate-key`, `unique`, `unknown-field`, `ambiguous-name`, `key-mismatch`,
  `list-encoding`, `leafref`, `identityref`, `instance-identifier`, `fraction-digits`, `bits`,
  `xpath-error`, `xpath-unknown-function`, `operation-wrapper`, `action-parent`.
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

Instance data defaults to strict RFC 7951. Set `"encoding": "native"` on an instance for native
JSON (`encoding/dict-style`). The two modes do not fall back to each other. Paths point into the
input as written. Other `module` files in the case directory (not `submodule` files) are parsed
after the primary module so their `augment` statements merge into it.

`operation-wrapper` — rpc or action input or output in RFC 7951 mode is not the single member `module:input` / `module:output` (RFC 8040 §3.6); native JSON takes the bare parameters. `action-parent` — the context lacks the instance an action is invoked on (`document: "context"`, path `""`).

`ambiguous-name` — a bare member name matches more than one node. `key-mismatch` — a native
list entry's key leaf is present and is not the dict key. `list-encoding` — a list with more
than one key was given as an object; multi-key lists are arrays only.

## CLI protocol

The Python runner adds a `cli` implementation when
`XYANG_CLI` is set and calls, per instance:

```
$XYANG_CLI validate --format json <case-dir>/<module> <instance.json> \
    --include-path <case-dir> --features '<features as JSON, or null>'
```

An instance with `rpc` adds `--rpc <name>` (`action`: `--action <path>`), `--output` for
`direction: "output"`, and `--context <file>` for `context`. The CLI loads only the primary module, so cases whose
other modules augment it fail under `XYANG_CLI`; the library runners load them.

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
