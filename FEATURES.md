# xYang Feature Set

This document lists the YANG features implemented in xYang, based on actual usage in `meta-model.yang`.

## Features Implemented

### Module Structure
- ✅ `module` - Module definition
- ✅ `yang-version` - YANG version (1.1)
- ✅ `namespace` - Module namespace
- ✅ `prefix` - Module prefix
- ✅ `organization` - Organization (1 occurrence)
- ✅ `contact` - Contact info (1 occurrence)
- ✅ `description` - Description text
- ✅ `revision` - Revision history (1 occurrence)

### Type Definitions
- ✅ `typedef` - Type definitions (heavily used)
- ✅ `type` - Type references

### Built-in Types
- ✅ `string` - String type
- ✅ `int32` - 32-bit integer
- ✅ `uint8` - 8-bit unsigned integer
- ✅ `boolean` - Boolean type
- ✅ `decimal64` - Decimal64 type (2 occurrences)

### Derived Types
- ✅ `enumeration` - Enumeration type (6 occurrences)
- ✅ `union` - Union type (3 occurrences)

### Data Structures
- ✅ `container` - Container statements
- ✅ `list` - List statements (with key)
- ✅ `leaf` - Leaf statements
- ✅ `leaf-list` - Leaf-list statements

### Constraints
- ✅ `must` - Must constraints (57 occurrences) - **Parsed and evaluated**
- ✅ `when` - When conditions (1 occurrence) - **Parsed and evaluated**
- ✅ `mandatory` - Mandatory fields (15 occurrences)
- ✅ `default` - Default values (29 occurrences)
- ✅ `min-elements` - Minimum elements (5 occurrences)
- ✅ `max-elements` - Maximum elements (2 occurrences)
- ✅ `key` - List keys (heavily used)

### Type Constraints
- ✅ `pattern` - Pattern matching (7 occurrences)
- ✅ `length` - Length constraints (8 occurrences)
- ✅ `range` - Range constraints (1 occurrence)
- ✅ `fraction-digits` - Decimal fraction digits (2 occurrences)

### Type References
- ✅ `leafref` - Leaf references (11 occurrences) - **Parsed but not resolved**
- ✅ `path` - Leafref paths
- ✅ `require-instance` - Leafref require-instance

### Container Features
- ✅ `presence` - Container presence (4 occurrences)

## Features NOT Implemented

The following YANG features are not used in `meta-model.yang` and are not implemented:

- ❌ `grouping` / `uses` - Grouping and uses statements
- ❌ `augment` - Augmentation
- ❌ `deviation` - Deviation
- ❌ `import` - Module imports (modules are self-contained)
- ❌ `extension` - Extension statements
- ❌ `identity` / `identityref` - Identity statements
- ❌ `bits` - Bits type
- ❌ `empty` - Empty type
- ❌ `instance-identifier` - Instance identifier

## When Conditions

xYang supports `when` statements for conditional validation. When a `when` condition evaluates to `false`, the associated statement (container, leaf, list, etc.) is skipped during validation. This allows conditional inclusion of schema elements based on data values.

Example from `meta-model.yang`:
```yang
container item_type {
  when "../type = 'array'";
  description "Required for array fields";
  ...
}
```

If `../type = 'array'` evaluates to false, the `item_type` container is not validated and is treated as optional.

## XPath Implementation

xYang implements a minimal XPath evaluator that handles all the XPath expressions used in `meta-model.yang`:

1. **Path Navigation**: Supports relative paths (`../field`, `../../field`) and absolute paths (`/data-model/entities`)

2. **Functions**: 
   - `string-length(.)` - Get length of current node value
   - `translate(., '_', '')` - Translate/remove characters
   - `count(...)` - Count elements in a list
   - `deref(...)` - Resolve leafref (simplified implementation)
   - `current()` - Get current node value
   - `not(...)` - Logical negation
   - `true()`, `false()` - Boolean literals
   - `bool(...)` - Convert value to boolean following YANG rules

3. **Comparisons**: `=`, `!=`, `<=`, `>=`, `<`, `>`

4. **Logical Operators**: `or`, `and`

5. **Filtering**: `[name = current()]`, `[type != 'array']`, `[id = current()]`, `[1]`

6. **String Concatenation**: `+` operator for string concatenation

7. **Arithmetic Operations**: `+`, `-`, `*`, `/` operators

The XPath evaluator uses proper tokenization and AST-based parsing (not string-based), making it more robust and maintainable.

## Error Reporting

xYang provides enhanced error reporting with line numbers and context:

### YANG Parser Errors
- **Line numbers**: Errors include the exact line number (1-indexed) where the error occurred
- **Context lines**: Shows surrounding lines with markers indicating the error line
- **Filename**: When parsing from a file, the filename is included in the error message
- **Example**:
  ```
  test.yang: 15: Expected '{' after module name 'test'
  >>>   15 | module test
        16 |   namespace "urn:test";
        17 |   prefix "test";
  ```

### XPath Parser Errors
- **Character position**: Errors include the exact character position in the expression
- **Expression context**: Shows a snippet of the expression around the error location
- **Pointer**: Visual pointer (^) indicates the exact error location
- **Example**:
  ```
  Expected PAREN_CLOSE, got EOF
  Expression: count(fields[type !=
                         ^
  Position: 23 (end of expression)
  ```

## Code Organization

The XPath implementation is organized in a dedicated subfolder for better modularity:

```
xYang/
├── xpath/
│   ├── __init__.py      # Exports XPathEvaluator
│   ├── evaluator.py     # Main XPath evaluator
│   ├── parser.py         # Tokenizer and recursive descent parser
│   └── ast.py           # AST node definitions
├── errors.py            # Custom exception classes
├── parser.py            # YANG parser
├── validator.py         # Validation engine
└── ...
```

## Limitations

1. **Leafref Resolution**: `deref()` is implemented with simplified resolution. Full resolution would require complete schema traversal and instance data mapping.

2. **XPath Scope**: Only the XPath features actually used in `meta-model.yang` are implemented. More complex XPath features (e.g., axes, complex predicates, namespaces) are not supported.

3. **Error Handling**: The XPath evaluator catches all exceptions during evaluation and returns `False` or `None` for constraint validation. This ensures validation doesn't crash on invalid expressions, but detailed error information may be lost in constraint evaluation contexts.

## Usage Statistics from meta-model.yang

- `must`: 57 occurrences
- `default`: 29 occurrences
- `mandatory`: 15 occurrences
- `leafref`: 11 occurrences
- `pattern`: 7 occurrences
- `enumeration`: 6 occurrences
- `min-elements`: 5 occurrences
- `presence`: 4 occurrences
- `union`: 3 occurrences
- `max-elements`: 2 occurrences
- `decimal64`: 2 occurrences
- `fraction-digits`: 2 occurrences
- `when`: 1 occurrence
- `range`: 1 occurrence
