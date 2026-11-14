"""
Parsing helpers for ``type bits`` substatements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING, Optional

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangBitStmt, YangTypeStmt, YangBitsTypeStmt, YangDerivedTypeStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class BitsStatementParser:
    """Parsers for ``bit`` substatements and ``bits`` finalization."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_type_bit(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``bit`` substatement under ``type bits { ... }`` (RFC 7950 §9.3.4)."""
        if not isinstance(type_stmt, (YangBitsTypeStmt, YangDerivedTypeStmt)):
            raise tokens.make_error("bit requires a bits or derived type")
        if type_stmt.bits is None:
            type_stmt.bits = []
        tokens.consume(kw.BIT)
        bit_name = tokens.consume()
        bit_stmt = YangBitStmt(name=bit_name, position=None)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            bit_ctx = context.push_parent(bit_stmt)
            self._parsers.parse_body(tokens, bit_ctx, "bit", error_context="bit")
            tokens.consume_type(YangTokenType.RBRACE)
        type_stmt.bits.append(bit_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_bit_position(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``position`` under ``bit`` (RFC 7950 §9.7.4)."""
        tokens.consume(kw.POSITION)
        parent = context.current_parent
        if isinstance(parent, YangBitStmt) and parent.position is not None:
            raise tokens.make_error("Duplicate position in bit statement")
        pos = int(tokens.consume_type(YangTokenType.INTEGER))
        if isinstance(parent, YangBitStmt):
            parent.position = pos
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def finalize_bits_type(self, type_stmt: YangBitsTypeStmt, tokens: TokenStream) -> None:
        """Assign implicit bit positions; validate unique names and positions (RFC 7950 §9.3.4).

        Positions are resolved in **declaration order**: an implicit bit uses the largest
        position already assigned at that point (+1), or 0 if none yet.
        """
        seen_names: set[str] = set()
        used_positions: set[int] = set()
        for b in type_stmt.bits:
            if b.name in seen_names:
                raise tokens.make_error(f"Duplicate bit name {b.name!r} in bits type")
            seen_names.add(b.name)
            if b.position is not None:
                p = b.position
                if p < 0:
                    raise tokens.make_error(f"Invalid negative position {p} for bit {b.name!r}")
                if p in used_positions:
                    raise tokens.make_error(
                        f"Duplicate position {p} for bit {b.name!r} in bits type"
                    )
                used_positions.add(p)
            else:
                p = 0 if not used_positions else max(used_positions) + 1
                b.position = p
                used_positions.add(p)
