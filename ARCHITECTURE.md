# Architecture

xYang parses YANG, checks RFC 7951 JSON, and exports JSON Schema. Python lives in `src/xyang`. TypeScript lives in `ts/src` and mirrors it: `src/xyang/x/y.py` corresponds to `ts/src/x/y.ts`.

Key learnings for agents: [`docs/KEY-LEARNINGS.md`](docs/KEY-LEARNINGS.md).

| To change | Look in |
|---|---|
| Parser keyword dispatch | `parser/dispatch_registry` (Python) / `parser/dispatch-registry` (TS) |
| Built-in type JSON encoding | `types/registry` |
| JSON Schema export | `json/generator` |
| JSON Schema import | `json/parser` |
| Instance validation | `validator/` |
| XPath | `xpath/` |

Each language has one frozen built-in table. An entry records `json_encoding`, `bounds`, `pattern`, and the schema export, schema import, and RFC 7951 value check for that type. The generator, the parser, and the validator call the table. A shared `types.json` is a possible follow-up, not part of this layout.
