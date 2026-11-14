"""
Parsing for ``revision`` (module history) and ``revision-date`` (RFC 7950).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from .. import keywords as kw
from ..parser_context import TokenStream, ParserContext, YangTokenType

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class RevisionStatementParser:
    """``revision`` / ``revision-date`` substatements and braced ``revision`` bodies."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse top-level ``revision`` statement."""
        tokens.consume(kw.REVISION)
        date = self._parsers.parse_string_argument(tokens)
        revision: dict[str, str] = {"date": date, "description": "", "reference": ""}
        if tokens.consume_if_type(YangTokenType.LBRACE):
            body = SimpleNamespace(description="", reference="")
            body_ctx = context.push_parent(body)
            self._parsers.parse_body(tokens, body_ctx, "revision", error_context="revision")
            tokens.consume_type(YangTokenType.RBRACE)
            revision["description"] = body.description
            revision["reference"] = body.reference
        context.module.revisions.append(revision)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_revision_date_statement(self, tokens: TokenStream) -> str:
        """Parse a full ``revision-date`` substatement (keyword, value, optional ``;``)."""
        tokens.consume(kw.REVISION_DATE)
        date = self._parse_revision_date_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return date

    def _parse_revision_date_argument(self, tokens: TokenStream) -> str:
        """Parse revision-date value only (no keyword or trailing ``;``)."""
        return self._parsers.parse_string_argument(tokens)
