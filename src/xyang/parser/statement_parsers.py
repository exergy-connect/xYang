"""
Statement parsers for YANG statements.
"""

from __future__ import annotations

import re

from . import keywords as kw
from .dispatch_registry import DISPATCH_REGISTRY

from types import SimpleNamespace
from typing import Any, Callable, Optional, TYPE_CHECKING, cast
from .parser_context import TokenStream, ParserContext, YangTokenType
from .statements.anydata import AnydataStatementParser
from .statements.anyxml import AnyxmlStatementParser
from .statements.augment import AugmentStatementParser
from .statements.deviation import DeviationStatementParser
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
from .statements.notification import NotificationStatementParser
from .statements.rpc import RpcStatementParser
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


def _is_identifier(text: str) -> bool:
    """An identifier, using the same letters the tokenizer accepts."""
    if not text or not (text[0].isalpha() or text[0] == "_"):
        return False
    return all(ch.isalnum() or ch in "_-." for ch in text[1:])


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
        self._notification_parser = NotificationStatementParser(self)
        self._rpc_parser = RpcStatementParser(self)
        self._list_parser = ListStatementParser(self)
        self._leaf_parser = LeafStatementParser(self)
        self._leaf_list_parser = LeafListStatementParser(self)
        self._augment_parser = AugmentStatementParser(self)
        self._deviation_parser = DeviationStatementParser(self)
        self._typedef_parser = TypedefStatementParser(self)
        ensure_builtin_extensions_loaded()
        #: ``revision-date`` captured while parsing an ``include { ... }`` body.
        self._include_revision_date: Optional[str] = None
        self._runtime_dispatch = self._build_runtime_dispatch()

    # ------------------------------------------------------------------
    # Small helpers for common patterns
    # ------------------------------------------------------------------

    def add_to_parent_or_module(
        self, context: ParserContext, stmt: "YangStatement"
    ) -> None:
        """Add statement to the current parent (if it can contain statements) or to the module."""
        parent = context.current_parent
        if isinstance(parent, YangStatementList):
            parent.statements.append(stmt)
        else:
            # Fallback to module-level statements (e.g. when no parent or parent is a type).
            context.module.statements.append(stmt)

    def append_attr_list(self, obj: object, attr: str, value: object) -> None:
        """Append value to a list attribute on obj, creating the list if needed."""
        current = getattr(obj, attr, None)
        if current is None:
            current = []
            setattr(obj, attr, current)
        current.append(value)

    def dispatch_key(self, tokens: TokenStream) -> str | YangTokenType:
        """Use keyword lexeme for identifiers, raw type for punctuation/literals."""
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            return cast(str, tokens.peek())
        return tokens.peek_type()

    def substatement_handler(
        self, tokens: TokenStream, dispatch: dict[str, Callable[..., Any]]
    ) -> Optional[Callable[..., Any]]:
        """Resolve a handler from a keyword-keyed map; non-identifier peek types never match."""
        key = self.dispatch_key(tokens)
        return dispatch.get(key) if isinstance(key, str) else None

    def handler_for(self, parent: str, keyword: str) -> Optional[Callable[..., Any]]:
        """Handler for *keyword* under *parent*, or ``None`` when the registry does not allow it."""
        return self._runtime_dispatch[parent].get(keyword)

    def dispatch_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        parent: str,
        *handler_args: Any,
        error_context: str | None = None,
    ) -> None:
        """One substatement of *parent*.

        1. Call the handler when the keyword is in that parent's table.
        2. Otherwise parse ``prefix:name`` as an extension invocation.
        3. Otherwise skip an unsupported construct or raise ``YangSyntaxError``
           naming the parent and the keyword.
        """
        label = parent if error_context is None else error_context
        key = self.dispatch_key(tokens)
        handler = self._runtime_dispatch[parent].get(key) if isinstance(key, str) else None
        if handler is not None:
            handler(tokens, context, *handler_args)
            return
        if self.is_prefixed_extension_start(tokens):
            self.parse_prefixed_extension_statement(tokens, context)
            return
        self.skip_unsupported_or_raise_unknown_stmt(tokens, label)

    def parse_body(
        self,
        tokens: TokenStream,
        context: ParserContext,
        parent: str,
        *handler_args: Any,
        error_context: str | None = None,
    ) -> None:
        """Parse every substatement until the closing ``}``."""
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            self.dispatch_substatement(
                tokens,
                context,
                parent,
                *handler_args,
                error_context=error_context,
            )

    def _parse_discarded_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``description`` and drop it (import, include, if-feature)."""
        self.parse_optional_description(tokens, context.push_parent(SimpleNamespace()))

    def _parse_include_revision_date(self, tokens: TokenStream, _context: ParserContext) -> None:
        self._include_revision_date = self._revision_parser.parse_revision_date_statement(tokens)

    def _default_keyword_handlers(self) -> dict[str, Callable[..., Any]]:
        mod = self._module_parser
        return {
            kw.LEAF: self.parse_leaf,
            kw.LIST: self.parse_list,
            kw.LEAF_LIST: self.parse_leaf_list,
            kw.CONTAINER: self.parse_container,
            kw.NOTIFICATION: self.parse_notification,
            kw.RPC: self.parse_rpc,
            kw.ACTION: self.parse_action,
            kw.ANYDATA: self.parse_anydata,
            kw.ANYXML: self.parse_anyxml,
            kw.TYPEDEF: self.parse_typedef,
            kw.GROUPING: self.parse_grouping,
            kw.IMPORT: mod.parse_import_stmt,
            kw.INCLUDE: mod.parse_include_stmt,
            kw.REVISION: self.parse_revision,
            kw.DESCRIPTION: self.parse_description,
            kw.REFERENCE: self.parse_reference,
            kw.FEATURE: self.parse_feature_stmt,
            kw.IDENTITY: self.parse_identity,
            kw.EXTENSION: self.parse_extension_stmt,
            kw.AUGMENT: self.parse_augment,
            kw.DEVIATION: self.parse_deviation,
            kw.YANG_VERSION: mod.parse_yang_version,
            kw.NAMESPACE: mod.parse_namespace,
            kw.PREFIX: mod.parse_prefix,
            kw.ORGANIZATION: mod.parse_organization,
            kw.CONTACT: mod.parse_contact,
            kw.TYPE: self.parse_type,
            kw.UNITS: self.parse_units,
            kw.DEFAULT: self.parse_leaf_default,
            kw.STATUS: self.parse_status_ignored,
            kw.CONFIG: self.parse_config,
            kw.WHEN: self.parse_when,
            kw.MUST: self.parse_must,
            kw.IF_FEATURE: self.parse_if_feature_stmt,
            kw.PRESENCE: self.parse_presence,
            kw.USES: self.parse_uses,
            kw.REFINE: self.parse_refine,
            kw.CHOICE: self.parse_choice,
            kw.CASE: self.parse_case,
            kw.KEY: self.parse_list_key,
            kw.UNIQUE: self.parse_list_unique,
            kw.MIN_ELEMENTS: self.parse_min_elements,
            kw.MAX_ELEMENTS: self.parse_max_elements,
            kw.ORDERED_BY: self.parse_ordered_by,
            kw.MANDATORY: self.parse_leaf_mandatory,
            kw.INPUT: self.parse_input,
            kw.OUTPUT: self.parse_output,
        }

    def _parent_handler_overrides(self) -> dict[str, dict[str, Callable[..., Any]]]:
        mod = self._module_parser
        typ = self._type_parser
        bits = self._bits_parser
        choice = self._choice_parser
        refine = self._refine_parser
        ident = self._identity_parser
        ext = self._extension_parser
        dev = self._deviation_parser

        def drop_type_stmt(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(tokens: TokenStream, context: ParserContext, _type_stmt: Any) -> Any:
                return fn(tokens, context)

            return wrapped

        return {
            "import": {
                kw.PREFIX: mod.parse_import_prefix_binding,
                kw.DESCRIPTION: self._parse_discarded_description,
                kw.REVISION_DATE: mod._parse_import_revision_date_binding,
            },
            "include": {
                kw.PREFIX: mod.parse_prefix_value_stmt,
                kw.DESCRIPTION: self._parse_discarded_description,
                kw.REVISION_DATE: self._parse_include_revision_date,
            },
            "belongs-to": {kw.PREFIX: mod.parse_prefix_value_stmt},
            "typedef": {kw.DEFAULT: self.parse_typedef_default},
            "choice": {
                kw.MANDATORY: choice.parse_choice_mandatory,
                kw.DEFAULT: choice.parse_choice_default,
            },
            "refine": {
                kw.MANDATORY: refine._parse_refine_mandatory,
                kw.DEFAULT: refine._parse_refine_default,
            },
            "identity": {kw.BASE: ident._parse_identity_base},
            "if-feature": {kw.DESCRIPTION: self._parse_discarded_description},
            "must": {
                kw.ERROR_MESSAGE: self.parse_must_error_message,
                kw.ERROR_APP_TAG: self.parse_must_error_app_tag,
            },
            "extension": {kw.ARGUMENT: ext._parse_extension_argument_stmt},
            "argument": {kw.YIN_ELEMENT: ext._parse_extension_argument_yin_element},
            "deviation": {kw.DEVIATE: dev.parse_deviate_substatement},
            "pattern": {
                kw.ERROR_MESSAGE: typ.parse_pattern_error_message,
                kw.ERROR_APP_TAG: typ.parse_pattern_error_app_tag,
                kw.MODIFIER: typ.parse_pattern_modifier,
            },
            "enum": {
                kw.VALUE: typ.parse_enum_value,
                kw.STATUS: typ.parse_enum_status,
            },
            "bit": {kw.POSITION: bits.parse_bit_position},
            "length": {
                kw.ERROR_MESSAGE: typ.parse_restriction_error_message,
                kw.ERROR_APP_TAG: typ.parse_restriction_error_app_tag,
            },
            "range": {
                kw.ERROR_MESSAGE: typ.parse_restriction_error_message,
                kw.ERROR_APP_TAG: typ.parse_restriction_error_app_tag,
            },
            "type": {
                kw.TYPE: drop_type_stmt(typ.parse_type),
                kw.PATTERN: typ.parse_type_pattern,
                kw.LENGTH: typ.parse_type_length,
                kw.RANGE: typ.parse_type_range,
                kw.FRACTION_DIGITS: typ.parse_type_fraction_digits,
                kw.ENUM: typ.parse_type_enum,
                kw.BIT: bits.parse_type_bit,
                kw.PATH: typ.parse_type_path,
                kw.REQUIRE_INSTANCE: typ.parse_type_require_instance,
                kw.BASE: typ.parse_type_base,
                kw.UNITS: drop_type_stmt(self.parse_units),
                kw.DESCRIPTION: drop_type_stmt(self.parse_description),
                kw.REFERENCE: drop_type_stmt(self.parse_reference),
            },
        }

    def _build_runtime_dispatch(self) -> dict[str, dict[str, Callable[..., Any]]]:
        defaults = self._default_keyword_handlers()
        overrides = self._parent_handler_overrides()
        runtime: dict[str, dict[str, Callable[..., Any]]] = {}
        for parent, spec in DISPATCH_REGISTRY.items():
            over = overrides.get(parent, {})
            extra = set(over) - spec.keywords
            if extra:
                raise RuntimeError(
                    f"handler override for keywords not allowed under {parent}: {sorted(extra)}"
                )
            table: dict[str, Callable[..., Any]] = {}
            missing: list[str] = []
            for keyword in spec.keywords:
                handler = over.get(keyword, defaults.get(keyword))
                if handler is None:
                    missing.append(keyword)
                else:
                    table[keyword] = handler
            if missing:
                raise RuntimeError(f"no handler for {parent}: {sorted(missing)}")
            runtime[parent] = table
        return runtime

    def _skip_unsupported_if_present(self, tokens: TokenStream, context: str) -> bool:
        """If the next token starts deviation/extension/rpc/..., skip it and warn. Returns True if skipped."""
        if not is_unsupported_construct_start(tokens):
            return False
        skip_unsupported_construct(tokens, context=context)
        return True

    def skip_unsupported_or_raise_unknown_stmt(
        self, tokens: TokenStream, context: str
    ) -> bool:
        """Skip unsupported constructs when applicable; otherwise raise ``Unknown statement in {context}: …``."""
        peek = tokens.peek()
        if peek in (kw.INPUT, kw.OUTPUT):
            raise tokens.make_error(
                f"{peek!r} is only valid as a substatement of 'rpc' or 'action' (RFC 7950)"
            )
        if self._skip_unsupported_if_present(tokens, context):
            return True
        raise tokens.make_error(
            f"Invalid or unknown statement in {context}: {tokens.peek()!r}"
        )

    def consume_identifier_ref(self, tokens: TokenStream) -> tuple[Optional[str], str]:
        """``name`` or ``prefix:name``, quoted or unquoted (RFC 7950 identifier-ref-arg-str).

        The argument is read by :meth:`parse_string_argument`, then checked as an
        identifier or a single ``prefix:identifier``.
        """
        raw = self.parse_string_argument(tokens)
        if ":" not in raw:
            if not _is_identifier(raw):
                raise tokens.make_error(f"Expected an identifier, got {raw!r}")
            return None, raw
        prefix, name = raw.split(":", 1)
        if (
            prefix
            and name
            and ":" not in name
            and _is_identifier(prefix)
            and _is_identifier(name)
        ):
            return prefix, name
        raise tokens.make_error(
            f"Expected an identifier or prefix:identifier, got {raw!r}"
        )

    def consume_qname_from_identifier(self, tokens: TokenStream) -> str:
        """Joined ``prefix:name`` form; prefer :meth:`consume_identifier_ref` for new code."""
        prefix, name = self.consume_identifier_ref(tokens)
        return f"{prefix}:{name}" if prefix else name

    def _consume_prefix_argument(self, tokens: TokenStream) -> str:
        """Prefix argument: an identifier, quoted or unquoted."""
        return self.parse_identifier_argument(tokens, "prefix")

    def _consume_optional_extension_argument(
        self, tokens: TokenStream
    ) -> Optional[str]:
        """Consume optional extension argument as normalized string (unquoted)."""
        if not tokens.has_more():
            return None
        tt = tokens.peek_type()
        if tt in (YangTokenType.LBRACE, YangTokenType.SEMICOLON, YangTokenType.RBRACE):
            return None
        return self.parse_string_argument(tokens)

    def _parse_extension_invocation_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        inv_name: str,
    ) -> None:
        """One substatement inside ``prefix:extension { ... }`` (after the opening ``{``)."""
        self.dispatch_substatement(
            tokens,
            context,
            "extension-invocation",
            error_context=f"extension invocation '{inv_name}'",
        )

    def is_prefixed_extension_start(self, tokens: TokenStream) -> bool:
        """Return True only for ``IDENTIFIER ':' IDENTIFIER`` starts."""
        return (
            tokens.peek_type_at(0) == YangTokenType.IDENTIFIER
            and tokens.peek_type_at(1) == YangTokenType.COLON
            and tokens.peek_type_at(2) == YangTokenType.IDENTIFIER
        )

    def parse_prefixed_extension_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``prefix:extension``; current token must be the *prefix* (IDENTIFIER).

        The prefix is consumed, then ``:`` and the extension name. No handler lookup is
        used for the prefix token (only ``identifier`` … ``:`` commits to an extension).
        """
        if not self.is_prefixed_extension_start(tokens):
            raise tokens.make_error(
                "Expected prefixed extension invocation 'prefix:name'"
            )
        prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.COLON)
        ext_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        resolved_module = context.module.resolve_prefixed_module(prefix)
        if resolved_module is None:
            raise tokens.make_error(
                f"Unknown extension prefix {prefix!r} in invocation {prefix}:{ext_name}"
            )
        resolved_extension = resolved_module.get_extension(ext_name)
        if resolved_extension is None:
            raise tokens.make_error(
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
        self.add_to_parent_or_module(context, inv)

    def parse_revision_date_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``revision-date`` substatement (e.g. under ``include``)."""
        self._revision_parser.parse_revision_date_statement(tokens)

    def parse_reference_string_only(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``reference``; store on parent when it has a ``reference`` field."""
        self.parse_reference(tokens, context)

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

    def parse_deviation(self, tokens: TokenStream, context: ParserContext) -> None:
        self._deviation_parser.parse_deviation(tokens, context)
    
    def parse_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse description statement (optional braced extension substatements are skipped)."""
        tokens.consume(kw.DESCRIPTION)
        desc = self.parse_string_argument(tokens)
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

    def parse_reference(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse reference statement into ``current_parent.reference`` when present."""
        tokens.consume(kw.REFERENCE)
        ref = self.parse_string_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        parent = context.current_parent
        if parent is not None and hasattr(parent, "reference"):
            setattr(parent, "reference", ref)

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

    def parse_notification(self, tokens: TokenStream, context: ParserContext):
        return self._notification_parser.parse_notification(tokens, context)

    def parse_rpc(self, tokens: TokenStream, context: ParserContext):
        return self._rpc_parser.parse_rpc(tokens, context)

    def parse_action(self, tokens: TokenStream, context: ParserContext):
        return self._rpc_parser.parse_action(tokens, context)

    def parse_input(self, tokens: TokenStream, context: ParserContext):
        return self._rpc_parser.parse_input(tokens, context)

    def parse_output(self, tokens: TokenStream, context: ParserContext):
        return self._rpc_parser.parse_output(tokens, context)

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
        value = self.parse_string_argument(tokens)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.key = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_list_unique(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``unique "<descendant-path> ..."`` (RFC 7950 §7.8.3)."""
        tokens.consume(kw.UNIQUE)
        arg = self.parse_string_argument(tokens)
        paths = [
            "/".join(seg.split(":", 1)[-1] for seg in path.split("/") if seg)
            for path in arg.split()
        ]
        if not paths:
            raise tokens.make_error("unique requires at least one descendant path")
        if isinstance(context.current_parent, YangListStmt):
            context.current_parent.unique.append(paths)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements (list, leaf-list, or refine)."""
        tokens.consume(kw.MIN_ELEMENTS)
        value = self.parse_integer_or_unbounded(tokens, "min-elements")
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.min_elements = value
        elif parent and hasattr(parent, "min_elements"):
            setattr(parent, "min_elements", value)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements (list, leaf-list, or refine)."""
        tokens.consume(kw.MAX_ELEMENTS)
        value = self.parse_integer_or_unbounded(tokens, "max-elements")
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
        self.parse_keyword_argument(tokens, "ordered-by", ("user", "system"))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_leaf_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in leaf / anydata / anyxml."""
        tokens.consume(kw.MANDATORY)
        value = self.parse_boolean_argument(tokens, "mandatory")
        parent = context.current_parent
        if isinstance(parent, (YangLeafStmt, YangAnydataStmt, YangAnyxmlStmt)):
            parent.mandatory = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_default_value_tokens(self, tokens: TokenStream) -> str:
        """Consume a YANG ``default`` value (after the ``default`` keyword)."""
        return self.parse_string_argument(tokens)

    def parse_leaf_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in leaf statement."""
        tokens.consume(kw.DEFAULT)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.default = self.parse_default_value_tokens(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_typedef_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in typedef statement (RFC 7950 §7.3)."""
        tokens.consume(kw.DEFAULT)
        parent = context.current_parent
        if isinstance(parent, YangTypedefStmt):
            parent.default = self.parse_default_value_tokens(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_presence(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse presence statement for container."""
        tokens.consume(kw.PRESENCE)
        value = self.parse_string_argument(tokens)
        if context.current_parent and isinstance(context.current_parent, YangContainerStmt):
            context.current_parent.presence = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_config(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``config true|false`` (RFC 7950 §7.21.1) into the current parent."""
        from ..ast import YangRefineStmt, YangStatementWithWhen

        tokens.consume(kw.CONFIG)
        value = self.parse_boolean_argument(tokens, "config")
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_config = value
        elif isinstance(parent, YangStatementWithWhen):
            parent.config = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_status_ignored(self, tokens: TokenStream, _context: ParserContext) -> None:
        """Parse ``status``; the value is checked and not stored on the AST."""
        self.parse_status_argument(tokens)

    def parse_units(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``units`` substatement (RFC 7950 §7.21.4) into ``current_parent.units``."""
        tokens.consume(kw.UNITS)
        units = self.parse_string_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        parent = context.current_parent
        if parent is not None and hasattr(parent, "units"):
            setattr(parent, "units", units)

    def parse_string_concatenation(self, tokens: TokenStream) -> str:
        """Quoted string with ``+`` concatenation, or one unquoted argument."""
        if not tokens.has_more() or tokens.peek_type() != YangTokenType.STRING:
            return self.parse_string_argument(tokens)
        parts = [tokens.consume_type(YangTokenType.STRING)]
        while tokens.has_more() and tokens.peek_type() == YangTokenType.PLUS:
            tokens.consume_type(YangTokenType.PLUS)
            if not tokens.has_more() or tokens.peek_type() != YangTokenType.STRING:
                raise tokens.make_error("Expected quoted string after '+'")
            parts.append(tokens.consume_type(YangTokenType.STRING))
        return "".join(parts)

    def parse_string_argument(self, tokens: TokenStream) -> str:
        """One statement argument: quoted string (``+`` concatenation) or an unquoted run.

        The unquoted form runs up to whitespace, ``;``, or ``{`` and may contain
        ``:``, ``/``, ``.``, and digits (RFC 7950 §6.1.3).
        """
        if not tokens.has_more():
            raise tokens.make_error("Expected statement argument, got 'end'")
        if tokens.peek_type() == YangTokenType.STRING:
            return self.parse_string_concatenation(tokens)
        return self._read_unquoted_argument(tokens)

    def _read_unquoted_argument(self, tokens: TokenStream) -> str:
        """Concatenate lexemes that are adjacent in the source."""
        stop = (
            YangTokenType.SEMICOLON,
            YangTokenType.LBRACE,
            YangTokenType.RBRACE,
            YangTokenType.STRING,
        )
        parts: list[str] = []
        prev_line: int | None = None
        prev_end: int | None = None
        while tokens.has_more():
            tok = tokens.peek_token()
            if tok is None or tok.type in stop:
                break
            if prev_end is not None and (tok.line_num != prev_line or tok.char_pos != prev_end):
                break
            parts.append(tok.value)
            prev_line = tok.line_num
            prev_end = tok.char_pos + len(tok.value)
            tokens.consume()
        if not parts:
            got = tokens.peek() if tokens.has_more() else "end"
            raise tokens.make_error(f"Expected statement argument, got {got!r}")
        return "".join(parts)

    def parse_identifier_argument(self, tokens: TokenStream, statement: str) -> str:
        """One argument, then reject text that is not an identifier."""
        raw = self.parse_string_argument(tokens)
        if not _is_identifier(raw):
            raise tokens.make_error(
                f"{statement} argument must be an identifier, got {raw!r}"
            )
        return raw

    def parse_keyword_argument(
        self, tokens: TokenStream, statement: str, allowed: tuple[str, ...]
    ) -> str:
        """One argument, then reject text outside the statement's keyword grammar."""
        raw = self.parse_string_argument(tokens)
        if raw not in allowed:
            choices = " or ".join(repr(item) for item in allowed)
            raise tokens.make_error(
                f"{statement} argument must be {choices}, got {raw!r}"
            )
        return raw

    def parse_integer_argument(self, tokens: TokenStream, statement: str) -> int:
        """One argument that is a signed decimal integer."""
        raw = self.parse_string_argument(tokens)
        if re.fullmatch(r"[+-]?\d+", raw) is None:
            raise tokens.make_error(
                f"{statement} argument must be an integer, got {raw!r}"
            )
        return int(raw)

    def parse_status_argument(self, tokens: TokenStream) -> str:
        """``status current|deprecated|obsolete``, quoted or unquoted."""
        tokens.consume(kw.STATUS)
        value = self.parse_keyword_argument(
            tokens, "status", ("current", "deprecated", "obsolete")
        )
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return value

    def parse_boolean_argument(self, tokens: TokenStream, statement: str) -> bool:
        """Exact lexical ``true`` or ``false``, quoted or unquoted.

        ``"true"`` and ``true`` are the same value. ``TRUE``, ``yes``, ``1``,
        and a missing argument are syntax errors naming the statement.
        """
        if not tokens.has_more() or tokens.peek_type() in (
            YangTokenType.SEMICOLON,
            YangTokenType.LBRACE,
            YangTokenType.RBRACE,
        ):
            raise tokens.make_error(
                f"{statement} argument must be 'true' or 'false', got ''"
            )
        raw = self.parse_string_argument(tokens)
        if raw == kw.TRUE:
            return True
        if raw == kw.FALSE:
            return False
        raise tokens.make_error(
            f"{statement} argument must be 'true' or 'false', got {raw!r}"
        )

    def parse_integer_or_unbounded(self, tokens: TokenStream, statement: str) -> int | None:
        """``min-elements`` / ``max-elements``: an integer or ``unbounded``.

        ``unbounded`` is stored as ``None`` (no bound). Invalid text is a syntax error.
        """
        raw = self.parse_string_argument(tokens)
        if raw == "unbounded":
            return None
        if re.fullmatch(r"[+-]?\d+", raw) is None:
            raise tokens.make_error(
                f"{statement} argument must be an integer or 'unbounded', got {raw!r}"
            )
        return int(raw)

    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        return self._must_parser.parse_must(tokens, context)

    def parse_must_error_message(self, tokens: TokenStream, context: ParserContext) -> None:
        self._must_parser.parse_must_error_message(tokens, context)

    def parse_must_error_app_tag(self, tokens: TokenStream, context: ParserContext) -> None:
        self._must_parser.parse_must_error_app_tag(tokens, context)

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
    
    def copy_statement(self, stmt: 'YangStatement') -> 'YangStatement':
        """Create a copy of a statement, handling AST nodes properly."""
        return copy_yang_statement(stmt)

    def _apply_refine(self, stmt: 'YangStatement', refine: 'YangRefineStmt') -> None:
        """Apply refine modifications to a statement."""
        from ..refine_expand import apply_refine_to_node

        apply_refine_to_node(stmt, refine)
