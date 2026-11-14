# xYang

**Parse YANG modules, validate JSON instance data, and export JSON Schema—without a NETCONF stack.**

xYang targets real-world modules and pipelines: agents, CI, and schema tooling that need **RFC 7950-style checks** (`must`, `when`, `if-feature`, built-in types, leafrefs, and the rest) on **one consolidated JSON document** ([RFC 7951](https://www.rfc-editor.org/rfc/rfc7951)). It can also emit a **JSON Schema (2020-12)** view with **`x-yang`** metadata for round-trip where supported.

The same feature set is implemented in Python, TypeScript, and Zig:

| | **Python** (`xyang`) | **TypeScript** (`@exergy-connect/xyang`) | **Zig** (`xyang-zig`) |
|---|----------------------|------------------------------|------------------------|
| **Package** | [PyPI](https://pypi.org/project/xyang) `xyang` | [npm](https://www.npmjs.com/package/@exergy-connect/xyang) `@exergy-connect/xyang` | GitHub Release binary |
| **CLI** | `xyang` | `xyang-ts` | `xyang-zig` |
| **Runtime** | Python ≥ 3.11, zero required deps | Node ≥ 24 | none (static binary) |
| **Source** | [`src/xyang/`](src/xyang/) | [`ts/src/`](ts/src/) | [`zig/src/`](zig/src/) |

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

**Zig**

`xyang-zig` is one static executable: the same `parse`, `validate`, and `convert` commands as `xyang`, including `--help` / `-h` and `-V` / `--version`. It does not need Python, Node, or a shared library. `-V` prints the xYang version from `pyproject.toml`, the same text as `xyang -V`.

A published GitHub Release attaches one binary per platform. Linux builds are fully static (musl). macOS binaries link libSystem. Windows binaries do not need a MinGW runtime DLL.

| File | Platform |
| --- | --- |
| `xyang-zig-linux-x64` | Linux x64, fully static |
| `xyang-zig-linux-arm64` | Linux arm64, fully static |
| `xyang-zig-macos-arm64` | macOS Apple silicon |
| `xyang-zig-macos-x64` | macOS Intel |
| `xyang-zig-windows-x64.exe` | Windows x64 |
| `xyang-zig-windows-arm64.exe` | Windows arm64 |

```bash
chmod +x xyang-zig-linux-x64
./xyang-zig-linux-x64 --help
./xyang-zig-linux-x64 parse examples/meta-model.yang
./xyang-zig-linux-x64 validate examples/meta-model.yang data.json
./xyang-zig-linux-x64 convert examples/meta-model.yang -o meta-model.yang.json
```

Flags match `xyang`. `convert` writes `<stem>.yang.json` (or `-o PATH`); it does not print the schema on stdout.

Build it from a checkout with Zig 0.17.1 (the version pinned in `zig/build.zig.zon`):

```bash
cd zig && zig build -Doptimize=ReleaseSafe
./zig-out/bin/xyang-zig --help
```

An experimental [WebAssembly build](zig/wasm/README.md) embeds the same Zig
validation core in browsers and Wasm hosts, loading canonical `.yang.json` models
without WASI or filesystem access. New releases include `xyang.wasm` and its
JavaScript wrapper, `xyang.mjs`, as downloadable assets. To build from source:
`cd zig && zig build wasm -Doptimize=ReleaseSmall`.

### Standalone binary

Use the Zig `xyang-zig-<platform>` executable for agents, appliances, and minimal
CI images that need xYang without a Python or Node.js installation. Download it
from the [GitHub Releases](https://github.com/exergy-connect/xYang/releases)
assets; the platform list and build instructions are in the **Zig** section above.
Check the selected release's assets before scripting a download: older releases
may not include Zig binaries.

The binary uses `xyang` flags: `validate --format json` returns machine-readable
diagnostics, and `convert` writes `<stem>.yang.json` or the path supplied with
`-o`. When migrating from the former standalone `xyang-ts` executable, update the
asset and executable names and consume the output file from `convert` instead of
capturing its stdout. The Python and npm packages remain available as library APIs.

---

## Quick start

### CLI

Discover the commands and flags this revision implements with `xyang --help`, `xyang-ts --help`, `xyang-zig --help`, or `<command> --help` / `-h`. Help exits 0, writes to stdout, and does not open a YANG module or a data file. `xyang -V` / `xyang --version` and `xyang-zig -V` / `xyang-zig --version` print the package version. `xyang-ts` has no version flag.

```bash
# Python
xyang parse examples/meta-model.yang
xyang validate examples/meta-model.yang data.json
xyang convert examples/meta-model.yang -o meta-model.yang.json

# TypeScript (after build, or npx from package)
xyang-ts parse examples/meta-model.yang
xyang-ts validate examples/meta-model.yang data.json
xyang-ts convert examples/meta-model.yang

# Zig (release binary, or `cd zig && zig build`)
xyang-zig parse examples/meta-model.yang
xyang-zig validate examples/meta-model.yang data.json
xyang-zig convert examples/meta-model.yang -o meta-model.yang.json
```

Python and Zig `convert` write `<file>.yang.json` (or `-o PATH`); `xyang-ts convert` prints to stdout.

Validate one rpc's or action's input or output with `--rpc NAME` or `--action PATH` (input by default, `--output` for the output) and server data with `--context data.json` (required for an action). The context is validated first; its errors carry `"document": "context"`.

```bash
xyang validate --format json --rpc add-link model.yang rpc-input.json            # {"module:input": {...}}
xyang validate --rpc add-link --output --context state.json model.yang out.json
xyang validate --native-json --rpc add-link model.yang params.json              # bare parameters
xyang validate --action /ex:interfaces/interface=eth0/reset --context state.json model.yang in.json
```

`PATH` is the RFC 8040 §3.5.3 data resource identifier of the action node; the action node is a child of that instance in the XPath accessible tree (RFC 7950 §6.4.1). Details: [FEATURES.md](FEATURES.md#rpc-and-action-instances).

Shared flags: `--include-path DIR` (repeatable) for imports; on **validate**, `--anydata-validation off|complete|candidate` and `--anydata-module PATH` for validating RFC 7951 qualified JSON under `anydata` (see below).

### Python API

```python
from xyang import parse_yang_file, YangValidator

module = parse_yang_file("examples/meta-model.yang")
validator = YangValidator(module)

data = {"data-model": {"name": "example", "entities": []}}
is_valid, errors, warnings = validator.validate(data)
```

`validate()` returns a tuple `(is_valid, errors, warnings)`; each error is a string `"<path>: <message>"` with paths like `/top/items[id='a']/v`.

To validate an rpc's or action's input or output, name it: `validator.validate_detailed(data, rpc="add-link", direction="input", context=state)` or `action="/ex:interfaces/interface=eth0/reset"` (also `validate`, and `xyang.validate(schema, data, rpc=... | action=..., direction=..., context=...)`). `data` is `{"module:input": {...}}` (RFC 8040 §3.6), or the bare parameters with `native_json=True`. `context` is server data (required for an action), validated first; its issues carry `"document": "context"`. An unknown rpc or action raises `ValueError`.

### TypeScript API

```typescript
import { parseYangFile, YangValidator } from "@exergy-connect/xyang";

const module = parseYangFile("examples/meta-model.yang");
const validator = new YangValidator(module);

const result = validator.validate({ "data-model": { name: "example", entities: [] } });
```

`validate()` returns `{ isValid, errors, warnings }`; paths look like `top.items[0].v`.

To validate an rpc's or action's input or output, name it: `validator.validateDetailed(data, { rpc: "add-link", direction: "input", context })` or `{ action: "/ex:interfaces/interface=eth0/reset", context }` (also `validate`, and the top-level `validate(schema, data, { rpc | action, direction, context })`). `data` is `{"module:input": {...}}` (RFC 8040 §3.6), or the bare parameters with `nativeJson: true`. `context` is server data (required for an action), validated first; its issues carry `document: "context"`. An unknown rpc or action throws.

RFC 7951 JSON is the default for instance input (the JSON document, not the schema `.yang.json` file). There is no fallback between encodings. RFC 7951 lists are arrays, `int64` / `uint64` / `decimal64` are strings, and `empty` is `[null]`. `--native-json` (Python `native_json=True`, TypeScript `{ nativeJson: true }`, case.json `"encoding": "native"`) enables native dict-style input: keyed objects for single-key lists, bare names, JSON numbers, and `null` for empty. Error paths point at the input as written (`/m:top/interface/0/mtu` or `/top/interface/eth0/mtu`). In RFC mode a union follows member order, so `"5"` in `union { type int64; type string; }` is an int64. In native mode a string stays a string.

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

## Example: audit engagement as a distributed hypergraph

The [ontology hypergraph example](examples/ontology-hypergraph/README.md) models a fictional audit of a fictional client in one YANG model: employees, accounts, terminations, sign-ins, privileged changes, controls, evidence, assessments, findings, and reviews. Times are numeric, so `must` expressions compare them. Each fact's declared breach is checked against the facts, and every outcome and finding must agree with them: the sample is valid because it reports a real breach, and hiding or inventing one is invalid. Four parties publish over HTTP; the collector merges them, verifies model and export digests, and validates with xYang. Optional pyang/Yangson and OWL RL checks and a [traceability matrix](examples/ontology-hypergraph/TRACEABILITY.md) are included.

## What xYang does (and does not)

**Does**

- Parse YANG 1.1-shaped modules: containers, lists, leaves, choices, groupings, augments, features, imports, and common constraints.
- Validate a **single JSON instance tree** against the module data model (types, cardinality, `must` / `when`, `if-feature`, leafrefs, identityrefs, etc.).
- Optional **anydata subtree validation** for opaque payloads (YANG Push notifications, RPC output shapes, etc.) per [draft-ietf-netmod-yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation).
- Export **JSON Schema** with **`x-yang`** annotations for tooling and round-trip where supported.

**Does not (today)**

- NETCONF/RESTCONF servers, XML instance encoding, or incremental edit validation.
- Full RFC 7950 surface (`notification` instance validation is limited—see **FEATURES.md**).
- A generic XPath 1.0 engine; expressions are evaluated in **schema context** for `must` / `when` (subset documented in **FEATURES.md**).

Supported subset and RFC deviations: [FEATURES.md](FEATURES.md#deviations-from-rfc-7950--rfc-7951).

Grammar: [design/yang-ebnf-supported-constructs.md](design/yang-ebnf-supported-constructs.md).

---

## Browser ES modules

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

---

## Benchmarks

Time, peak memory, and source lines for both implementations, refreshed by the
[Benchmark workflow](.github/workflows/benchmark.yml) when a release is
published. Methodology and limitations: [benchmarks/README.md](benchmarks/README.md).

<!-- xyang-benchmark:start -->
_Generated by `benchmarks/release_bench.py`; do not edit by hand. Methodology and limitations: [benchmarks/README.md](benchmarks/README.md)._

- **Version:** xyang 1.0.2 (PyPI), @exergy-connect/xyang 1.0.2 (npm) (release `v1.0.2`)
- **Commit:** `d24c840f9c10`, measured 2026-11-14T05:18:12+00:00
- **Runtimes:** CPython 3.12.16, Node.js v24.22.2
- **Machine:** GitHub Actions ubuntu24 image 20261111.370.1 (X64); Linux 7.0.0-1017-azure x86_64; AMD EPYC 9V45 96-Core Processor (4 logical CPUs, 15.6 GiB RAM)

Time (warm, in-process, measured call only):

| Workload | Phase | Python median | TypeScript median | Timed iterations |
|---|---|---|---|---|
| small | parse | 9.29 ms | 5.42 ms | 90 (3 processes × 30, 5 warmup each) |
| small | validate | 4.90 ms | 0.68 ms | 150 (3 processes × 50, 10 warmup each) |
| large | parse | 48.5 ms | 27.6 ms | 30 (3 processes × 10, 2 warmup each) |
| large | validate | 1,519 ms | 207 ms | 15 (3 processes × 5, 1 warmup each) |
| none | process startup | 113 ms wall | 27.4 ms wall | 10 processes |

Peak process memory (fresh process, one operation, no warmup; total process peak):

| Workload | Operation | Python peak RSS | TypeScript peak RSS | Processes |
|---|---|---|---|---|
| small | import + parse workload modules once | 19.5 MiB | 64.6 MiB | 5 × 1 operation |
| small | import + parse schema + decode JSON + build validator + validate once | 19.6 MiB | 65.8 MiB | 5 × 1 operation |
| large | import + parse workload modules once | 20.8 MiB | 79.9 MiB | 5 × 1 operation |
| large | import + parse schema + decode JSON + build validator + validate once | 101.4 MiB | 252.2 MiB | 5 × 1 operation |
| none | process startup (library loaded) | 17.9 MiB | 49.2 MiB | 10 |

Workloads:

- **small** (meta-model sample): parse 1 module(s), 835 YANG lines; validate `examples/meta-model.yang` against 4,884 bytes of JSON (checked-in copy of tests/data/new_meta_model_sample.yaml as JSON).
- **large** (IETF modules + 10k-interface inventory): parse 4 module(s), 4,696 YANG lines; validate `benchmarks/workloads/interface-inventory.yang` against 2,097,811 bytes of JSON, 10,016 list entries (synthetic, generated by benchmarks/workloads.py: 10000 interfaces, 16 LAGs, pinned SHA-256).

Time is the median over all timed iterations of the measured call only (no startup, imports, file reads, or setup). Memory comes from separate fresh processes, not the timing processes: each loads the runtime and library, does the setup, runs the operation once, and reports its own high-water resident set size (Linux `VmHWM`). The figure is the median over processes in MiB (2^20 bytes) and is the whole process peak: runtime, library, setup, inputs, the operation, and garbage not yet collected. No startup baseline is subtracted, no garbage collection is forced, and no runtime flags are set. The startup rows are processes that only load the library.

Code size (separate from performance; nonblank, noncomment lines, docstrings excluded):

| Language | Counted | Files | Code lines |
|---|---|---|---|
| Python | `src/xyang/**/*.py` | 83 | 14,271 |
| TypeScript | `ts/src/**/*.ts` | 85 | 15,774 |

Executable size:

| Binary | Bytes | KiB |
|---|---:|---:|
| Zig CLI (`xyang-zig`) | 790,808 | 772.3 |

Reproduce: `python benchmarks/release_bench.py run --zig-binary zig/zig-out-benchmark/bin/xyang-zig --out benchmarks/results/latest.json && python benchmarks/release_bench.py update-readme benchmarks/results/latest.json`
<!-- xyang-benchmark:end -->

---

## Repository layout

```
xYang/
├── src/xyang/          # Python library + xyang CLI
├── ts/                 # TypeScript package (@exergy-connect/xyang) + xyang-ts CLI
├── zig/                # Native Zig library + standalone xyang-zig CLI
├── examples/           # meta-model.yang, ietf-yang-push/, samples
├── tests/              # Python tests
├── benchmarks/         # Release benchmark harness and workloads
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
| **Release Zig binaries** | [`.github/workflows/zig-release.yml`](.github/workflows/zig-release.yml) | On a published release, builds six `xyang-zig` executables for Linux, macOS, and Windows (x64 and arm64), smoke-tests Linux x64, builds and tests the freestanding Wasm library, and attaches the binaries plus `xyang.wasm` and `xyang.mjs`. A manual run uploads workflow artifacts only |
| **Benchmark** | [`.github/workflows/benchmark.yml`](.github/workflows/benchmark.yml) | On a published release, measures time, peak memory, and source lines, attaches `benchmark-<tag>.json` to the release, and opens a pull request that refreshes the README benchmark section. On `workflow_dispatch`, measures and uploads a workflow artifact (`open_pr` also proposes the README update). On pull requests touching benchmark files, a smoke run only |
| **Ontology example** | [`.github/workflows/ontology-example.yml`](.github/workflows/ontology-example.yml) | On a published release, runs `pytest -m ontology` with the optional pyang and OWL RL tools installed, and `npm run test:ontology`. A skipped Python test fails the job. `workflow_dispatch` runs the same checks and publishes nothing. Pull requests do not run these tests |

The TypeScript test workflow runs on pushes to `main` and on pull requests that touch `ts/**` (and related paths). It builds the release bundles and does not commit or upload them. The Zig binaries and the TypeScript bundles are attached only when a release is published. The stdout flush is covered by the TypeScript test suite.

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
    version: v1.0.0

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

Pin `version` to a release tag that published the `xyang-ts.mjs` asset. v1.0.0 is the first release with it; earlier tags have no assets.

---

## License

MIT License
