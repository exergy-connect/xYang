# xYang

**Parse YANG modules, validate JSON instance data, and export JSON Schema—without a NETCONF stack.**

xYang targets real-world modules and pipelines: agents, CI, and schema tooling that need **RFC 7950-style checks** (`must`, `when`, `if-feature`, built-in types, leafrefs, and the rest) on **one consolidated JSON document** ([RFC 7951](https://www.rfc-editor.org/rfc/rfc7951)). It can also emit a **JSON Schema (2020-12)** view with **`x-yang`** metadata for round-trip where supported.

The same feature set is implemented twice:

| | **Python** (`xyang`) | **TypeScript** (`@exergy-connect/xyang`) |
|---|----------------------|------------------------------|
| **Package** | [PyPI](https://pypi.org/project/xyang) `xyang` | [npm](https://www.npmjs.com/package/@exergy-connect/xyang) `@exergy-connect/xyang` |
| **CLI** | `xyang` | `xyang-ts` |
| **Runtime** | Python ≥ 3.11, zero required deps | Node ≥ 24 |
| **Source** | [`src/xyang/`](src/xyang/) | [`ts/src/`](ts/src/) |

Not every YANG statement is modeled; unsupported constructs are skipped with a warning so mixed modules still load. See [**FEATURES.md**](FEATURES.md) for the full matrix, JSON hybrid format, and known gaps.

**Repository:** [github.com/exergy-connect/xYang](https://github.com/exergy-connect/xYang) · **npm:** [`@exergy-connect/xyang`](https://www.npmjs.com/package/@exergy-connect/xyang) · **Issues:** [github.com/exergy-connect/xYang/issues](https://github.com/exergy-connect/xYang/issues)

MIT licensed.

---

## Native JSON format: intent

The xYang native JSON format is an optimized, reversible transformation of standard YANG files. Like JSON to YAML, it carries the same information. `xyang convert` and `schema_to_yang_json` write the `.yang.json` file; `parse_json_schema` loads it. TypeScript uses `generateJsonSchema` and `parseJsonSchema`.

- **Reversible.** Converting back must produce equivalent YANG.
- **Unambiguous.** Each construct has one canonical form.
- **Fast to load.** Processing uses the JSON and does not parse YANG text at runtime.

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

### Standalone binary

The TypeScript CLI is also built as a single executable with [QuickJS-ng](https://github.com/quickjs-ng/quickjs) 0.18.0. It is the same `parse` / `validate` / `convert` commands, with no Node.js or Python install. The linux-x64 build is about 1 MB and starts in a few milliseconds, so an agent or a small CI image can shell out to it directly.

This does not replace the Python package or the npm package. Those stay the supported library APIs.

A published GitHub Release attaches:

| File | Platform |
| --- | --- |
| `xyang-ts-linux-x64` | Linux x64, fully static |
| `xyang-ts-linux-arm64` | Linux arm64, fully static |
| `xyang-ts-macos-arm64` | macOS Apple silicon |
| `xyang-ts-macos-x64` | macOS Intel |
| `xyang-ts-windows-x64.exe` | Windows x64 |

```bash
chmod +x xyang-ts-linux-x64
./xyang-ts-linux-x64 parse examples/meta-model.yang
./xyang-ts-linux-x64 validate examples/openconfig/openconfig-interfaces-subset.yang \
  examples/openconfig/sample_interfaces.json
./xyang-ts-linux-x64 convert examples/meta-model.yang
```

Flags match `xyang-ts`. Piped output is flushed before exit, including JSON Schema documents larger than Node's 64 KiB pipe buffer.

Build it from a checkout (Zig 0.14.1 and the TypeScript dependencies; details in [`qjs/README.md`](qjs/README.md)):

```bash
cd ts && npm ci && npm run build
cd ../qjs && ./build.sh linux-x64
./smoke.sh dist/xyang-ts-linux-x64
```

`./build.sh all` also cross-compiles linux-arm64, macOS, and Windows. Linux binaries are static musl. macOS binaries link libSystem.

A `--format json` mode and an MCP server are follow-ups. This binary does not add either.

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
├── qjs/                # QuickJS-ng static executable of the TypeScript CLI
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

**TypeScript** (Node.js 24 or newer; `.nvmrc` / `.node-version` pin the version local tools and CI use)

```bash
cd ts && npm install && npm test
```

`npm test` does not require a prior build. Library and CLI bundles are produced with `tsdown` (`npm run build`). The browser IIFE is a separate esbuild step.

---

## GitHub Actions

### Workflows in this repository

| Workflow | File | Purpose |
|----------|------|---------|
| **Tests (TypeScript)** | [`.github/workflows/tests-ts.yml`](.github/workflows/tests-ts.yml) | `npm run lint`, `npm run build:check`, `npm run build:ci`, and `npm test` in `ts/` on the Node version in `.nvmrc` and on the latest LTS. The `build:ci` step is a check only: it does not commit or upload |
| **Release TypeScript artifacts** | [`.github/workflows/release-artifacts.yml`](.github/workflows/release-artifacts.yml) | On a published release, runs `npm run build:ci` and attaches `artifacts/xyang-ts.mjs` and `docs/xyang.umd.min.js`. On `workflow_dispatch`, uploads those files as workflow artifacts only |
| **Release QuickJS binaries** | [`.github/workflows/qjs-release.yml`](.github/workflows/qjs-release.yml) | On a published release, builds all five `xyang-ts` executables, smoke-tests the Linux binaries against the Node CLI, and attaches the files. Also runnable by hand (`workflow_dispatch`) without attaching anything |

The TypeScript test workflow runs on pushes to `main` and on pull requests that touch `ts/**` (and related paths). It builds the release bundles and does not commit or upload them. The QuickJS binaries and the TypeScript bundles are attached only when a release is published. The stdout flush is covered by the TypeScript test suite.

### Release artifacts

[`ts/scripts/build-ci-artifacts.mjs`](ts/scripts/build-ci-artifacts.mjs) writes two bundles. They are gitignored and are not committed. A published GitHub Release attaches them (see **Release TypeScript artifacts** above). The same files can be downloaded from the release assets.

| File | Role |
|------|------|
| `artifacts/xyang-ts.mjs` | Single-file Node CLI (`parse`, `validate`, `convert`), published as a release asset |
| `docs/xyang.umd.min.js` | Browser IIFE library bundle, published as a release asset |

Build them locally:

```bash
cd ts && npm install && npm run build:ci
```

The full npm package under `ts/dist/` is **not** committed; use `npm run build:check` for publish-style validation.

### `xyang-ts` composite action (other repositories)

Reuse [`.github/actions/xyang-ts`](.github/actions/xyang-ts/action.yml) to download `xyang-ts.mjs` from a GitHub Release and run the CLI — no `npm install`, checkout, or build step in the consumer workflow.

**Minimal validate job:**

```yaml
jobs:
  validate-yang:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: exergy-connect/xYang/.github/actions/xyang-ts@main
        with:
          version: latest
          command: validate
          yang-file: model/example.yang
          data-file: data/instance.json
          include-path: model/
```

**Inputs**

| Input | Default | Description |
|-------|---------|-------------|
| `repository` | `exergy-connect/xYang` | xYang GitHub repository |
| `version` | `latest` | Release tag whose `xyang-ts.mjs` asset to download, or `latest` |
| `command` | *(empty)* | `parse`, `validate`, or `convert`. Omit to only expose `xyang-ts` on `PATH` |
| `yang-file` | *(empty)* | YANG module path (required when `command` is set) |
| `data-file` | *(empty)* | JSON instance path for `validate` |
| `include-path` | *(empty)* | Module search directories (`--include-path`, one per line) |
| `working-directory` | *(empty)* | Directory for the `xyang-ts` invocation |

**Outputs:** `cli` (absolute path to the downloaded `xyang-ts.mjs`).

**Setup only** (run multiple commands in later steps):

```yaml
- uses: exergy-connect/xYang/.github/actions/xyang-ts@main
  id: xyang
  with:
    version: v0.1.4

- run: xyang-ts parse model/example.yang
- run: xyang-ts convert model/example.yang
```

**Anydata validation** (use setup-only mode; flags are CLI-only):

```yaml
- uses: exergy-connect/xYang/.github/actions/xyang-ts@main
  with:
    version: latest

- run: |
    xyang-ts validate modules/host.yang data/envelope.json \
      --include-path modules/ \
      --anydata-validation complete \
      --anydata-module modules/payload.yang
```

Pin `version` to a release tag that published the `xyang-ts.mjs` asset.

---

## License

MIT License


### Browser ES modules

The npm package includes a self-contained browser ESM bundle at
`@exergy-connect/xyang/browser`. Resolve that export in your build tool or copy
the resolved file and its adjacent source map to your static assets:

```js
import { parseYangString, YangValidator } from "@exergy-connect/xyang/browser";

const validator = new YangValidator(parseYangString(source));
const result = validator.validate(data);
```

Validation rejects unknown fields at the document root, in containers, and in
list entries. Arbitrary payloads belong in modeled `anydata` or `anyxml` nodes.
The browser bundle supports string parsing; filesystem parsing requires Node.js.

## Infer required YANG features (API)

For models gated by feature names or positive `and` conjunctions, infer the
minimum feature requirements from the elements present in an instance:

```typescript
import { parseYangString, inferRequiredFeatures } from "@exergy-connect/xyang";

const module = parseYangString(`module example {
  namespace "urn:example"; prefix ex;
  feature statistics;
  leaf count { if-feature "statistics"; type uint32; }
}`);
const features = inferRequiredFeatures(module, { "example:count": 3 });
// ["example:statistics"]
```

The result is a sorted, deduplicated list of `module-name:feature` strings (not
import prefixes). It includes gates on enclosing containers, lists, choices and
cases, gates carried by expanded uses/augments, and transitive feature
prerequisites. Absent nodes contribute nothing; an empty document returns `[]`.
Parse with uses expansion enabled (the default). Both unqualified members in the
current module and module-qualified members are accepted.

This API infers requirements from member presence; it does not validate values,
mandatory nodes, or other constraints. `anydata` and `anyxml` contents are opaque.
It throws for unknown or ambiguous instance members, unknown features, cyclic
prerequisites, malformed container/list structure, and encountered expressions
outside simple feature atoms or `and` conjunctions (`or`, `not`, and parentheses
are unsupported). Unsupported conditions on absent branches are not evaluated.

Python exposes the same workflow:

```python
from xyang import parse_yang_string, infer_required_features

module = parse_yang_string('''module example {
  namespace "urn:example"; prefix ex;
  feature statistics;
  leaf count { if-feature "statistics"; type uint32; }
}''')
features = infer_required_features(module, {"example:count": 3})
# ["example:statistics"]
```

Python raises `ValueError` for the inference errors described above. TypeScript
throws `Error`. The returned list contains requirements only; when configuring a
validator (Python `YangValidator(module, enabled_features_by_module=...)`,
TypeScript `new YangValidator(module, { enabledFeaturesByModule })`), group these
names by module and explicitly supply empty sets for modules with no required
features, since omitted modules otherwise default to all features enabled.
