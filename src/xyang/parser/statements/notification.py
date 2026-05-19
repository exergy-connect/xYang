"""
Parsing helpers for ``notification`` statements (RFC 7950 §7.16).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw

from ..metadata_substatements import with_metadata_substatements
from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangNotificationStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class NotificationStatementParser:
    """Parser for ``notification`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._notification_substatement_dispatch = with_metadata_substatements(
            self._parsers,
            {
                kw.TYPEDEF: self._parsers.parse_typedef,
                kw.WHEN: self._parsers.parse_when,
                kw.MUST: self._parsers.parse_must,
                kw.LEAF: self._parsers.parse_leaf,
                kw.CONTAINER: self._parsers.parse_container,
                kw.LIST: self._parsers.parse_list,
                kw.LEAF_LIST: self._parsers.parse_leaf_list,
                kw.USES: self._parsers.parse_uses,
                kw.CHOICE: self._parsers.parse_choice,
                kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
                kw.ANYDATA: self._parsers.parse_anydata,
                kw.ANYXML: self._parsers.parse_anyxml,
            },
        )

    def _parse_notification_substatement(
        self, tokens: TokenStream, context: ParserContext, notification_name: str
    ) -> None:
        unsupported = f"notification '{notification_name}'"
        handler = self._parsers.substatement_handler(
            tokens, self._notification_substatement_dispatch
        )
        if handler:
            handler(tokens, context)
        elif self._parsers.is_prefixed_extension_start(tokens):
            self._parsers.parse_prefixed_extension_statement(tokens, context)
        elif self._parsers.skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_notification(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangNotificationStmt:
        """Parse notification statement."""
        tokens.consume(kw.NOTIFICATION)
        notification_name = tokens.consume()
        notification_stmt = YangNotificationStmt(name=notification_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(notification_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_notification_substatement(tokens, new_context, notification_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, notification_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return notification_stmt
