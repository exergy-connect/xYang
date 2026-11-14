"""
Parsing helpers for ``typedef`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .. import keywords as kw

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

    def parse_typedef(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume(kw.TYPEDEF)
        typedef_name = self._parsers.parse_identifier_argument(tokens, "typedef")
        typedef_stmt = YangTypedefStmt(name=typedef_name, scope=context.typedef_context or None)
        unsupported_ctx = f"typedef '{typedef_name}'"

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(typedef_stmt)
            self._parsers.parse_body(
                tokens, new_context, "typedef", error_context=unsupported_ctx
            )
            tokens.consume_type(YangTokenType.RBRACE)

        parent = context.current_parent
        from ...typedef_scope import register_typedef

        register_typedef(context.module.typedefs, typedef_stmt)
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
        from ...module import resolve_typedef

        td, target = resolve_typedef(type_stmt, mod)
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
