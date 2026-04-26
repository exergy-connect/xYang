"""
Skip unsupported YANG constructs (deviation, rpc, action, notification, input, output)
after emitting a warning.

These statements are not modeled in the AST; braces and arguments are consumed so the
rest of the module can parse.
"""

from __future__ import annotations

from . import keywords as kw

import logging
from typing import TYPE_CHECKING

from .parser_context import YangTokenType

if TYPE_CHECKING:
    from .parser_context import TokenStream

logger = logging.getLogger(__name__)

# RFC 7950 / 1.1 statements xYang does not implement — recognize and skip.
UNSUPPORTED_CONSTRUCT_TYPES = frozenset(
    {
        kw.DEVIATION,
        kw.RPC,
        kw.ACTION,
        kw.NOTIFICATION,
        kw.INPUT,
        kw.OUTPUT,
    }
)


def _consume_balanced_braces(tokens: TokenStream) -> None:
    """Consume a braced block including nested ``{`` / ``}`` (current token is ``{``)."""
    depth = 0
    while tokens.has_more():
        pt = tokens.peek_type()
        if pt == YangTokenType.LBRACE:
            depth += 1
            tokens.consume_type(YangTokenType.LBRACE)
        elif pt == YangTokenType.RBRACE:
            depth -= 1
            tokens.consume_type(YangTokenType.RBRACE)
            if depth == 0:
                return
        else:
            tokens.consume()


def skip_unsupported_construct(tokens: TokenStream, *, context: str) -> None:
    """
    Skip one statement starting at the current token (must be an unsupported keyword).

    Handles ``keyword ... ;`` and ``keyword ... { ... }`` (including nested braces).
    """
    tok = tokens.peek_token()
    if tok is None or tok.value not in UNSUPPORTED_CONSTRUCT_TYPES:
        return
    keyword = tok.value
    line_num, char_pos = tokens.position()
    where = tokens.filename or "<string>"
    logger.warning(
        "Ignoring unsupported YANG statement %r (%s) at %s:%s:%s",
        keyword,
        context,
        where,
        line_num,
        char_pos,
    )
    tokens.consume()
    while tokens.has_more():
        pt = tokens.peek_type()
        if pt == YangTokenType.LBRACE:
            _consume_balanced_braces(tokens)
            break
        if pt == YangTokenType.SEMICOLON:
            tokens.consume_type(YangTokenType.SEMICOLON)
            return
        if pt == YangTokenType.RBRACE:
            return
        tokens.consume()
    tokens.consume_if_type(YangTokenType.SEMICOLON)


def is_unsupported_construct_start(tokens: TokenStream) -> bool:
    if not tokens.has_more():
        return False
    tok = tokens.peek_token()
    return tok is not None and tok.value in UNSUPPORTED_CONSTRUCT_TYPES
