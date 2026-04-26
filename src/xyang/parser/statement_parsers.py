"""
Statement parsers for YANG statements.
"""

from __future__ import annotations

from . import keywords as kw

from types import SimpleNamespace
from typing import Optional, TYPE_CHECKING
from .parser_context import TokenStream, ParserContext, YangTokenType
from .statements.anydata import AnydataStatementParser
from .statements.anyxml import AnyxmlStatementParser
from .statements.augment import AugmentStatementParser
from .statements.extension import ExtensionStatementParser
from .statements.feature import FeatureStatementParser
from .statements.identity import IdentityStatementParser
from .statements.bits import BitsStatementParser
from .statements.module import ModuleStatementParser
from .statements.submodule import SubmoduleStatementParser
from .statements.typedef import TypedefStatementParser
from .statements.refine import RefineStatementParser
from .statements.revision import RevisionStatementParser
from .statements.type import TypeStatementParser
from .statements.uses import UsesStatementParser
from .statements.must import MustStatementParser
from .statements.when import WhenStatementParser
from .statements.choice import ChoiceStatementParser
from .statements.grouping import GroupingStatementParser
from .statements.container import ContainerStatementParser
from .statements.list import ListStatementParser
from .statements.leaf import LeafStatementParser
from .statements.leaf_list import LeafListStatementParser
from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangTypedefStmt,
    YangExtensionInvocationStmt,
    YangUsesStmt, YangRefineStmt,
    YangStatementList,
)
from ..ext import (
    ensure_builtin_extensions_loaded,
)

from ..refine_expand import copy_yang_statement
from .unsupported_skip import (
    _consume_balanced_braces,
    is_unsupported_construct_start,
    skip_unsupported_construct,
)

if TYPE_CHECKING:
    from .yang_parser import YangParser
    from ..ast import YangCaseStmt, YangChoiceStmt, YangStatement
    from ..module import YangModule

class StatementParsers:
    """Collection of statement parsing methods."""

    def __init__(self, yang_parser: Optional["YangParser"] = None):
        self._yang_parser: Optional["YangParser"] = yang_parser
        #: Set only while parsing an ``import { ... }`` block (prefix / revision-date capture).
        self._import_parse_state: Optional[SimpleNamespace] = None
        self._extension_parser = ExtensionStatementParser(self)
        self._feature_parser = FeatureStatementParser(self)
        self._identity_parser = IdentityStatementParser(self)
        self._anydata_parser = AnydataStatementParser(self)
        self._anyxml_parser = AnyxmlStatementParser(self)
        self._module_parser = ModuleStatementParser(self)
        self._submodule_parser = SubmoduleStatementParser(self, self._module_parser)
        self._refine_parser = RefineStatementParser(self)
        self._revision_parser = RevisionStatementParser(self)
        self._bits_parser = BitsStatementParser(self)
        self._type_parser = TypeStatementParser(self)
        self._uses_parser = UsesStatementParser(self)
        self._must_parser = MustStatementParser(self)
        self._when_parser = WhenStatementParser(self)
        self._choice_parser = ChoiceStatementParser(self)
        self._grouping_parser = GroupingStatementParser(self)
        self._container_parser = ContainerStatementParser(self)
        self._list_parser = ListStatementParser(self)
        self._leaf_parser = LeafStatementParser(self)
        self._leaf_list_parser = LeafListStatementParser(self)
        self._augment_parser = AugmentStatementParser(self)
        self._typedef_parser = TypedefStatementParser(self)
        ensure_builtin_extensions_loaded()
        # Substatements allowed inside ``prefix:extension { ... }`` (e.g. RFC 8791 ``structure``).
        self._extension_invocation_stmt = {
            kw.IF_FEATURE: self.parse_if_feature_stmt,
            kw.WHEN: self.parse_when,
            kw.MUST: self.parse_must,
            kw.DESCRIPTION: self.parse_description,
            kw.REFERENCE: self.parse_reference_string_only,
            kw.USES: self.parse_uses,
            kw.LEAF: self.parse_leaf,
            kw.LEAF_LIST: self.parse_leaf_list,
            kw.CONTAINER: self.parse_container,
            kw.LIST: self.parse_list,
            kw.CHOICE: self.parse_choice,
            kw.CASE: self.parse_case,
        }

    # ------------------------------------------------------------------
    # Small helpers for common patterns
    # ------------------------------------------------------------------

    def _add_to_parent_or_module(
        self, context: ParserContext, stmt: "YangStatement"
    ) -> None:
        """Add statement to the current parent (if it can contain statements) or to the module."""
        parent = context.current_parent
        if isinstance(parent, YangStatementList):
            parent.statements.append(stmt)
        else:
            # Fallback to module-level statements (e.g. when no parent or parent is a type).
            context.module.statements.append(stmt)

    def _append_attr_list(self, obj: object, attr: str, value: object) -> None:
        """Append value to a list attribute on obj, creating the list if needed."""
        current = getattr(obj, attr, None)
        if current is None:
            current = []
            setattr(obj, attr, current)
        current.append(value)

    def _dispatch_key(self, tokens: TokenStream) -> object:
        """Use keyword lexeme for identifiers, raw type for punctuation/literals."""
        return tokens.peek() if tokens.peek_type() == YangTokenType.IDENTIFIER else tokens.peek_type()

    def _skip_unsupported_if_present(self, tokens: TokenStream, context: str) -> bool:
        """If the next token starts deviation/extension/rpc/..., skip it and warn. Returns True if skipped."""
        if not is_unsupported_construct_start(tokens):
            return False
        skip_unsupported_construct(tokens, context=context)
        return True

    def _skip_unsupported_or_raise_unknown_stmt(
        self, tokens: TokenStream, context: str
    ) -> bool:
        """Skip unsupported constructs when applicable; otherwise raise ``Unknown statement in {context}: …``."""
        if self._skip_unsupported_if_present(tokens, context):
            return True
        raise tokens._make_error(
            f"Invalid or unknown statement in {context}: {tokens.peek()!r}"
        )

    def _consume_qname_from_identifier(self, tokens: TokenStream) -> str:
        """Consume ``name`` or ``prefix:name`` (``prefix:...`` chain). Current token must be IDENTIFIER."""
        parts = [tokens.consume_type(YangTokenType.IDENTIFIER)]
        while tokens.consume_if_type(YangTokenType.COLON):
            parts.append(tokens.consume_type(YangTokenType.IDENTIFIER))
        return ":".join(parts)

    def _consume_prefix_argument(self, tokens: TokenStream) -> None:
        """Prefix argument as string or bare identifier (common in example modules)."""
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            tokens.consume_type(YangTokenType.STRING)
        elif tt == YangTokenType.IDENTIFIER:
            tokens.consume_type(YangTokenType.IDENTIFIER)
        else:
            raise tokens._make_error(
                f"Expected prefix string or identifier, got {tt.name if tt else 'end'}"
            )

    def _consume_optional_extension_argument(
        self, tokens: TokenStream
    ) -> Optional[str]:
        """Consume optional extension argument as normalized string (unquoted)."""
        if not tokens.has_more():
            return None
        tt = tokens.peek_type()
        if tt in (YangTokenType.LBRACE, YangTokenType.SEMICOLON):
            return None
        if tt == YangTokenType.STRING:
            return self._parse_string_concatenation(tokens)
        if tt in (
            YangTokenType.IDENTIFIER,
            YangTokenType.INTEGER,
            YangTokenType.DOTTED_NUMBER,
        ):
            return tokens.consume()
        if tokens.peek() in (kw.TRUE, kw.FALSE):
            return tokens.consume()
        return None

    def _parse_extension_invocation_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        inv_name: str,
    ) -> None:
        """One substatement inside ``prefix:extension { ... }`` (after the opening ``{``)."""
        unsupported = f"extension invocation '{inv_name}'"
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            if not self._is_prefixed_extension_start(tokens):
                if self._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
                    return
            self._parse_prefixed_extension_statement(tokens, context)
            return
        token_value = tokens.peek()
        if token_value == kw.ANYDATA:
            self.parse_anydata(tokens, context)
            return
        if token_value == kw.ANYXML:
            self.parse_anyxml(tokens, context)
            return
        handler = self._extension_invocation_stmt.get(token_value)
        if handler:
            handler(tokens, context)
            return
        if self._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def _is_prefixed_extension_start(self, tokens: TokenStream) -> bool:
        """Return True only for ``IDENTIFIER ':' IDENTIFIER`` starts."""
        return (
            tokens.peek_type_at(0) == YangTokenType.IDENTIFIER
            and tokens.peek_type_at(1) == YangTokenType.COLON
            and tokens.peek_type_at(2) == YangTokenType.IDENTIFIER
        )

    def _parse_prefixed_extension_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``prefix:extension``; current token must be the *prefix* (IDENTIFIER).

        The prefix is consumed, then ``:`` and the extension name. No handler lookup is
        used for the prefix token (only ``identifier`` … ``:`` commits to an extension).
        """
        if not self._is_prefixed_extension_start(tokens):
            raise tokens._make_error(
                "Expected prefixed extension invocation 'prefix:name'"
            )
        prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.COLON)
        ext_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        resolved_module = context.module.resolve_prefixed_module(prefix)
        if resolved_module is None:
            raise tokens._make_error(
                f"Unknown extension prefix {prefix!r} in invocation {prefix}:{ext_name}"
            )
        resolved_extension = resolved_module.get_extension(ext_name)
        if resolved_extension is None:
            raise tokens._make_error(
                f"Unknown extension {ext_name!r} in module {resolved_module.name!r} "
                f"for invocation {prefix}:{ext_name}"
            )
        arg = self._consume_optional_extension_argument(tokens)
        inv = YangExtensionInvocationStmt(
            name=f"{prefix}:{ext_name}",
            prefix=prefix,
            resolved_module=resolved_module,
            resolved_extension=resolved_extension,
            argument=arg,
        )
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(inv)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_extension_invocation_substatement(
                    tokens, new_context, inv.name
                )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        self._add_to_parent_or_module(context, inv)

    def parse_revision_date_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``revision-date`` substatement (e.g. under ``include``)."""
        self._revision_parser.parse_revision_date_statement(tokens)

    def parse_reference_string_only(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume(kw.REFERENCE)
        tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_extension_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._extension_parser.parse_extension_stmt(tokens, context)

    def parse_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._feature_parser.parse_feature_stmt(tokens, context)

    def parse_if_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._feature_parser.parse_if_feature_stmt(tokens, context)

    def parse_uses(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangUsesStmt]:
        return self._uses_parser.parse_uses(tokens, context)

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        self._augment_parser.parse_augment(tokens, context)
    
    def parse_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse description statement (optional braced extension substatements are skipped)."""
        tokens.consume(kw.DESCRIPTION)
        desc = tokens.consume_type(YangTokenType.STRING)
        if tokens.has_more() and tokens.peek_type() == YangTokenType.LBRACE:
            _consume_balanced_braces(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        parent = context.current_parent
        if parent is not None and hasattr(parent, "description"):
            setattr(parent, "description", desc)

    def parse_optional_description(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """If the next token is ``description``, parse it into ``current_parent.description``."""
        if not tokens.has_more() or tokens.peek() != kw.DESCRIPTION:
            return
        self.parse_description(tokens, context)

    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse revision statement."""
        self._revision_parser.parse_revision(tokens, context)

    def parse_typedef(self, tokens: TokenStream, context: ParserContext) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        return self._typedef_parser.parse_typedef(tokens, context)

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        self._identity_parser.parse_identity(tokens, context)

    def parse_type_base(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_base(tokens, context, type_stmt)

    def parse_container(self, tokens: TokenStream, context: ParserContext) -> YangContainerStmt:
        return self._container_parser.parse_container(tokens, context)

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        return self._list_parser.parse_list(tokens, context)

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        return self._leaf_parser.parse_leaf(tokens, context)

    def parse_leaf_list(self, tokens: TokenStream, context: ParserContext) -> YangLeafListStmt:
        return self._leaf_list_parser.parse_leaf_list(tokens, context)

    def parse_anydata(self, tokens: TokenStream, context: ParserContext) -> YangAnydataStmt:
        return self._anydata_parser.parse_anydata(tokens, context)

    def parse_anyxml(self, tokens: TokenStream, context: ParserContext) -> YangAnyxmlStmt:
        return self._anyxml_parser.parse_anyxml(tokens, context)

    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        return self._type_parser.parse_type(tokens, context)

    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_pattern(tokens, context, type_stmt)

    def parse_type_length(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_length(tokens, context, type_stmt)

    def parse_type_range(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_range(tokens, context, type_stmt)

    def parse_type_fraction_digits(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_fraction_digits(tokens, context, type_stmt)

    def parse_type_enum(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_enum(tokens, context, type_stmt)

    def parse_type_bit(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._bits_parser.parse_type_bit(tokens, context, type_stmt)

    def parse_type_path(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_path(tokens, context, type_stmt)

    def parse_type_require_instance(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_require_instance(tokens, context, type_stmt)

    def parse_list_key(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse key in list statement."""
        tokens.consume(kw.KEY)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            value, _ = tokens.consume_oneof([YangTokenType.STRING, YangTokenType.IDENTIFIER])
            context.current_parent.key = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements (list, leaf-list, or refine)."""
        tokens.consume(kw.MIN_ELEMENTS)
        value = int(tokens.consume_type(YangTokenType.INTEGER))
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.min_elements = value
        elif parent and hasattr(parent, "min_elements"):
            setattr(parent, "min_elements", value)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements (list, leaf-list, or refine)."""
        tokens.consume(kw.MAX_ELEMENTS)
        value = int(tokens.consume_type(YangTokenType.INTEGER))
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.max_elements = value
        elif parent and hasattr(parent, "max_elements"):
            setattr(parent, "max_elements", value)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_ordered_by(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ordered-by under list or leaf-list (RFC 7950 §7.7.1).

        xYang does not track user vs system ordering in validation; the statement is accepted
        and discarded after syntax check.
        """
        tokens.consume(kw.ORDERED_BY)
        arg = tokens.consume()
        if arg not in ("user", "system"):
            raise tokens._make_error(f"ordered-by must be 'user' or 'system', got {arg!r}")
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_leaf_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in leaf / anydata / anyxml."""
        tokens.consume(kw.MANDATORY)
        parent = context.current_parent
        if isinstance(parent, (YangLeafStmt, YangAnydataStmt, YangAnyxmlStmt)):
            _, tt = tokens.consume_oneof([kw.TRUE, kw.FALSE])
            parent.mandatory = tt == kw.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def _parse_default_value_tokens(self, tokens: TokenStream) -> str | int:
        """Consume a YANG ``default`` value (after the ``default`` keyword)."""
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            return tokens.consume_type(YangTokenType.STRING)
        if tt == YangTokenType.INTEGER:
            return tokens.consume_type(YangTokenType.INTEGER)
        if tt == YangTokenType.IDENTIFIER:
            return tokens.consume_type(YangTokenType.IDENTIFIER)
        raise tokens._make_error(
            f"Expected default value (string, integer, identifier, or true/false), "
            f"got {tt.name if tt else 'end'}"
        )

    def parse_leaf_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in leaf statement."""
        tokens.consume(kw.DEFAULT)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.default = self._parse_default_value_tokens(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_presence(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse presence statement for container."""
        tokens.consume(kw.PRESENCE)
        if context.current_parent and isinstance(context.current_parent, YangContainerStmt):
            context.current_parent.presence = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_string_concatenation(self, tokens: TokenStream) -> str:
        """Consume one or more STRING tokens with optional PLUS between; return concatenated string."""
        parts = [tokens.consume_type(YangTokenType.STRING)]
        while tokens.has_more() and tokens.peek_type() == YangTokenType.PLUS:
            tokens.consume_type(YangTokenType.PLUS)
            parts.append(tokens.consume_type(YangTokenType.STRING))
        return ''.join(parts)

    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        return self._must_parser.parse_must(tokens, context)

    def parse_must_error_message(self, tokens: TokenStream, context: ParserContext) -> None:
        self._must_parser.parse_must_error_message(tokens, context)

    def parse_when(self, tokens: TokenStream, context: ParserContext) -> None:
        self._when_parser.parse_when(tokens, context)
    
    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        self._grouping_parser.parse_grouping(tokens, context)
    
    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        self._refine_parser.parse_refine(tokens, context)
    
    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        return self._choice_parser.parse_choice(tokens, context)
    
    def parse_case(self, tokens: TokenStream, context: ParserContext) -> YangCaseStmt:
        return self._choice_parser.parse_case(tokens, context)

    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        self._choice_parser.parse_choice_mandatory(tokens, context)
    
    def _copy_statement(self, stmt: 'YangStatement') -> 'YangStatement':
        """Create a copy of a statement, handling AST nodes properly."""
        return copy_yang_statement(stmt)

    def _apply_refine(self, stmt: 'YangStatement', refine: 'YangRefineStmt') -> None:
        """Apply refine modifications to a statement."""
        from ..refine_expand import apply_refine_to_node

        apply_refine_to_node(stmt, refine)
