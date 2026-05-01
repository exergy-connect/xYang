"""
Parsing helpers for ``refine`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangRefineStmt, YangUsesStmt
from ...errors import XPathSyntaxError
from ...xpath import XPathParser

if TYPE_CHECKING:
    from ...xpath.ast import PathNode
    from ..statement_parsers import StatementParsers


class RefineStatementParser:
    """Parsers for ``refine`` statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers
        self._refine_substatement_dispatch = {
            kw.MUST: self._parsers.parse_must,
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.MIN_ELEMENTS: self._parsers.parse_min_elements,
            kw.MAX_ELEMENTS: self._parsers.parse_max_elements,
            kw.ORDERED_BY: self._parsers.parse_ordered_by,
            kw.MANDATORY: self._parse_refine_mandatory,
            kw.DEFAULT: self._parse_refine_default,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.TYPE: self._parsers.parse_type,
        }

    def _parse_refine_substatement(
        self, tokens: TokenStream, context: ParserContext, target_path: PathNode
    ) -> None:
        """One substatement inside ``refine { ... }`` (no ``refine:*`` registry keys)."""
        handler = self._parsers._substatement_handler(tokens, self._refine_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
            tokens, f"refine '{target_path.to_string()}'"
        ):
            return

    def _parse_refine_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in refine (RFC 7950 section 7.13.2: leaf / choice target)."""
        tokens.consume(kw.MANDATORY)
        _, tt = tokens.consume_oneof([kw.TRUE, kw.FALSE])
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_mandatory = tt == kw.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_refine_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in refine (RFC 7950 section 7.13.2; applied to expanded leaf / leaf-list)."""
        tokens.consume(kw.DEFAULT)
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_defaults.append(self._parsers._parse_default_value_tokens(tokens))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse refine statement (supports descendant paths ``a/b``)."""
        tokens.consume(kw.REFINE)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            parts = [self._parsers._consume_qname_from_identifier(tokens)]
        else:
            parts = [tokens.consume()]
        while tokens.has_more() and tokens.peek_type() == YangTokenType.SLASH:
            tokens.consume_type(YangTokenType.SLASH)
            if tokens.peek_type() == YangTokenType.IDENTIFIER:
                parts.append(self._parsers._consume_qname_from_identifier(tokens))
            else:
                parts.append(tokens.consume())
        path_arg = "/".join(parts)
        try:
            path_node = XPathParser(path_arg).parse_path()
        except XPathSyntaxError as e:
            raise tokens._make_error(str(e)) from e
        refine_stmt = YangRefineStmt(name="refine", target_path=path_node)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(refine_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_refine_substatement(tokens, new_context, path_node)
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangUsesStmt):
            context.current_parent.refines.append(refine_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
