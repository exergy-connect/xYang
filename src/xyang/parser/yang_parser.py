"""
YANG parser implementation (refactored).

Parses YANG module files and builds an in-memory representation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from ..augment_expand import apply_augmentations
from ..errors import YangSyntaxError
from ..ext import apply_extension_invocations
from ..module import YangModule
from ..uses_expand import expand_all_uses_in_module
from .tokenizer import YangTokenizer
from .parser_context import ParserContext, TokenStream
from .statement_registry import StatementRegistry
from .statement_parsers import StatementParsers


class YangParser:
    """Parser for YANG modules."""

    def __init__(
        self,
        *,
        expand_uses: bool = True,
        include_path: Tuple[Path, ...] = (),
    ):
        """
        Args:
            expand_uses: If True (default), after parsing: expand ``uses`` and
                ``refine``, merge ``augment`` into target schema, and remove
                top-level ``augment`` statements. If False, those constructs stay
                in the AST as written. Use False for **reversible** pipelines (e.g.
                YANG → JSON Schema with ``x-yang`` → YANG): the generator can expand
                ``uses`` only at emit time while preserving source structure in the
                stored AST.
            include_path: Extra directories to search for ``include`` submodules
                (after the directory of the file being parsed).
        """
        self.tokenizer = YangTokenizer()
        self.registry = StatementRegistry()
        self.parsers = StatementParsers(self.registry, yang_parser=self)
        self.expand_uses = expand_uses
        self.include_path = include_path
        self._include_stack: list[Path] = []
        self._module_cache: dict[Path, YangModule] = {}
        self._import_pending: set[Path] = set()
        self._register_handlers()

    def _expand_and_augment(self, module: YangModule) -> None:
        """Runs only when ``expand_uses`` is True (same gate as reversibility)."""
        if self.expand_uses:
            expand_all_uses_in_module(module)
            apply_augmentations(module)
            apply_extension_invocations(module)

    def _register_handlers(self):
        """Register all statement handlers."""
        for _kw, _handler in (
            ('if-feature', self.parsers.parse_if_feature_stmt),
            ('when', self.parsers.parse_when),
            ('must', self.parsers.parse_must),
            ('description', self.parsers.parse_description),
            ('reference', self.parsers.parse_reference_string_only),
            # Generic extension bodies (e.g. RFC 8791 ``structure``) allow data definition statements.
            ('uses', self.parsers.parse_uses),
            ('leaf', self.parsers.parse_leaf),
            ('leaf-list', self.parsers.parse_leaf_list),
            ('container', self.parsers.parse_container),
            ('list', self.parsers.parse_list),
            ('choice', self.parsers.parse_choice),
            ('case', self.parsers.parse_case),
            ('anydata', self.parsers.parse_anydata),
            ('anyxml', self.parsers.parse_anyxml),
        ):
            self.registry.register(f'extension_invocation:{_kw}', _handler)

        self.registry.register('must:error-message', self.parsers.parse_must_error_message)
        self.registry.register('must:description', self.parsers.parse_description)
        self.registry.register('when:description', self.parsers.parse_description)

        # ``if-feature`` (RFC 7950 §7.20.2): supported under data/schema constructs this
        # parser implements — container, leaf, leaf-list, list, choice, case, uses, refine,
        # augment, identity — plus ``feature`` (§7.20.1.1).  Not on ``enum`` / ``bit`` per
        # RFC 7950 §9.  ``deviation``, ``rpc``, ``action``, ``notification``,
        # ``input``, ``output`` are skipped with a warning (see ``unsupported_skip``).

        # Augment body
        self.registry.register('augment:if-feature', self.parsers.parse_if_feature_stmt)
        self.registry.register('augment:uses', self.parsers.parse_uses)
        self.registry.register('augment:leaf', self.parsers.parse_leaf)
        self.registry.register('augment:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('augment:container', self.parsers.parse_container)
        self.registry.register('augment:list', self.parsers.parse_list)
        self.registry.register('augment:choice', self.parsers.parse_choice)
        self.registry.register('augment:anydata', self.parsers.parse_anydata)
        self.registry.register('augment:anyxml', self.parsers.parse_anyxml)
        self.registry.register('augment:description', self.parsers.parse_description)
        self.registry.register('augment:when', self.parsers.parse_when)
        self.registry.register('augment:must', self.parsers.parse_must)

        # Container body statements
        self.registry.register('container:description', self.parsers.parse_description)
        self.registry.register('container:presence', self.parsers.parse_presence)
        self.registry.register('container:when', self.parsers.parse_when)
        self.registry.register('container:must', self.parsers.parse_must)
        self.registry.register('container:leaf', self.parsers.parse_leaf)
        self.registry.register('container:container', self.parsers.parse_container)
        self.registry.register('container:list', self.parsers.parse_list)
        self.registry.register('container:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('container:uses', self.parsers.parse_uses)
        self.registry.register('container:choice', self.parsers.parse_choice)
        self.registry.register('container:anydata', self.parsers.parse_anydata)
        self.registry.register('container:anyxml', self.parsers.parse_anyxml)
        self.registry.register('container:if-feature', self.parsers.parse_if_feature_stmt)

        # List body statements
        self.registry.register('list:key', self.parsers.parse_list_key)
        self.registry.register('list:min-elements', self.parsers.parse_min_elements)
        self.registry.register('list:max-elements', self.parsers.parse_max_elements)
        self.registry.register('list:ordered-by', self.parsers.parse_ordered_by)
        self.registry.register('list:description', self.parsers.parse_description)
        self.registry.register('list:when', self.parsers.parse_when)
        self.registry.register('list:leaf', self.parsers.parse_leaf)
        self.registry.register('list:container', self.parsers.parse_container)
        self.registry.register('list:list', self.parsers.parse_list)
        self.registry.register('list:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('list:must', self.parsers.parse_must)
        self.registry.register('list:uses', self.parsers.parse_uses)
        self.registry.register('list:choice', self.parsers.parse_choice)
        self.registry.register('list:anydata', self.parsers.parse_anydata)
        self.registry.register('list:anyxml', self.parsers.parse_anyxml)
        self.registry.register('list:if-feature', self.parsers.parse_if_feature_stmt)

        # Leaf body statements
        self.registry.register('leaf:type', self.parsers.parse_type)
        self.registry.register('leaf:mandatory', self.parsers.parse_leaf_mandatory)
        self.registry.register('leaf:default', self.parsers.parse_leaf_default)
        self.registry.register('leaf:description', self.parsers.parse_description)
        self.registry.register('leaf:must', self.parsers.parse_must)
        self.registry.register('leaf:when', self.parsers.parse_when)
        self.registry.register('leaf:if-feature', self.parsers.parse_if_feature_stmt)

        # Leaf-list body statements
        self.registry.register('leaf-list:type', self.parsers.parse_type)
        self.registry.register('leaf-list:min-elements', self.parsers.parse_min_elements)
        self.registry.register('leaf-list:max-elements', self.parsers.parse_max_elements)
        self.registry.register('leaf-list:ordered-by', self.parsers.parse_ordered_by)
        self.registry.register('leaf-list:description', self.parsers.parse_description)
        self.registry.register('leaf-list:when', self.parsers.parse_when)
        self.registry.register('leaf-list:must', self.parsers.parse_must)
        self.registry.register('leaf-list:if-feature', self.parsers.parse_if_feature_stmt)

        # Typedef body statements
        self.registry.register('typedef:type', self.parsers.parse_type)
        self.registry.register('typedef:description', self.parsers.parse_description)
        
        # Grouping body statements
        self.registry.register('grouping:description', self.parsers.parse_description)
        self.registry.register('grouping:choice', self.parsers.parse_choice)
        self.registry.register('grouping:container', self.parsers.parse_container)
        self.registry.register('grouping:list', self.parsers.parse_list)
        self.registry.register('grouping:leaf', self.parsers.parse_leaf)
        self.registry.register('grouping:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('grouping:uses', self.parsers.parse_uses)
        self.registry.register('grouping:anydata', self.parsers.parse_anydata)
        self.registry.register('grouping:anyxml', self.parsers.parse_anyxml)
        self.registry.register('grouping:if-feature', self.parsers.parse_if_feature_stmt)
        self.registry.register('grouping:when', self.parsers.parse_when)
        self.registry.register('grouping:must', self.parsers.parse_must)

        # Choice body statements
        self.registry.register('choice:mandatory', self.parsers.parse_choice_mandatory)
        self.registry.register('choice:description', self.parsers.parse_description)
        self.registry.register('choice:when', self.parsers.parse_when)
        self.registry.register('choice:if-feature', self.parsers.parse_if_feature_stmt)
        self.registry.register('choice:case', self.parsers.parse_case)
        
        # Case body statements
        self.registry.register('case:description', self.parsers.parse_description)
        self.registry.register('case:when', self.parsers.parse_when)
        self.registry.register('case:if-feature', self.parsers.parse_if_feature_stmt)
        self.registry.register('case:uses', self.parsers.parse_uses)
        self.registry.register('case:anydata', self.parsers.parse_anydata)
        self.registry.register('case:anyxml', self.parsers.parse_anyxml)
        self.registry.register('case:leaf', self.parsers.parse_leaf)
        self.registry.register('case:container', self.parsers.parse_container)
        self.registry.register('case:list', self.parsers.parse_list)
        self.registry.register('case:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('case:choice', self.parsers.parse_choice)

        for _ctx in ("anydata", "anyxml"):
            self.registry.register(f"{_ctx}:description", self.parsers.parse_description)
            self.registry.register(f"{_ctx}:when", self.parsers.parse_when)
            self.registry.register(f"{_ctx}:must", self.parsers.parse_must)
            self.registry.register(f"{_ctx}:if-feature", self.parsers.parse_if_feature_stmt)
            self.registry.register(f"{_ctx}:mandatory", self.parsers.parse_leaf_mandatory)

    def merge_included_submodule(
        self,
        *,
        parent: YangModule,
        submodule_name: str,
        revision_date: Optional[str],
        source_dir: Optional[Path],
        tokens: TokenStream,
    ) -> None:
        """Load a submodule file and merge its definitions into *parent*."""
        if source_dir is None:
            raise tokens._make_error(
                "include requires a filesystem location for the submodule: "
                "use parse_file(), or parse_string(..., source_path=Path('module.yang'))"
            )
        path = self._resolve_submodule_path(submodule_name, revision_date, source_dir, tokens)
        sub = self._parse_submodule_from_path(path)
        if sub.name != submodule_name:
            raise tokens._make_error(
                f"submodule file defines name {sub.name!r}, include expects {submodule_name!r}"
            )
        if sub.belongs_to_module and sub.belongs_to_module != parent.name:
            raise tokens._make_error(
                f"submodule belongs-to {sub.belongs_to_module!r} "
                f"does not match module {parent.name!r}"
            )
        self._merge_submodule_definitions(parent, sub, tokens)

    def register_import(
        self,
        *,
        parent: YangModule,
        imported_module_name: str,
        local_prefix: str,
        revision_date: Optional[str],
        source_dir: Optional[Path],
        tokens: TokenStream,
    ) -> None:
        """Load an imported module and record ``local_prefix`` → module on *parent*."""
        if source_dir is None:
            raise tokens._make_error(
                "import requires a filesystem location: "
                "use parse_file(), or parse_string(..., source_path=Path('module.yang'))"
            )
        own = parent.own_prefix_stripped()
        if local_prefix == own:
            raise tokens._make_error(
                f"Import prefix {local_prefix!r} must differ from this module's prefix"
            )
        if local_prefix in parent.import_prefixes:
            raise tokens._make_error(f"Duplicate import prefix {local_prefix!r}")
        mod = self._load_imported_module(
            imported_module_name, revision_date, source_dir, tokens
        )
        if mod.name != imported_module_name:
            raise tokens._make_error(
                f"imported file defines module {mod.name!r}, import expects {imported_module_name!r}"
            )
        parent.import_prefixes[local_prefix] = mod

    def _load_imported_module(
        self,
        name: str,
        revision_date: Optional[str],
        source_dir: Path,
        tokens: TokenStream,
    ) -> YangModule:
        path = self._resolve_submodule_path(name, revision_date, source_dir, tokens)
        cached = self._module_cache.get(path)
        if cached is not None:
            return cached
        if path in self._import_pending:
            raise YangSyntaxError(
                f"Circular import: {path}",
                filename=str(path),
            )
        self._import_pending.add(path)
        try:
            inner = YangParser(
                expand_uses=self.expand_uses,
                include_path=self.include_path,
            )
            inner._module_cache = self._module_cache
            inner._import_pending = self._import_pending
            content = path.read_text(encoding="utf-8")
            mod = inner.parse_string(
                content,
                filename=str(path),
                source_path=path,
                finalize=False,
            )
            self._expand_and_augment(mod)
            self._module_cache[path] = mod
            return mod
        finally:
            self._import_pending.discard(path)

    def _resolve_submodule_path(
        self,
        name: str,
        revision_date: Optional[str],
        source_dir: Path,
        tokens: TokenStream,
    ) -> Path:
        dirs = (source_dir, *self.include_path)
        candidates: list[str] = []
        if revision_date:
            candidates.append(f"{name}@{revision_date}.yang")
        candidates.append(f"{name}.yang")
        for directory in dirs:
            for candidate in candidates:
                path = (directory / candidate).resolve()
                if path.is_file():
                    return path
        for directory in dirs:
            matches = sorted(directory.glob(f"{name}@*.yang"))
            if matches:
                return matches[-1].resolve()
        searched = ", ".join(str(d) for d in dirs)
        raise tokens._make_error(
            f"Could not find submodule {name!r} (tried filenames {candidates!r}) under [{searched}]"
        )

    def _parse_submodule_from_path(self, path: Path) -> YangModule:
        path = path.resolve()
        if path in self._include_stack:
            raise YangSyntaxError(
                f"Circular submodule include: {path}",
                filename=str(path),
            )
        self._include_stack.append(path)
        try:
            content = path.read_text(encoding="utf-8")
            return self.parse_string(
                content,
                filename=str(path),
                source_path=path,
                finalize=False,
            )
        finally:
            self._include_stack.pop()

    def _merge_submodule_definitions(
        self, parent: YangModule, sub: YangModule, tokens: TokenStream
    ) -> None:
        for n, td in sub.typedefs.items():
            if n in parent.typedefs:
                raise tokens._make_error(f"Duplicate typedef {n!r} from include of {sub.name!r}")
            parent.typedefs[n] = td
        for n, ident in sub.identities.items():
            if n in parent.identities:
                raise tokens._make_error(f"Duplicate identity {n!r} from include of {sub.name!r}")
            parent.identities[n] = ident
        for n, grp in sub.groupings.items():
            if n in parent.groupings:
                raise tokens._make_error(f"Duplicate grouping {n!r} from include of {sub.name!r}")
            parent.groupings[n] = grp
        for fname in sub.features:
            if fname in parent.features:
                raise tokens._make_error(
                    f"Duplicate feature {fname!r} from include of {sub.name!r}"
                )
            parent.features.add(fname)
        for fname, ifs in sub.feature_if_features.items():
            if fname in parent.feature_if_features:
                raise tokens._make_error(
                    f"Duplicate feature if-feature for {fname!r} from include of {sub.name!r}"
                )
            parent.feature_if_features[fname] = list(ifs)
        own = parent.own_prefix_stripped()
        for pref, im in sub.import_prefixes.items():
            if pref == own:
                continue
            existing = parent.import_prefixes.get(pref)
            if existing is not None and existing.name != im.name:
                raise tokens._make_error(
                    f"Import prefix {pref!r} from include of {sub.name!r} "
                    f"conflicts with existing import of {existing.name!r}"
                )
            if existing is None:
                parent.import_prefixes[pref] = im
        parent.statements.extend(sub.statements)
        sub.statements.clear()
        sub.typedefs.clear()
        sub.identities.clear()
        sub.groupings.clear()
        sub.features.clear()
        sub.feature_if_features.clear()
        sub.import_prefixes.clear()

    def parse_file(self, file_path: Path) -> YangModule:
        """Parse a YANG file (resolves ``include`` relative to this file's directory)."""
        path = file_path.resolve()
        self._import_pending.clear()
        self._include_stack = [path]
        try:
            content = path.read_text(encoding="utf-8")
            module = self.parse_string(
                content,
                filename=str(path),
                source_path=path,
                finalize=False,
            )
            self._expand_and_augment(module)
            return module
        finally:
            self._include_stack = []

    def parse_string(
        self,
        content: str,
        filename: Optional[str] = None,
        source_path: Optional[Path] = None,
        *,
        finalize: bool = True,
    ) -> YangModule:
        """
        Parse YANG content from a string.

        Args:
            content: YANG file content
            filename: Optional filename for error reporting
            source_path: If set, its parent directory is used to resolve ``include``
            finalize: If True (default) and ``expand_uses`` is True, run uses
                expansion, refine, and augment merge before returning. Set False when
                parsing an included submodule (the caller expands once on the
                top-level module).
        """
        module = YangModule()

        tokens = self.tokenizer.tokenize(content, filename)

        if not tokens.has_more():
            raise tokens._make_error("Empty input")
        root = tokens.peek()
        context = ParserContext(
            module=module,
            current_parent=module,
            source_dir=source_path.parent if source_path else None,
        )
        if root == "module":
            self.parsers._module_parser.parse_module(tokens, context)
        elif root == "submodule":
            self.parsers._submodule_parser.parse_submodule(tokens, context)
        else:
            raise tokens._make_error("Expected 'module' or 'submodule' statement at start of file")

        if finalize:
            self._expand_and_augment(module)

        return module


def parse_yang_file(
    file_path: str | Path,
    *,
    include_path: Tuple[str, ...] = (),
) -> YangModule:
    """Parse a YANG file and return a YangModule."""
    extras = tuple(Path(p) for p in include_path)
    parser = YangParser(include_path=extras)
    return parser.parse_file(Path(file_path))


def parse_yang_string(content: str) -> YangModule:
    """Parse YANG content from a string and return a YangModule."""
    parser = YangParser()
    return parser.parse_string(content)
