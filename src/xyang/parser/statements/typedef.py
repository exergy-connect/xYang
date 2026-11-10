"""
Parsing helpers for ``typedef`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .. import keywords as kw

from ..metadata_substatements import with_metadata_substatements
from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import (
    YangChoiceStmt,
    YangContainerStmt,
    YangGroupingStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangStatement,
    YangStatementList,
    YangTypedefStmt,
    YangTypeStmt,
)

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class TypedefStatementParser:
    """Parser for ``typedef`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._typedef_body_dispatch = with_metadata_substatements(
            self._parsers,
            {
                kw.TYPE: self._parsers.parse_type,
                kw.UNITS: self._parsers.parse_units,
                kw.DEFAULT: self._parsers.parse_typedef_default,
            },
        )

    def parse_typedef(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume(kw.TYPEDEF)
        typedef_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        typedef_stmt = YangTypedefStmt(name=typedef_name)
        unsupported_ctx = f"typedef '{typedef_name}'"

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(typedef_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self._parsers.substatement_handler(tokens, self._typedef_body_dispatch)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers.skip_unsupported_or_raise_unknown_stmt(
                    tokens, unsupported_ctx
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)

        if typedef_name in context.module.typedefs:
            raise tokens.make_error(
                f"Duplicate typedef {typedef_name!r} in module {context.module.name!r}"
            )
        context.module.typedefs[typedef_name] = typedef_stmt
        parent = context.current_parent
        if isinstance(parent, YangGroupingStmt):
            parent.typedef_names.append(typedef_name)
        if isinstance(parent, YangStatementList) and parent is not context.module:
            parent.statements.append(typedef_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return typedef_stmt


def propagate_typedef_units(module: object) -> None:
    """Copy typedef ``units`` onto leafs that use the typedef and set none of their own."""

    def lookup(type_stmt: YangTypeStmt | None, mod: object, seen: set[tuple[int, str, str]]) -> str:
        if type_stmt is None:
            return ""
        key = (id(mod), type_stmt.prefix or "", type_stmt.name)
        if key in seen:
            return ""
        seen.add(key)
        target = mod
        if type_stmt.prefix and hasattr(mod, "resolve_prefixed_module"):
            target = mod.resolve_prefixed_module(type_stmt.prefix)  # type: ignore[attr-defined]
            if target is None:
                return ""
        typedefs = getattr(target, "typedefs", None)
        td = typedefs.get(type_stmt.name) if isinstance(typedefs, dict) else None
        if td is None:
            return ""
        own = getattr(td, "units", "") or ""
        if own:
            return own
        return lookup(getattr(td, "type", None), target, seen)

    def walk(statements: list[YangStatement], mod: object) -> None:
        for stmt in statements:
            if isinstance(stmt, (YangLeafStmt, YangLeafListStmt)) and not stmt.units and stmt.type is not None:
                found = lookup(stmt.type, mod, set())
                if found:
                    stmt.units = found
            if isinstance(stmt, YangChoiceStmt):
                for case in stmt.cases:
                    walk(case.statements, mod)
            if isinstance(stmt, YangContainerStmt):
                for grouping in stmt.groupings.values():
                    walk(grouping.statements, mod)
            nested = getattr(stmt, "statements", None)
            if isinstance(nested, list) and nested is not statements:
                walk(nested, mod)

    walk(list(getattr(module, "statements", []) or []), module)
    for grouping in getattr(module, "groupings", {}).values():
        walk(getattr(grouping, "statements", []) or [], module)
