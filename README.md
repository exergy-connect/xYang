# xYang

**Parse YANG modules, validate JSON instance data, and export JSON Schema—without a NETCONF stack.**

xYang targets real-world modules and pipelines: agents, CI, and schema tooling that need **RFC 7950-style checks** (`must`, `when`, `if-feature`, built-in types, leafrefs, and the rest) on **one consolidated JSON document** ([RFC 7951](https://www.rfc-editor.org/rfc/rfc7951)). It can also emit a **JSON Schema (2020-12)** view with **`x-yang`** metadata for round-trip where supported.

The same feature set is implemented twice:

| | **Python** (`xyang`) | **TypeScript** (`@exergy-connect/xyang`) |
|---|----------------------|------------------------------|
| **Package** | [PyPI](https://pypi.org/project/xyang) `xyang` | [npm](https://www.npmjs.com/package/@exergy-connect/xyang) `@exergy-connect/xyang` |
| **CLI** | `xyang` | `xyang-ts` |
| **Runtime** | Python ≥ 3.10, zero required deps | Node ≥ 24 |
| **Source** | [`src/xyang/`](src/xyang/) | [`ts/src/`](ts/src/) |

Not every YANG statement is modeled; unsupported constructs are skipped with a warning so mixed modules still load. See [**FEATURES.md**](FEATURES.md) for the full matrix, JSON hybrid format, and known gaps.

**Repository:** [github.com/exergy-connect/xYang](https://github.com/exergy-connect/xYang) · **npm:** [`@exergy-connect/xyang`](https://www.npmjs.com/package/@exergy-connect/xyang) · **Issues:** [github.com/exergy-connect/xYang/issues](https://github.com/exergy-connect/xYang/issues)

MIT licensed.

---

## Install

**Python**

```bash
pip install xyang
# development: pip install -e .
```

Optional: **PyYAML** for `.yaml` / `.yml` instance files on `xyang validate`.

**TypeScript**

```bash
npm install @exergy-connect/xyang
# from checkout:
cd ts && npm install && npm run build
```

---

## Quick start

### CLI

```bash
# Python
xyang parse examples/meta-model.yang
xyang validate examples/meta-model.yang data.json
xyang convert examples/meta-model.yang -o meta-model.yang.json

# TypeScript (after build, or npx from package)
xyang-ts parse examples/meta-model.yang
xyang-ts validate examples/meta-model.yang data.json
xyang-ts convert examples/meta-model.yang
```

Shared flags: `--include-path DIR` (repeatable) for imports; on **validate**, `--anydata-validation off|complete|candidate` and `--anydata-module PATH` for validating RFC 7951 qualified JSON under `anydata` (see below).

### Python API

```python
from xyang import parse_yang_file, YangValidator

module = parse_yang_file("examples/meta-model.yang")
validator = YangValidator(module)

data = {"data-model": {"name": "example", "entities": []}}
is_valid, errors, warnings = validator.validate(data)
```

### TypeScript API

```typescript
import { parseYangFile, YangValidator } from "@exergy-connect/xyang";

const module = parseYangFile("examples/meta-model.yang");
const validator = new YangValidator(module);

const result = validator.validate({ "data-model": { name: "example", entities: [] } });
```

---

## Example: IETF YANG Push notification

Under [`examples/ietf-yang-push/`](examples/ietf-yang-push/) there is a captured device notification: [`27-push-update.json`](examples/ietf-yang-push/27-push-update.json) uses the [RFC 8791](https://www.rfc-editor.org/rfc/rfc8791) envelope (`ietf-yp-notification:envelope`) with a `ietf-yang-push:push-change-update` payload in `contents` **anydata**. The `modules/` directory is the publisher YANG library.

Validate the envelope and the qualified subtree under `contents`:

**Python**

```bash
xyang validate \
  examples/ietf-yang-push/modules/ietf-yp-notification@2025-06-04.yang \
  examples/ietf-yang-push/27-push-update.json \
  --include-path examples/ietf-yang-push/modules \
  --anydata-validation complete \
  --anydata-module examples/ietf-yang-push/modules/ietf-yang-push@2019-09-09.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-yp-observation@2025-02-24.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms-x733@2019-09-11.yang
```

**TypeScript** (same flags; run from repo root after `cd ts && npm run build`)

```bash
node ts/dist/cli.js validate \
  examples/ietf-yang-push/modules/ietf-yp-notification@2025-06-04.yang \
  examples/ietf-yang-push/27-push-update.json \
  --include-path examples/ietf-yang-push/modules \
  --anydata-validation complete \
  --anydata-module examples/ietf-yang-push/modules/ietf-yang-push@2019-09-09.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-yp-observation@2025-02-24.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms-x733@2019-09-11.yang
```

- **Host module** — `ietf-yp-notification` defines `envelope` (`event-time`, `hostname`, `sequence-number`, `contents` anydata).
- **`--anydata-validation complete`** — validates RFC 7951 `module:node` members under `contents` (push update, observation timestamps, nested alarm notification in a `yang-patch` edit, etc.).
- **`--anydata-module`** — loads only the modules needed for that subtree; imports resolve via `--include-path`. Omit it to scan every `*.yang` under the include path (slower).

Use `candidate` instead of `complete` for structural checks only (no `must` / `when` / types on the anydata subtree). More detail: [`examples/ietf-yang-push/README.md`](examples/ietf-yang-push/README.md), [`examples/anydata_validation_usage.py`](examples/anydata_validation_usage.py).

---

## What xYang does (and does not)

**Does**

- Parse YANG 1.1-shaped modules: containers, lists, leaves, choices, groupings, augments, features, imports, and common constraints.
- Validate a **single JSON instance tree** against the module data model (types, cardinality, `must` / `when`, `if-feature`, leafrefs, identityrefs, etc.).
- Optional **anydata subtree validation** for opaque payloads (YANG Push notifications, RPC output shapes, etc.) per [draft-ietf-netmod-yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation).
- Export **JSON Schema** with **`x-yang`** annotations for tooling and round-trip where supported.

**Does not (today)**

- NETCONF/RESTCONF servers, XML instance encoding, or incremental edit validation.
- Full RFC 7950 surface (`rpc` / `notification` / `deviation` instance validation is limited or skipped—see **FEATURES.md**).
- A generic XPath 1.0 engine; expressions are evaluated in **schema context** for `must` / `when` (subset documented in **FEATURES.md**).

---

## Repository layout

```
xYang/
├── src/xyang/          # Python library + xyang CLI
├── ts/                 # TypeScript package (@exergy-connect/xyang) + xyang-ts CLI
├── examples/           # meta-model.yang, ietf-yang-push/, samples
├── tests/              # Python tests
├── FEATURES.md         # Authoritative feature list
└── pyproject.toml      # PEP 517/621 project metadata and tooling config
```

---

## Development

**Python**

```bash
pip install -e ".[dev]"
pytest
```

**TypeScript**

```bash
cd ts && npm install && npm test
```

`typescript` is pinned to **6.x** (not 7) because `tsup` 8.5.1 bundles `rollup-plugin-dts` for `dts: true` builds, and that toolchain fails under TypeScript 7 with `useCaseSensitiveFileNames` errors during `.d.ts` generation. Revisit when [tsup#1405](https://github.com/egoist/tsup/issues/1405) is resolved or `tsup` ships a compatible `rollup-plugin-dts`.

---

## GitHub Actions

### Workflows in this repository

| Workflow | File | Purpose |
|----------|------|---------|
| **Tests (TypeScript)** | [`.github/workflows/tests-ts.yml`](.github/workflows/tests-ts.yml) | `npm run lint`, `npm run build:check`, and `npm test` in `ts/` on Node 24 |
| **Build TypeScript CI artifacts** | [`.github/workflows/build-ts-dist.yml`](.github/workflows/build-ts-dist.yml) | Runs `npm run build:ci` and keeps committed build artifacts in sync |

Both workflows run on pushes to `main` and on pull requests that touch `ts/**` (and related paths).

### Committed CI artifacts

The **Build TypeScript CI artifacts** workflow commits two bundled outputs produced by [`ts/scripts/build-ci-artifacts.mjs`](ts/scripts/build-ci-artifacts.mjs):

| File | Role |
|------|------|
| [`artifacts/xyang-ts.mjs`](artifacts/xyang-ts.mjs) | Single-file Node CLI (`parse`, `validate`, `convert`) |
| [`docs/xyang.umd.min.js`](docs/xyang.umd.min.js) | Browser IIFE library bundle |

Regenerate locally:

```bash
cd ts && npm install && npm run build:ci
git add -f artifacts/xyang-ts.mjs docs/xyang.umd.min.js
```

On **same-repo** PRs and pushes to `main`, the workflow auto-commits when artifacts drift. On **fork** PRs, the check fails instead (no write access to the contributor branch).

The full npm package under `ts/dist/` is **not** committed; use `npm run build:check` for publish-style validation.

### `xyang-ts` composite action (other repositories)

Reuse [`.github/actions/xyang-ts`](.github/actions/xyang-ts/action.yml) to check out xYang and run the CLI from committed `artifacts/xyang-ts.mjs` — no `npm install` or build step in the consumer workflow.

**Minimal validate job:**

```yaml
jobs:
  validate-yang:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: exergy-connect/xYang/.github/actions/xyang-ts@main
        with:
          ref: main
          command: validate
          args: model/example.yang data/instance.json --include-path model/
```

**Inputs**

| Input | Default | Description |
|-------|---------|-------------|
| `repository` | `exergy-connect/xYang` | xYang GitHub repository |
| `ref` | `main` | Branch, tag, or SHA (must include committed `artifacts/xyang-ts.mjs`) |
| `path` | `.xyang` | Checkout directory under the workflow workspace |
| `command` | *(empty)* | `parse`, `validate`, or `convert`. Omit to only expose `xyang-ts` on `PATH` |
| `args` | *(empty)* | Remaining CLI arguments (space-separated) |
| `working-directory` | *(empty)* | Directory for the `xyang-ts` invocation |

**Outputs:** `cli` (path to `artifacts/xyang-ts.mjs`), `xyang-root` (xYang repo root).

**Setup only** (run multiple commands in later steps):

```yaml
- uses: exergy-connect/xYang/.github/actions/xyang-ts@main
  id: xyang
  with:
    ref: v0.1.2

- run: xyang-ts parse model/example.yang
- run: xyang-ts convert model/example.yang
```

**Anydata validation** (same flags as the CLI):

```yaml
- uses: exergy-connect/xYang/.github/actions/xyang-ts@main
  with:
    command: validate
    args: >-
      modules/host.yang data/envelope.json
      --include-path modules/
      --anydata-validation complete
      --anydata-module modules/payload.yang
```

Pin `ref` to a release tag or SHA once this workflow is on `main`.

---

## License

MIT License
