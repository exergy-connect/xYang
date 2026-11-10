# @exergy-connect/xyang

Parse YANG modules, validate RFC 7951 JSON instance data, and export JSON Schema without a NETCONF stack.

Requires Node.js 24 or newer. MIT licensed.

## Install

```bash
npm install @exergy-connect/xyang
```

## TypeScript / JavaScript API

```typescript
import { parseYangString, YangValidator } from "@exergy-connect/xyang";

const module = parseYangString(`
  module example {
    yang-version 1.1;
    namespace "urn:example";
    prefix ex;
    container settings {
      leaf name { type string; mandatory true; }
    }
  }
`);

const validator = new YangValidator(module);
const result = validator.validate({ settings: { name: "example" } });
console.log(result);
```

Use `parseYangFile("path/to/module.yang")` to load a module from disk.

## Python ↔ TypeScript names

| Python | TypeScript |
| --- | --- |
| `parse_yang_file(path, include_path=...)` | `parseYangFile(path, { includePath })` |
| `YangParser(expand_uses=, include_path=)` | `new YangParser({ expandUses, includePath })` |
| `enable_extension` | `enableExtension` |
| `validate() -> (ok, errors, warnings)` | `validate() -> { isValid, errors, warnings }` |

`expand_uses`, `include_path`, `find_statement`, `get_all_leaves`, and `enable_extension` still work and warn once. Use the camelCase names.

## CLI

```bash
npx xyang-ts parse module.yang
npx xyang-ts validate module.yang data.json
npx xyang-ts convert module.yang
```

Add `--include-path DIR` for imported modules. See the [project documentation](https://github.com/exergy-connect/xYang#readme) for additional flags and examples.

The same CLI is also built as a single QuickJS-ng executable (about 1 MB, no Node.js install), which is what you want when an agent or a minimal image shells out to `xyang-ts`. Build and download instructions are in the [project README](https://github.com/exergy-connect/xYang#standalone-binary).

## Browser

```typescript
import { parseYangString, YangValidator } from "@exergy-connect/xyang/browser";
```

The browser entry point parses YANG source strings without filesystem access.

## Features and limitations

- Parse YANG modules, including imports, groupings, augments, and common constraints.
- Validate one consolidated JSON instance document, including types, cardinality, `must`, `when`, leafrefs, and identityrefs.
- Export JSON Schema 2020-12 with `x-yang` metadata.
- Optionally validate qualified JSON subtrees under `anydata`.

Unsupported YANG constructs may be skipped with a warning. See the [feature matrix and known gaps](https://github.com/exergy-connect/xYang/blob/main/FEATURES.md) for details.

[Source and documentation](https://github.com/exergy-connect/xYang) · [Report an issue](https://github.com/exergy-connect/xYang/issues)

## Infer required YANG features

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
