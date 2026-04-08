# xyang validate

Use the **xyang** CLI (and `xyang` Python package) in this repo to **parse** YANG modules and **validate** **JSON** or **YAML** instance data against them. YAML paths need **PyYAML** (`pip install PyYAML` or `pip install -e ".[dev]"`).

Full behavior and scope: [**FEATURES.md**](FEATURES.md); primary example module: [`examples/meta-model.yang`](examples/meta-model.yang).

## Environment

**Recommended:** from the repository root, use a venv and an editable install so `xyang` is on `PATH`:

```bash
cd /path/to/xYang
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -e .
```

**Without installing:** add the package source tree to `PYTHONPATH` and invoke the module:

```bash
cd /path/to/xYang
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
```

Then use either the **`xyang`** script (if installed) or **`python3 -m xyang`** everywhere below.

## Parse a `.yang` file (syntax / AST)

```bash
xyang parse path/to/module.yang
# or: python3 -m xyang parse path/to/module.yang
```

On success: module name, `yang-version`, namespace, prefix, optional organization, typedef count, top-level statement count (stdout). On failure: error message (**stderr**), exit **1**.

## Validate instance data (JSON or YAML) against a module

The instance document must match the **data tree** the module defines (container / list / leaf names as your encoder produces). Validation uses **`YangValidator`** (`xyang`).

```bash
xyang validate path/to/module.yang path/to/instance.json
xyang validate path/to/module.yang path/to/instance.yaml   # or .yml; needs PyYAML
```

**JSON on stdin** (omit the data file):

```bash
xyang validate path/to/module.yang < instance.json
```

**Exit codes:** **0** if valid (**stdout**: `Valid.`; **warnings** also on **stdout** as `Warning: …`). **1** if invalid or on errors (**stderr**: `Validation failed:` plus each error line, or `Error: …` for parse/load failures).

## Convert YANG → JSON Schema (`*.yang.json`)

```bash
xyang convert path/to/module.yang -o path/to/module.yang.json
```

If `-o` is omitted, default output is `<stem>.yang.json` next to the `.yang` file. The file is JSON Schema (2020-12) plus **`x-yang`** metadata for tooling that understands it.

## Optional: `pyang` (IETF-oriented checker)

If **`pyang`** is installed, a strict parse can surface issues outside xyang’s implemented subset:

```bash
pyang --strict path/to/module.yang
```

xyang and `pyang` may disagree on edge cases; use `pyang` as supplementary unless the goal is strict IETF tooling parity.

## When the user points at a netlab topology YAML

`xyang validate` only checks data against the **YANG module**; it does **not** turn a stock netlab lab file into that shape. A typical `topology.yml` is a **different encoding** than something like `netlab-topology-lab` expects (e.g. `groups` / `nodes` / `validate` as **maps** vs the module’s **lists** keyed by `name`; `links` as loose dicts vs `links[]` with `name` + `endpoint[]`; `addressing` as a map of pool names vs `addressing.pool[]` entries with a `name` leaf; dotted YAML keys like `defaults.sources.extra` vs nested objects `defaults` → `sources` → `extra`). Either **normalize** in tooling and then validate the result, or author instance JSON/YAML that already matches the module. Use the module’s description and `FEATURES.md`; run **`xyang validate`** on the normalized instance—do not claim success without running it.

## Agent checklist

1. **Environment:** `pip install -e .` from repo root, **or** `PYTHONPATH` includes **`<repo>/src`**.
2. Run **`xyang parse`** (or `python3 -m xyang parse`) on any `.yang` the user changed.
3. If they have instance data, run **`xyang validate <module.yang> <instance.json|yaml|yml>`** or pipe JSON on stdin.
4. On failure, report **stderr** (and relevant **stdout**) verbatim; suggest fixes in YANG or instance shape.
