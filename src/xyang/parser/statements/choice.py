"""
Parsing helpers for ``choice`` and ``case`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..metadata_substatements import with_data_node_substatements
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
        self._choice_substatement_dispatch = with_data_node_substatements(
            self._parsers,
            {
                kw.WHEN: self._parsers.parse_when,
                kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
                kw.CASE: self.parse_case,
                kw.MANDATORY: self.parse_choice_mandatory,
            },
        )
        self._case_substatement_dispatch = with_data_node_substatements(
            self._parsers,
            {
            kw.WHEN: self._parsers.parse_when,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.USES: self._parsers.parse_uses,
            kw.LEAF: self._parsers.parse_leaf,
            kw.CONTAINER: self._parsers.parse_container,
            kw.LIST: self._parsers.parse_list,
            kw.LEAF_LIST: self._parsers.parse_leaf_list,
            kw.ANYDATA: self._parsers.parse_anydata,
            kw.ANYXML: self._parsers.parse_anyxml,
            kw.CHOICE: self.parse_choice,
            },
        )

    def _parse_choice_substatement(
        self, tokens: TokenStream, context: ParserContext, choice_name: str
    ) -> None:
        unsupported = f"choice '{choice_name}'"
        handler = self._parsers.substatement_handler(tokens, self._choice_substatement_dispatch)
        if handler:
            handler(tokens, context)
            return
        key = self._parsers.dispatch_key(tokens)
        if isinstance(key, str) and key in _INLINE_CHOICE_SCHEMA_KEYS:
            self._parse_choice_implicit_case(tokens, context)
            return
        if self._parsers.is_prefixed_extension_start(tokens):
            self._parsers.parse_prefixed_extension_statement(tokens, context)
            return
        self._parsers.skip_unsupported_or_raise_unknown_stmt(tokens, unsupported)

    def _parse_choice_implicit_case(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse a schema node under ``choice`` as an implicit ``case`` (RFC 7950 §7.9.2)."""
        choice = context.current_parent
        if not isinstance(choice, YangChoiceStmt):
            raise tokens.make_error("internal: implicit choice case outside choice body")
        case_stmt = YangCaseStmt(name="")
        case_ctx = context.push_parent(case_stmt)
        handler = self._parsers.substatement_handler(
            tokens, self._case_substatement_dispatch
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
        unsupported = f"case '{case_name}'"
        handler = self._parsers.substatement_handler(tokens, self._case_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers.is_prefixed_extension_start(tokens):
            self._parsers.parse_prefixed_extension_statement(tokens, context)
        elif self._parsers.skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume(kw.CHOICE)
        choice_name = tokens.consume()  # identifier or keyword
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
            self._parsers.add_to_parent_or_module(context, case_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return case_stmt

    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory statement in choice."""
        tokens.consume(kw.MANDATORY)
        _, tt = tokens.consume_oneof([kw.TRUE, kw.FALSE])
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.mandatory = tt == kw.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
