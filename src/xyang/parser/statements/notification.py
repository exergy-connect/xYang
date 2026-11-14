"""
Parsing helpers for ``notification`` statements (RFC 7950 §7.16).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangNotificationStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class NotificationStatementParser:
    """Parser for ``notification`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_notification(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangNotificationStmt:
        """Parse notification statement."""
        tokens.consume(kw.NOTIFICATION)
        notification_name = self._parsers.parse_identifier_argument(tokens, "notification")
        notification_stmt = YangNotificationStmt(name=notification_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(notification_stmt)
            self._parsers.parse_body(
                tokens,
                new_context,
                "notification",
                error_context=f"notification '{notification_name}'",
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, notification_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return notification_stmt
