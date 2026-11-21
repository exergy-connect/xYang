# Benchmarks

`release_bench.py` measures time, peak memory, and source lines for the Python
and TypeScript implementations, and optionally benchmarks the Zig CLI on the same inputs. Its results go into the
marked benchmark section of the repository [README](../README.md) and into
[`results/latest.json`](results/latest.json).

`parse_bench.py`, `benchmark.py`, and `ts/bench/parse.bench.ts` are older
developer timing and profiling scripts. They are not part of the release
numbers.

## Run

From the repository root, with Python 3.11+ and Node.js 24 (`.nvmrc`):

```bash
pip install -e .
(cd ts && npm ci)
python benchmarks/release_bench.py run --out benchmarks/results/latest.json
python benchmarks/release_bench.py update-readme benchmarks/results/latest.json
```

Other commands:

| Command | Purpose |
|---|---|
| `run --smoke --out FILE` | 1 process, 1 iteration, no warmup. Checks the harness works; never goes into the README. |
| `run --languages python --workloads small` | Subset run. |
| `run --zig-cli PATH --zig-binary PATH --zig-build ReleaseSafe` | Add end-to-end Zig CLI time and memory, and record its binary size and build configuration (Linux with GNU time). |
| `render FILE` | Print the README Markdown for a results file. |
| `update-readme FILE --check` | Exit 1 if the README section differs from what `FILE` renders. |
| `validate FILE` | Check a results file against the schema. |

`update-readme` replaces only the text between `<!-- xyang-benchmark:start -->`
and `<!-- xyang-benchmark:end -->`, and running it twice gives the same file. It
refuses smoke results and results measured on a dirty working tree (tracked
files modified), unless `--allow-dirty` is passed.

## Workloads

Both workers get the same resolved spec: absolute paths of the modules, their
include directories, and the instance file. They call the public API with
equivalent arguments (`parse_yang_file` / `parseYangFile`, `YangValidator` with
`validate_detailed` / `validateDetailed`). Defined in [`workloads.py`](workloads.py).

| Workload | Parse | Validate |
|---|---|---|
| `small` | `examples/meta-model.yang` (1 module, 835 lines) | the meta-model against [`workloads/meta-model-sample.json`](workloads/meta-model-sample.json) (4.9 kB; a JSON copy of `tests/data/new_meta_model_sample.yaml`) |
| `large` | 4 IETF and example modules (4,696 lines): `ietf-alarms`, `ietf-subscribed-notifications`, `ietf-interfaces`, `meta-model` | [`workloads/interface-inventory.yang`](workloads/interface-inventory.yang) against a generated RFC 7951 instance: 10,000 interfaces and 16 LAGs, 2.1 MB |

The large instance is generated at run time by `inventory_instance()` with no
randomness, then checked against the pinned SHA-256 `INVENTORY_SHA256`. A
mismatch stops the run. Nothing is downloaded. Each result records the instance
size and SHA-256.

Every timed validation must return valid; an invalid result fails the run. The
Zig CLI uses the same module and instance paths and checks the JSON validation
result on every invocation.

## Zig CLI measurements

Release benchmarks reuse the published Zig CLI and use `--zig-cli` to run it on both
workloads. The Zig table reports the median of five fresh-process samples (one
for smoke runs). Each parse sample invokes the CLI once for each workload module
and sums the wall times; each validation sample starts a new CLI, loads the model,
reads and decodes the instance, validates, and exits. A separate `--version` row
measures a minimal CLI invocation. Peak RSS comes from five separate GNU `time`
measurements; for multi-module parsing it is the largest individual process
peak, not a sum. The executable's SHA-256 ties the timings to the measured binary.

These are end-to-end command-line measurements, including process startup and
file I/O. Python and TypeScript timings below measure repeated in-process calls
after setup, so the tables cannot be compared as equivalent operations. Zig
release-to-release deltas use the same CLI measurements when the preceding
release has them with the same recorded build configuration; otherwise they show `n/a`.

## What is measured

Every measurement runs in fresh processes: `python
benchmarks/worker.py SPEC` or `node <bundle> SPEC`. The TypeScript worker
(`ts/bench/worker.ts`) and the library sources in `ts/src` are bundled with the
pinned esbuild from `ts/package-lock.json` (`ts/scripts/build-bench-worker.mjs`).

Three kinds of process are used, and no process serves two purposes:

| Kind | Per (language, workload, phase) | What it does | What is reported |
|---|---|---|---|
| Timing | 3 processes | setup, warmup iterations, timed iterations | median time over all timed iterations |
| Memory | 5 processes | setup, exactly one operation, no warmup | median peak RSS |
| Startup | 10 per language | loads the library and exits | wall time from spawn to exit, peak RSS |

**Time.** In-process, around the measured call only: `time.perf_counter_ns` in
Python, `process.hrtime.bigint` in Node.js. Not timed: runtime startup, module
imports and bundle load, reading files, JSON decoding of the instance, parsing the
schema module for validation, and constructing the validator. The reported
figure is the median over all timed iterations from all timing processes, and
the iteration count is reported with it. Defaults (warmup, iterations per
process):

| Workload | parse | validate |
|---|---|---|
| small | 5, 30 | 10, 50 |
| large | 2, 10 | 1, 5 |

The memory of timing processes is not reported. In a warmed loop the peak grows
with the iteration count because garbage accumulates between collections (Node's
V8 heap grows before it collects). For example, a TypeScript small parse peaked
at about 68 MiB after one iteration and about 110 MiB after 35, while the live
data was about 7 MiB.

**Peak memory.** Separate memory processes each do the full setup and then the
operation exactly once:

- parse: start the runtime, load the library, parse the workload's modules once.
- validate: start the runtime, load the library, parse the schema module, read
  and decode the instance JSON, construct the validator, validate once.

Just before it prints its result, the child reads its own `VmHWM` from
`/proc/self/status`. That is the high-water mark of the process's resident set
size, reset by `exec`, and it covers all threads (including Node's libuv and V8
helper threads). It is reported in MiB (2^20 bytes) as the median over the
memory processes, with the process and operation counts in the results.

This is the whole process peak: the runtime itself, the loaded library, the
setup (schema parse, decoded instance, validator), the operation, and garbage not
yet collected. No startup baseline is subtracted. Garbage collection is not
forced, and no runtime flags (such as `--expose-gc` or heap limits) are set. The
startup rows give the fixed part for comparison. Python's `tracemalloc` and
Node's `heapUsed` measure different things and are not reported.

**Process startup.** 10 processes per language only load the library (Python
`from xyang import ...`; Node loads the bundle) and exit. The parent measures wall
clock from spawn to exit.

The workers start no child processes, so there is nothing to account for below
them. The parent does not use `wait4`/`getrusage(RUSAGE_CHILDREN)` because on
Linux that `ru_maxrss` also includes the parent's own resident size from before
`exec`. Off Linux the workers fall back to `getrusage` `maxrss`, which has that
problem; the results record the source as `rss_source`.

## Code size

`loc.py` counts lines with the standard library only, so the count depends only
on the source tree:

- Python: `src/xyang/**/*.py`, using `tokenize` and `ast`.
- TypeScript: `ts/src/**/*.ts` (no `*.d.ts`), using a small lexer for strings,
  template literals, comments, and regex literals.

A line counts when a code token touches it. Blank lines, comment-only lines, and
Python docstrings (treated like JSDoc) do not. A multi-line string counts every
line. Not counted: tests (`tests/`, `ts/test/`), fixtures and workloads
(`tests/cases/`, `examples/`, `benchmarks/`), generated output (`ts/dist/`,
`artifacts/`, `docs/*.js`, `src/xyang.egg-info/`), dependencies
(`ts/node_modules/`), and tooling (`ts/bench/`, `ts/scripts/`). Code size
is reported in its own table, separate from performance.

## Executable size

Release and manual benchmark runs reuse the Zig release workflow's CLI, built with
the pinned toolchain and `-Doptimize=ReleaseSafe -Dtarget=x86_64-linux-musl
-Dcpu=baseline` (stripped by `build.zig`). The benchmark verifies its commit and
SHA-256 before use. Previous releases measured a `small` build, so Zig deltas
against those releases are unavailable.
The results JSON records the file size in bytes and SHA-256; the generated README
section shows bytes and KiB. This is the same binary attached to the release.

To include a local binary, pass `run --zig-binary PATH` with the other run options.
The harness measures that file without executing it. Omitting the option keeps
older results and smoke runs compatible and does not require Zig.

## Release

[`.github/workflows/benchmark.yml`](../.github/workflows/benchmark.yml):

- **Release published:** the Zig release workflow builds and attaches the binary;
  on its successful completion, the benchmark runs on the same release commit
  using that exact binary (`ubuntu-24.04`, Python
  3.12, Node.js from `.nvmrc`). The results JSON and rendered section are a
  workflow artifact and the job summary. The JSON is attached to the release as
  `benchmark-<tag>.json`. A second job checks out `main`, rewrites the README
  section and `benchmarks/results/latest.json`, pushes `benchmark/<tag>-<run id>`,
  and opens a pull request against `main`. It never pushes to `main`.
- Merging a release benchmark PR triggers the PyPI and npm publishing workflows. Each checks that the README matches complete, clean results for the published release tag, that the measured commit is the tag commit, and that only README and results changed since that tag. Package builds use the merged README. If the release benchmark PR fails to merge or its checks fail, publishing does not proceed. Both publishing workflows may also be dispatched on `main` for a retry and apply the same gate.
- **Manual (`workflow_dispatch`):** first run `Release Zig binaries` on the
  desired ref, then dispatch `Benchmark` on that same ref with its run ID. The
  result is an artifact only; set `open_pr` to also propose the README update.
- **Pull requests touching benchmark files:** the Zig workflow builds the CLI
  once and shares it with its smoke job, which checks the schema and README
  against `results/latest.json`. No timing thresholds.

The workflow uses `GITHUB_TOKEN` to attach the results and the repository secret
`PUBLISH_BENCHMARK_TOKEN` to push the branch and open the pull request. The
fine-grained token needs Contents and Pull requests read/write access to this
repository. Its owner must have repository write access, and the organization
may need to approve the token. If PR creation fails, the workflow fails and
prints a compare link for opening it by hand.

For a release, the workflow downloads the immediately preceding stable version's
benchmark asset when available. The README shows signed percentage changes in
time and memory; positive values mean an increase. `n/a` means a baseline is
missing or the workload changed. Results from different GitHub runners may be
affected by hardware and measurement noise. The prior measurement is embedded
in the results file so README regeneration and the publishing gate remain
reproducible. If the preceding release has no benchmark asset, the README shows
absolute results only.
If measurement fails, the job fails before anything is attached, pushed, or
proposed. The README keeps the previous section, which names the version,
commit, and date it was measured at.

## Limitations

- **Hardware noise.** GitHub-hosted runners are shared VMs; the CPU model can
  change between runs and timings can vary by tens of percent. Compare numbers
  from the same results file. The machine is recorded with each result.
- **Cross-runtime boundaries.** Rows compare the same work, not identical
  machinery: CPython runs bytecode, and Node.js runs a JIT. Node gets warmup
  iterations that let it optimize, so the medians are steady-state numbers. The
  startup row shows the one-time cost. Node's peak RSS includes V8's heap
  reservation and code space, which makes its fixed memory larger.
- **Representativeness.** The large instance is synthetic: a wide, flat list with
  one leafref and simple constraints. Validation cost depends heavily on `must`,
  `when`, and leafref density, which real models vary widely in.
- **Code size** is not a measure of features or quality, and the two
  implementations organize code differently.
