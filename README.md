# xYang

A minimal Python library implementing the YANG features used in `examples/meta-model.yang`.

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

xYang implements a minimal XPath evaluator for the expressions used in `meta-model.yang`:

- **Path navigation**: `../field`, `../../field`, absolute paths `/data-model/entities`
- **Functions**: `string-length()`, `translate()`, `count()`, `deref()`, `current()`, `not()`, `true()`, `false()`, `bool()`
- **Comparisons**: `=`, `!=`, `<=`, `>=`, `<`, `>`
- **Logical operators**: `or`, `and`
- **Filtering**: `[name = current()]`, `[type != 'array']`, `[id = current()]`, `[1]`
- **String concatenation**: `+` operator

The evaluator handles the specific XPath patterns used in `meta-model.yang` without requiring a full XPath engine.

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

- **Leafref resolution**: `deref()` is implemented but uses simplified resolution (full implementation would require complete schema traversal)
- **Complex XPath**: Only the XPath features used in `meta-model.yang` are supported
- **No dependencies**: Pure Python, no external libraries required

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
