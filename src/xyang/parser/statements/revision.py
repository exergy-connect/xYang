"""
Parsing for ``revision`` (module history) and ``revision-date`` (RFC 7950).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from .. import keywords as kw
from ..parser_context import TokenStream, ParserContext, YangTokenType
from ..unsupported_skip import is_unsupported_construct_start, skip_unsupported_construct

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class RevisionStatementParser:
    """``revision`` / ``revision-date`` substatements and braced ``revision`` bodies."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse top-level ``revision`` statement."""
        tokens.consume(kw.REVISION)
        tt0 = tokens.peek_type()
        if tt0 == YangTokenType.STRING:
            date = tokens.consume_type(YangTokenType.STRING)
        else:
            chunks: list[str] = []
            while tokens.has_more() and tokens.peek_type() not in (
                YangTokenType.LBRACE,
                YangTokenType.SEMICOLON,
            ):
                tt = tokens.peek_type()
                if tt in (
                    YangTokenType.IDENTIFIER,
                    YangTokenType.DOTTED_NUMBER,
                    YangTokenType.INTEGER,
                ):
                    chunks.append(tokens.consume_type(tt))
                else:
                    break
            date = "".join(chunks)
            if not date:
                raise tokens.make_error(
                    f"Expected revision date, got {tt0.name if tt0 else 'end'}"
                )
        revision: dict[str, str] = {"date": date, "description": "", "reference": ""}
        if tokens.consume_if_type(YangTokenType.LBRACE):
            body = SimpleNamespace(description="", reference="")
            body_ctx = context.push_parent(body)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek() == kw.DESCRIPTION:
                    self._parsers.parse_description(tokens, body_ctx)
                    continue
                if tokens.peek() == kw.REFERENCE:
                    self._parsers.parse_reference(tokens, body_ctx)
                    continue
                if is_unsupported_construct_start(tokens):
                    skip_unsupported_construct(tokens, context="revision")
                    continue
                raise tokens.make_error(
                    f"Unknown statement in revision: {tokens.peek()!r}"
                )
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
        tt0 = tokens.peek_type()
        if tt0 == YangTokenType.STRING:
            return tokens.consume_type(YangTokenType.STRING)
        chunks: list[str] = []
        while tokens.has_more() and tokens.peek_type() != YangTokenType.SEMICOLON:
            tt = tokens.peek_type()
            if tt in (
                YangTokenType.IDENTIFIER,
                YangTokenType.DOTTED_NUMBER,
                YangTokenType.INTEGER,
            ):
                chunks.append(tokens.consume_type(tt))
            else:
                break
        if not chunks:
            raise tokens.make_error(
                f"Expected revision-date value, got {tt0.name if tt0 else 'end'}"
            )
        return "".join(chunks)
