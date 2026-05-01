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
        self._uses_substatement_dispatch = {
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.WHEN: self._parsers.parse_when,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.REFINE: self._parsers.parse_refine,
        }

    def _parse_uses_substatement(
        self, tokens: TokenStream, context: ParserContext, grouping_name: str
    ) -> None:
        """One substatement inside ``uses { ... }``."""
        unsupported = f"uses '{grouping_name}'"
        handler = self._parsers._substatement_handler(tokens, self._uses_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_uses(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangUsesStmt]:
        """Parse uses statement.

        Uses statements are stored temporarily and expanded after all groupings
        have been parsed. A YangUsesStmt node is created as a placeholder.
        """
        tokens.consume(kw.USES)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            grouping_name = self._parsers._consume_qname_from_identifier(tokens)
        else:
            grouping_name = tokens.consume()
        uses_stmt = YangUsesStmt(name="uses", grouping_name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(uses_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_uses_substatement(tokens, new_context, grouping_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, uses_stmt)
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
                nested_grouping = module.get_grouping(stmt.grouping_name) if module else None
                if nested_grouping:
                    body = [copy_yang_statement(s) for s in nested_grouping.statements]
                    nested_expanded = self._expand_uses(
                        YangGroupingStmt(name="", statements=body),
                        stmt.refines,
                        module,
                    )
                    expanded.extend(nested_expanded)
            else:
                stmt_copy = self._parsers._copy_statement(stmt)
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
