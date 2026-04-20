"""
Parsing helpers for ``choice`` and ``case`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangCaseStmt, YangChoiceStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ChoiceStatementParser:
    """Parsers for ``choice`` statements and related substatements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._choice_substatement_dispatch = {
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.CASE: self.parse_case,
            YangTokenType.MANDATORY: self.parse_choice_mandatory,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }
        self._case_substatement_dispatch = {
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.USES: self._parsers.parse_uses,
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
            YangTokenType.CHOICE: self.parse_choice,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }

    def _parse_choice_substatement(
        self, tokens: TokenStream, context: ParserContext, choice_name: str
    ) -> None:
        unsupported = f"choice '{choice_name}'"
        handler = self._choice_substatement_dispatch.get(tokens.peek_type())
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def _parse_case_substatement(
        self, tokens: TokenStream, context: ParserContext, case_name: str
    ) -> None:
        unsupported = f"case '{case_name}'"
        handler = self._case_substatement_dispatch.get(tokens.peek_type())
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume_type(YangTokenType.CHOICE)
        choice_name = tokens.consume()  # identifier or keyword
        choice_stmt = YangChoiceStmt(name=choice_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(choice_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_choice_substatement(tokens, new_context, choice_name)
            tokens.consume_type(YangTokenType.RBRACE)
            choice_stmt.validate_case_unique_child_names()
        self._parsers._add_to_parent_or_module(context, choice_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return choice_stmt

    def parse_case(self, tokens: TokenStream, context: ParserContext) -> YangCaseStmt:
        """Parse case statement."""
        tokens.consume_type(YangTokenType.CASE)
        case_name = tokens.consume()  # identifier or keyword
        case_stmt = YangCaseStmt(name=case_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(case_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_case_substatement(tokens, new_context, case_name)
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.cases.append(case_stmt)
        else:
            self._parsers._add_to_parent_or_module(context, case_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return case_stmt

    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory statement in choice."""
        tokens.consume_type(YangTokenType.MANDATORY)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
