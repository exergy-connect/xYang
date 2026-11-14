"""
Parsing helpers for ``uses`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import Optional, TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangGroupingStmt, YangUsesStmt
from ...refine_expand import apply_refines_by_path, copy_yang_statement

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers
    from ...ast import YangStatement
    from ...module import YangModule


class UsesStatementParser:
    """Parser for ``uses`` statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_uses(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangUsesStmt]:
        """Parse uses statement.

        Uses statements are stored temporarily and expanded after all groupings
        have been parsed. A YangUsesStmt node is created as a placeholder.
        """
        tokens.consume(kw.USES)
        grouping_prefix, grouping_name = self._parsers.consume_identifier_ref(tokens)
        uses_stmt = YangUsesStmt(
            name="uses",
            grouping_name=grouping_name,
            grouping_prefix=grouping_prefix,
        )
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(uses_stmt)
            label = uses_stmt.grouping_qname()
            self._parsers.parse_body(
                tokens, new_context, "uses", error_context=f"uses '{label}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, uses_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return uses_stmt

    def _expand_uses(
        self,
        grouping: "YangStatement",
        refines: list,
        module: Optional["YangModule"] = None,
    ) -> list:
        """Legacy helper: expand nested ``uses`` inside a grouping (rarely used)."""
        expanded = []
        for stmt in grouping.statements:
            if isinstance(stmt, YangUsesStmt):
                nested_grouping = None
                if module is not None:
                    if stmt.grouping_prefix:
                        gmod = module.resolve_prefixed_module(stmt.grouping_prefix)
                        nested_grouping = (
                            gmod.get_grouping(stmt.grouping_name) if gmod is not None else None
                        )
                    else:
                        nested_grouping = module.get_grouping(stmt.grouping_name)
                if nested_grouping:
                    body = [copy_yang_statement(s) for s in nested_grouping.statements]
                    nested_expanded = self._expand_uses(
                        YangGroupingStmt(name="", statements=body),
                        stmt.refines,
                        module,
                    )
                    expanded.extend(nested_expanded)
            else:
                stmt_copy = self._parsers.copy_statement(stmt)
                apply_refines_by_path([stmt_copy], refines)
                expanded.append(stmt_copy)

        return expanded

    def _expand_uses_with_statements(
        self,
        statements: list,
        refines: list,
        module: Optional["YangModule"] = None,
    ) -> list:
        """Apply path-based refines to an already-expanded statement list (legacy helper)."""
        apply_refines_by_path(statements, refines)
        return statements
