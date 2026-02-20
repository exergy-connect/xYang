# xYang

xYang implements exactly the YANG and XPath features required to correctly validate `examples/meta-model.yang`. This is a narrower scope than full YANG 1.1 compliance, but a deeper implementation than a generic subset library — particularly around `deref()` chaining, union type coercion, and `current()` scoping in leaf-list constraints.

## Features

xYang implements only the YANG features actually used in `meta-model.yang`:

- **Module Structure**: Module definition with yang-version, namespace, prefix, organization, contact, description, revision
- **Type Definitions**: Typedef statements with type constraints
- **Built-in Types**: string, int32, uint8, boolean, decimal64
- **Derived Types**: enumeration, union
- **Data Structures**: Container, list, leaf, and leaf-list statements
- **Constraints**: 
  - `must` statements (evaluated using XPath)
  - `when` conditions (evaluated using XPath)
  - `mandatory`, `default`, `min-elements`, `max-elements`
  - Type constraints: `pattern`, `length`, `range`, `fraction-digits`
- **Type References**: Leafref with path and require-instance
- **Container Presence**: Presence statements

## Installation

```bash
pip install -e .
```

## Usage

### Parsing a YANG Module

```python
from xYang import parse_yang_file, parse_yang_string

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

# Access module properties
print(f"Module: {module.name}")
print(f"Namespace: {module.namespace}")
print(f"Prefix: {module.prefix}")
```

### Validating Data

```python
from xYang import parse_yang_file, YangValidator

# Parse module
module = parse_yang_file("examples/meta-model.yang")

# Create validator
validator = YangValidator(module)

# Validate data
# Note: The validator accepts raw consolidated JSON. Type coercion happens
# inline during XPath evaluation - comparison operators receive schema-type
# context and perform coercion automatically (e.g., string "true" -> bool True
# for boolean comparisons, string digits -> int for int32 comparisons).
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

### Working with Types

```python
from xYang import TypeSystem
from xYang.types import TypeConstraint

# Create type system
type_system = TypeSystem()

# Register a typedef
constraint = TypeConstraint(
    pattern=r'[a-z_][a-z0-9_]*',
    length="1..64"
)
type_system.register_typedef("entity-name", "string", constraint)

# Validate a value
is_valid, error = type_system.validate("server_name", "entity-name")
print(f"Valid: {is_valid}")
```

## Project Structure

```
xYang/
├── xYang/
│   ├── __init__.py      # Package exports
│   ├── parser.py        # YANG parser
│   ├── module.py        # Module representation
│   ├── ast.py           # Abstract syntax tree nodes
│   ├── types.py         # Type system
│   ├── validator.py     # Validation engine
│   ├── xpath.py         # XPath evaluator
│   ├── errors.py        # Error classes
│   └── xpath/           # XPath implementation
│       ├── __init__.py
│       ├── parser.py    # XPath parser
│       ├── ast.py       # XPath AST nodes
│       └── evaluator.py # XPath evaluator
├── examples/
│   ├── basic_usage.py   # Usage examples
│   └── meta-model.yang  # Example YANG module
├── tests/               # Test suite
├── benchmarks/          # Performance benchmarks
├── setup.py
└── README.md
```

## XPath Support

xYang implements exactly the XPath features required to correctly validate `meta-model.yang`:

- **Path navigation**: `../field`, `../../field`, absolute paths `/data-model/entities`
- **Functions**: `string-length()`, `translate()`, `count()`, `deref()`, `current()`, `not()`, `true()`, `false()`, `bool()`
- **Comparisons**: `=`, `!=`, `<=`, `>=`, `<`, `>`
- **Logical operators**: `or`, `and`
- **Filtering**: `[name = current()]`, `[type != 'array']`, `[id = current()]`, `[1]`
- **String concatenation**: `+` operator

The evaluator implements the specific XPath patterns used in `meta-model.yang` with schema-aware evaluation, particularly for `deref()` chaining and `current()` scoping. `deref()` is inherently schema-coupled: when called on a leafref node, it uses the leafref's schema definition path to resolve the referenced node, not heuristic lookups.

## When Conditions

xYang supports `when` statements for conditional validation. When a `when` condition evaluates to `false`, the associated statement (container, leaf, etc.) is skipped during validation:

```yang
container item_type {
  when "../type = 'array'";
  description "Only present when type is array";
  leaf primitive {
    type string;
  }
}
```

If `../type = 'array'` is false, the `item_type` container is not validated and is treated as optional. The `when` conditions are evaluated using the XPath evaluator.

## Must Statements

xYang supports `must` statements for constraint validation. `must` statements are evaluated using XPath and validation fails if any `must` constraint evaluates to `false`:

```yang
leaf minDate {
  type date;
  must "not(../maxDate) or . <= ../maxDate" {
    error-message "minDate must be less than or equal to maxDate";
  }
}
```

If a `must` constraint fails, validation returns an error with the specified error message.

## Limitations

- **Input contract**: The validator receives a consolidated JSON document. All data must be provided in a single, complete structure — there is no support for validating against source documents or handling partial/incremental data.
- **Type-aware coercion**: The XPath evaluator's comparison operators receive schema-type context and perform coercion inline. This ensures `bool()` in XPath sees actual booleans, not strings (e.g., string `"true"` is coerced to `True` during boolean comparisons). For union types, coercion is attempted in declared order, using the first success. The validator accepts raw consolidated JSON - type awareness is pushed to exactly where it's needed (the evaluator).
- **XPath scope**: Only the XPath features used in `meta-model.yang` are supported. Unsupported expressions will raise `UnsupportedXPathError` at parse time.
- **deref() implementation**: `deref()` is fully implemented for the patterns used in `meta-model.yang`, including:
  - **Schema-coupled resolution**: When `deref()` is called on a leafref node, it MUST resolve using the path from the leafref's schema definition, not just return the value. This reinforces that `deref()` is inherently schema-coupled and cannot be implemented without schema context.
  - Nested chaining: `deref(deref(...))` and deeper nesting
  - Field node identity: `deref(current())` returns the field node when `current()` is already a node (dict)
  - Entity and field resolution: resolves entity names and field references by name (for non-leafref cases)
  - Caching: results are cached for performance
  - Cycle detection: prevents infinite loops in circular references
  It requires schema-aware XPath evaluation and is not a general-purpose implementation.

## Design Rationale

**Zero dependencies**: xYang is implemented in pure Python with no external libraries. Full XPath 1.0 coverage was available via `elementpath` but was excluded to keep the dependency footprint zero. Users who need expressions outside the supported subset will need to extend the evaluator.

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black xYang/
```

## License

MIT License
