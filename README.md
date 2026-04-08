# xYang

**YANG models, validated JSON, and JSON Schema—without dragging in a full management stack.**

xYang is a pure-Python library and CLI for **parsing YANG 1.1-shaped modules**, **validating instance data** against `must` / `when` / types / leafrefs, and **exporting** a standards-friendly **JSON Schema (2020-12)** layer augmented with **`x-yang`** metadata so tools can round-trip where supported. It is built for real modules (the project’s reference design is [`examples/meta-model.yang`](examples/meta-model.yang)), with **deep** handling of the hard parts—**`deref()`** resolution tied to schema paths, **union** typing, and **`current()`** in list and leaf-list contexts—not a shallow syntax sketch.

- **Zero required runtime dependencies** — drop into apps, agents, and pipelines with minimal footprint.
- **Honest scope** — not every RFC 7950 statement is modeled; what *is* implemented is described precisely in [**FEATURES.md**](FEATURES.md) (including `import` / `include`, `if-feature`, `anydata` / `anyxml`, and JSON `if-features` round-trip). Constructs such as `rpc`, `notification`, and `deviation` are **recognized and skipped** with a log warning so mixed modules still parse.
- **MIT licensed** — use it in products and internal tools alike.

**Repository:** [github.com/exergy-connect/xYang](https://github.com/exergy-connect/xYang) · **Issues:** [github.com/exergy-connect/xYang/issues](https://github.com/exergy-connect/xYang/issues)

---

## Features (overview)

The list below is the short version; [**FEATURES.md**](FEATURES.md) is the authoritative, line-by-line feature matrix and documents the **YANG.json** hybrid format.

- **Module structure**: `module` / `submodule`, `yang-version`, `namespace`, `prefix`, metadata, `revision`, `import`, `include`, `feature`
- **Types**: `typedef`, built-in and derived types (`enumeration`, `union`, leafrefs inside unions, etc.); lexer knows the full RFC 7950 built-in name set—**validation depth varies by type** (see FEATURES.md)
- **Data nodes**: `container`, `list` + `key`, `leaf`, `leaf-list`, `choice` / `case`, `anydata` / `anyxml`, `grouping` / `uses` / `refine`, `augment` (merge when uses expansion is enabled)
- **Constraints**: `must`, `when`, `if-feature`, `mandatory`, `default`, `min-elements` / `max-elements`, `pattern`, `length`, `range`, `fraction-digits`
- **References**: `leafref` (+ `require-instance`), `instance-identifier`, `identityref`, `identity` / `base`, XPath `derived-from()` / `derived-from-or-self()`
- **Interop**: **`xyang`** CLI (`parse`, `validate`, `convert`) and **JSON Schema** export with **`x-yang`** annotations for generator/parser round-trip where supported

---

## Installation

**From PyPI** (when published):

```bash
pip install xYang
```

**From a checkout** (editable, for development):

```bash
pip install -e .
```

There are **no required runtime dependencies**. For **`xyang validate`** with **`.yaml` / `.yml`** instance files, install **PyYAML** (`pip install PyYAML` or `pip install -e ".[dev]"`).

**Requirements:** Python **≥ 3.8** (see `pyproject.toml`).

---

## Usage

### Command-line (`xyang`)

```bash
xyang -h                    # help
xyang parse <file.yang>     # print module info
xyang validate <file.yang> [data.json]  # or .yaml/.yml (needs PyYAML); omit file → JSON from stdin
xyang convert <file.yang> [-o path]     # YANG → .yang.json (output path ends with .yang.json)
```

Without installing the package, from the repo root: `PYTHONPATH=src python3 -m xyang -h`

### Parsing a YANG module

```python
from xyang import parse_yang_file, parse_yang_string

# Parse from file
module = parse_yang_file("examples/meta-model.yang")

# Parse from string
yang_content = """
module example {
  yang-version 1.1;
  namespace "urn:example";
  prefix "ex";
  
  container data {
    leaf name {
      type string;
    }
  }
}
"""
module = parse_yang_string(yang_content)

print(f"Module: {module.name}")
print(f"Namespace: {module.namespace}")
print(f"Prefix: {module.prefix}")
```

### Validating data

```python
from xyang import parse_yang_file, YangValidator

module = parse_yang_file("examples/meta-model.yang")
validator = YangValidator(module)

# Consolidated JSON document: one tree matching your module’s data layout.
# XPath comparisons use schema-aware coercion (e.g. string "true" vs boolean leaves).
data = {
    "data-model": {
        "name": "example",
        "entities": [
            {
                "name": "server",
                "fields": [
                    {"name": "id", "type": "string"}
                ]
            }
        ]
    }
}

is_valid, errors, warnings = validator.validate(data)
if not is_valid:
    for error in errors:
        print(f"Error: {error}")
```

### Working with types

```python
from xyang import TypeConstraint, TypeSystem

type_system = TypeSystem()
constraint = TypeConstraint(
    pattern=r'[a-z_][a-z0-9_]*',
    length="1..64"
)
type_system.register_typedef("entity-name", "string", constraint)

is_valid, error = type_system.validate("server_name", "entity-name")
print(f"Valid: {is_valid}")
```

### Converting YANG → JSON Schema (`.yang.json`)

Valid **JSON Schema** for structure and types; YANG-only rules (`must`, `when`, leafref paths, `if-features`, …) ride in **`x-yang`**. Details: [FEATURES.md — YANG.json hybrid format](FEATURES.md#yangjson-hybrid-format).

```python
from xyang.parser import YangParser
from xyang.json import schema_to_yang_json

parser = YangParser(expand_uses=False)
module = parser.parse_file("examples/meta-model.yang")
schema_to_yang_json(module, output_path="meta-model.yang.json")
```

CLI: `xyang convert examples/meta-model.yang -o meta-model.yang.json`

---

## Project layout

```
xYang/
├── src/xyang/
│   ├── __init__.py      # Package exports
│   ├── __main__.py      # CLI (parse, validate, convert)
│   ├── parser/          # YANG parser (incl. unsupported-statement skip)
│   ├── json/            # JSON Schema generator + parser
│   ├── validator/       # Document validation
│   ├── xpath/           # XPath for must/when
│   ├── ast.py           # AST nodes
│   ├── types.py         # Type system
│   ├── module.py        # Module model
│   └── errors.py
├── examples/            # meta-model.yang, samples, generated .yang.json
├── tests/
├── benchmarks/
├── FEATURES.md          # Full feature list & format spec
├── pyproject.toml
└── README.md
```

---

## XPath (schema-aware)

Coverage matches what **meta-model.yang** needs, evaluated with **schema context** (not a generic XPath 1.0 engine):

- **Paths**: `../field`, `../../field`, absolute paths such as `/data-model/entities`
- **Functions**: `string()`, `number()`, `concat()`, `string-length()`, `translate()`, `count()`, **`deref()`**, **`current()`**, `not()`, `true()`, `false()`, `boolean()`, `derived-from()`, `derived-from-or-self()`, …
- **Comparisons & logic**: `=`, `!=`, `<=`, `>=`, `<`, `>`, `and`, `or`
- **Literal sequences** (xYang extension): RHS `('a', 'b')` for membership-style equality
- **Predicates & indexing**: e.g. `[name = current()]`, `[1]`
- **String concat**: `+` between strings in expressions

**`deref()`** on leafref values follows the **leafref’s schema path** to resolve the target node; it supports nesting, caching, and cycle detection for the patterns used in production modules here.

---

## When & must (examples)

**When** — if the condition is false, the node is out of the effective schema; data there is reported as invalid:

```yang
container item_type {
  when "../type = 'array'";
  leaf primitive { type string; }
}
```

**Must** — XPath must evaluate true or validation fails (with `error-message` when provided):

```yang
leaf minDate {
  type date;
  must "not(../maxDate) or . <= ../maxDate" {
    error-message "minDate must be less than or equal to maxDate";
  }
}
```

---

## Scope & limitations

- **Single JSON instance** — validation is against one consolidated document, not NETCONF/XML fragments or incremental edits.
- **XPath subset** — unsupported expressions fail at XPath parse time (`UnsupportedXPathError`). Extend the evaluator to add features.
- **`deref()`** — fully handled for meta-model-style patterns; it remains **schema-coupled** by design, not a standalone generic resolver.
- **RFC surface** — see [**FEATURES.md**](FEATURES.md) for what is partial, skipped, or out of scope; the parser warns when it skips unsupported top-level-like statements.

## Design choices

**No mandatory third-party stack** — core package dependencies are empty in `pyproject.toml`; optional **PyYAML** only for YAML instances on the CLI. That keeps xYang easy to embed and audit.

---

## Development

```bash
pip install -e ".[dev]"
pytest
black src/xyang/
```

---

## License

MIT License
