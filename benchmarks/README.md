# Benchmarks

`release_bench.py` measures time, peak memory, and source lines for the Python
and TypeScript implementations on the same inputs. Its results go into the
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

Every timed validation must return valid; an invalid result fails the run.

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

Release and manual benchmark runs also build the Zig CLI with the pinned toolchain,
`-Doptimize=small -Dtarget=x86_64-linux-musl -Dcpu=baseline` (stripped by `build.zig`).
The results JSON records the file size in bytes and SHA-256; the generated README
section shows bytes and KiB. This build runs in the release benchmark workflow.

To include a local binary, pass `run --zig-binary PATH` with the other run options.
The harness measures that file without executing it. Omitting the option keeps
older results and smoke runs compatible and does not require Zig.

## Release

[`.github/workflows/benchmark.yml`](../.github/workflows/benchmark.yml):

- **Release published:** full run on the release tag (`ubuntu-24.04`, Python
  3.12, Node.js from `.nvmrc`). The results JSON and rendered section are a
  workflow artifact and the job summary. The JSON is attached to the release as
  `benchmark-<tag>.json`. A second job checks out `main`, rewrites the README
  section and `benchmarks/results/latest.json`, pushes `benchmark/<tag>-<run id>`,
  and opens a pull request against `main`. It never pushes to `main`.
- **Manual (`workflow_dispatch`):** full run on the chosen ref, artifact only;
  set `open_pr` to also propose the README update.
- **Pull requests touching benchmark files:** smoke run, schema check, and a
  check that the README section matches `results/latest.json`. No timing
  thresholds.

Only the workflow `GITHUB_TOKEN` is used: `contents: write` to attach the file
and push the branch, `pull-requests: write` to open the pull request. If the
repository does not allow GitHub Actions to create pull requests (Settings →
Actions → General), the branch is still pushed, and the job prints a warning with
the compare link to open it by hand. Pushes made with `GITHUB_TOKEN` do not start
other workflows, so close and reopen that pull request to run CI.

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
