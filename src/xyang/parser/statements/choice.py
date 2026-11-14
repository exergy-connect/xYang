"""
Parsing helpers for ``choice`` and ``case`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangCaseStmt, YangChoiceStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers

# RFC 7950 §7.9.2: schema nodes directly under ``choice`` imply a ``case`` named like the node.
_INLINE_CHOICE_SCHEMA_KEYS = frozenset({
    kw.LEAF,
    kw.LEAF_LIST,
    kw.CONTAINER,
    kw.LIST,
    kw.ANYDATA,
    kw.ANYXML,
    kw.CHOICE,
})


class ChoiceStatementParser:
    """Parsers for ``choice`` statements and related substatements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def _parse_choice_substatement(
        self, tokens: TokenStream, context: ParserContext, choice_name: str
    ) -> None:
        key = self._parsers.dispatch_key(tokens)
        if isinstance(key, str) and key in _INLINE_CHOICE_SCHEMA_KEYS:
            self._parse_choice_implicit_case(tokens, context)
            return
        self._parsers.dispatch_substatement(
            tokens, context, "choice", error_context=f"choice '{choice_name}'"
        )

    def _parse_choice_implicit_case(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse a schema node under ``choice`` as an implicit ``case`` (RFC 7950 §7.9.2)."""
        choice = context.current_parent
        if not isinstance(choice, YangChoiceStmt):
            raise tokens.make_error("internal: implicit choice case outside choice body")
        case_stmt = YangCaseStmt(name="")
        case_ctx = context.push_parent(case_stmt)
        key = self._parsers.dispatch_key(tokens)
        handler = (
            self._parsers.handler_for("case", key) if isinstance(key, str) else None
        )
        if handler is None:
            raise tokens.make_error(
                f"internal: unsupported implicit choice schema {tokens.peek()!r}"
            )
        handler(tokens, case_ctx)
        if not case_stmt.statements:
            raise tokens.make_error(
                "Expected a schema node in implicit choice case (RFC 7950 §7.9.2)"
            )
        first = case_stmt.statements[0]
        case_name = first.name or first.get_schema_node()
        if not case_name:
            raise tokens.make_error(
                "Implicit choice case requires a named schema node (RFC 7950 §7.9.2)"
            )
        case_stmt.name = case_name
        choice.cases.append(case_stmt)

    def _parse_case_substatement(
        self, tokens: TokenStream, context: ParserContext, case_name: str
    ) -> None:
        self._parsers.dispatch_substatement(
            tokens, context, "case", error_context=f"case '{case_name}'"
        )

    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume(kw.CHOICE)
        choice_name = self._parsers.parse_identifier_argument(tokens, "choice")
        choice_stmt = YangChoiceStmt(name=choice_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(choice_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_choice_substatement(tokens, new_context, choice_name)
            tokens.consume_type(YangTokenType.RBRACE)
            choice_stmt.validate_case_unique_child_names()
        self._parsers.add_to_parent_or_module(context, choice_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return choice_stmt

    def parse_case(self, tokens: TokenStream, context: ParserContext) -> YangCaseStmt:
        """Parse case statement."""
        tokens.consume(kw.CASE)
        case_name = self._parsers.parse_identifier_argument(tokens, "case")
        case_stmt = YangCaseStmt(name=case_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(case_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_case_substatement(tokens, new_context, case_name)
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.cases.append(case_stmt)
        else:
            self._parsers.add_to_parent_or_module(context, case_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return case_stmt

    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory statement in choice."""
        tokens.consume(kw.MANDATORY)
        value = self._parsers.parse_boolean_argument(tokens, "mandatory")
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.mandatory = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_choice_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``default`` in a choice (RFC 7950 §7.9.3)."""
        tokens.consume(kw.DEFAULT)
        name = self._parsers.parse_identifier_argument(tokens, "default")
        if isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.default = name
        tokens.consume_if_type(YangTokenType.SEMICOLON)
