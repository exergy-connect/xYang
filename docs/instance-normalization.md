# Instance normalization

Python xYang can normalize instance data as it walks the document for validation.
The rules are declared in the YANG model using the extensions in
[`shared/xyang-transform.yang`](../shared/xyang-transform.yang). They apply to
JSON and YAML input; they do not modify the caller's input object.

Normalization is currently implemented in Python. TypeScript preserves the
extension annotations but does not execute them.

## Expand dotted keys

Import `xyang-transform` and enable the setting **once at module level**:

```yang
import xyang-transform { prefix xt; }

xt:expand-dotted-keys true;
```

This expands dotted object members throughout the modeled instance. For example:

```yaml
nodes:
  dut:
    bgp.as: 65000
```

is validated as if it contained:

```yaml
nodes:
  dut:
    bgp:
      as: 65000
```

The setting covers modeled containers and list entries, including values in
native keyed lists. It does not split the keys of a native list map or inspect
opaque `anydata`. Dots in object member names are treated as separators when
the setting is enabled. Omit the statement or use `false` to leave them alone.

Distinct dotted and nested members can be combined. Conflicting paths, duplicate
spellings of the same modeled node, and empty path segments produce a
`normalize` error rather than overwriting data. Errors point to the original
dotted key where possible. The argument must be `true` or `false`, and the
statement is allowed only at module level.

## Normalize individual values

Attach `xt:normalize` to a modeled node to transform its input value. Each rule
contains exactly one `xt:if` followed by one `xt:apply`. Both arguments are
jq-style expressions; `.` is the current value. If the condition is true,
`xt:apply` produces the replacement. Otherwise the value is unchanged.

```yang
list links {
  key "left right";

  xt:normalize {
    xt:if 'type == "string" and contains("-")';
    xt:apply 'split("-") | {left: .[0], right: .[1]}';
  }

  leaf left  { type string; }
  leaf right { type string; }
}
```

For example, `"dut-x1"` becomes `{"left":"dut","right":"x1"}`. As written,
the expression uses only the first two parts of the split; model authors should
choose an expression appropriate to their accepted input.

Rules on a node run in source order, and a parent is normalized before its
children. On a list or leaf-list, a rule applies to each entry. Missing nodes
are not created. Python supports this expression subset:

- `.`, `.[N]`, `.["key"]`, strings, nonnegative integers,
  `true`, `false`, and `null`.
- Parentheses, object constructors such as `{left: .[0]}`, and the pipe `|`.
- `type`, `length`, `to_entries`, `has(expr)`, `contains(expr)`, `split(expr)`, `==`, `!=`,
  `and`, and `or`.

`contains` and `split` require string input and argument. `length` accepts a
string, array, or object; `to_entries` converts an array or object to an array
of `{key, value}` entries; `has` checks an object key or array index. Only `false` and `null`
are false in a condition; `and` and `or` short circuit. This is a bounded subset,
not a full jq implementation. Unsupported or malformed expressions raise
`ValueError`, even when the annotated node is absent. Evaluation failures produce
a `normalize` validation error at the input JSON Pointer. Errors in constructed
fields use the corresponding normalized field path.

## Validate the Netlab example

The [Netlab model](../examples/netlab/netlab.yang) enables dotted-key expansion
and normalizes link entries. From the xYang repository root, with the Netlab
repository at `../3rd-party/netlab` and PyYAML installed:

```sh
xyang validate examples/netlab/netlab.yang \
  ../3rd-party/netlab/tests/integration/validate/01-bgp-session.yml
```

The result is `{"valid": true, "errors": []}`. For YAML data files, the
Python CLI defaults to JSON output and native encoding, including the keyed-list
encoding used for `nodes`, `groups`, and `validate`. Use `--format text` to
request human-readable output.

Both the expressions and the dotted-key setting survive conversion to xYang's
native JSON Schema form and reload. Python applies them to ordinary documents,
operation parameters, and operation context.
