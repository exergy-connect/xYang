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

## CLI

```bash
npx xyang-ts parse module.yang
npx xyang-ts validate module.yang data.json
npx xyang-ts convert module.yang
```

Add `--include-path DIR` for imported modules. See the [project documentation](https://github.com/exergy-connect/xYang#readme) for additional flags and examples.

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
