# Key learnings

## Code structure for agents is a high-leverage point

In Donella Meadows' "Leverage Points: Places to Intervene in a System", changing the structure of a system beats tuning its parameters. For xYang, the code structure that coding agents work in is such a point: it decides how much an agent must search and read before a change, and therefore how fast and how reliably fixes land.

Before PR #117, adding or fixing one built-in type behaviour meant touching up to 28 files across Python and TypeScript, and agents spent most of their time searching and deliberating. PR #117 (issue #113) introduced one built-in type registry per language (`src/xyang/types/registry.py`, `ts/src/types/registry.ts`) with a parity test (`tests/types/test_registry_parity.py`) and `ARCHITECTURE.md`. Prompts that named exact files and lines finished quickly; open-ended ones flailed.

One table per concern per language replaces logic spread over many files. Python/TS parity is enforced by a test rather than by convention. Each entry cites its RFC 7950 section. Unknown input fails loudly (golden seams, no silent fallback). A change should touch one obvious place. Shared cases in `tests/cases/` are the spec for both languages.

The next application is parser keyword dispatch (which substatements each statement accepts), the same pattern as the type registry.

When a fix needs a broad search, treat that as a structural defect and open an issue to restructure, instead of only patching.
