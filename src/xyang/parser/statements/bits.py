"""
Parsing helpers for ``type bits`` substatements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangBitStmt, YangTypeStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class BitsStatementParser:
    """Parsers for ``bit`` substatements and ``bits`` finalization."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_type_bit(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``bit`` substatement under ``type bits { ... }`` (RFC 7950 §9.3.4)."""
        tokens.consume_type(YangTokenType.BIT)
        bit_name = tokens.consume()
        explicit_pos: Optional[int] = None
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                pt = tokens.peek_type()
                if pt == YangTokenType.POSITION:
                    tokens.consume_type(YangTokenType.POSITION)
                    if explicit_pos is not None:
                        raise tokens._make_error("Duplicate position in bit statement")
                    explicit_pos = int(tokens.consume_type(YangTokenType.INTEGER))
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_description(tokens, context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens,
                    "bit",
                    error_message=(
                        f"Unknown statement in bit: {tokens.peek()!r} "
                        f"(only position and description allowed)"
                    ),
                ):
                    pass
            tokens.consume_type(YangTokenType.RBRACE)
        type_stmt.bits.append(YangBitStmt(name=bit_name, position=explicit_pos))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def finalize_bits_type(self, type_stmt: YangTypeStmt, tokens: TokenStream) -> None:
        """Assign implicit bit positions; validate unique names and positions (RFC 7950 §9.3.4).

        Positions are resolved in **declaration order**: an implicit bit uses the largest
        position already assigned at that point (+1), or 0 if none yet.
        """
        seen_names: set[str] = set()
        used_positions: set[int] = set()
        for b in type_stmt.bits:
            if b.name in seen_names:
                raise tokens._make_error(f"Duplicate bit name {b.name!r} in bits type")
            seen_names.add(b.name)
            if b.position is not None:
                p = b.position
                if p < 0:
                    raise tokens._make_error(f"Invalid negative position {p} for bit {b.name!r}")
                if p in used_positions:
                    raise tokens._make_error(
                        f"Duplicate position {p} for bit {b.name!r} in bits type"
                    )
                used_positions.add(p)
            else:
                p = 0 if not used_positions else max(used_positions) + 1
                b.position = p
                used_positions.add(p)
