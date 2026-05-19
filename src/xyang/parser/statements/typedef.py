"""
Parsing helpers for ``typedef`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .. import keywords as kw

from ..metadata_substatements import with_metadata_substatements
from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangGroupingStmt, YangStatementList, YangTypedefStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class TypedefStatementParser:
    """Parser for ``typedef`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._typedef_body_dispatch = with_metadata_substatements(
            self._parsers,
            {
                kw.TYPE: self._parsers.parse_type,
                kw.DEFAULT: self._parsers.parse_typedef_default,
            },
        )

    def parse_typedef(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume(kw.TYPEDEF)
        typedef_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        typedef_stmt = YangTypedefStmt(name=typedef_name)
        unsupported_ctx = f"typedef '{typedef_name}'"

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(typedef_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self._parsers.substatement_handler(tokens, self._typedef_body_dispatch)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers.skip_unsupported_or_raise_unknown_stmt(
                    tokens, unsupported_ctx
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)

        if typedef_name in context.module.typedefs:
            raise tokens.make_error(
                f"Duplicate typedef {typedef_name!r} in module {context.module.name!r}"
            )
        context.module.typedefs[typedef_name] = typedef_stmt
        parent = context.current_parent
        if isinstance(parent, YangGroupingStmt):
            parent.typedef_names.append(typedef_name)
        if isinstance(parent, YangStatementList) and parent is not context.module:
            parent.statements.append(typedef_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return typedef_stmt
