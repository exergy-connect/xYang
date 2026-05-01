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
from ..semantic_validate import validate_semantics
from ..uses_expand import expand_all_uses_in_module
from .tokenizer import YangTokenizer
from .parser_context import ParserContext, TokenStream
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
        self.parsers = StatementParsers(yang_parser=self)
        self.expand_uses = expand_uses
        self.include_path = include_path
        self._include_stack: list[Path] = []
        self._module_cache: dict[Path, YangModule] = {}
        self._import_pending: set[Path] = set()

    def _expand_and_augment(self, module: YangModule) -> None:
        """Runs only when ``expand_uses`` is True (same gate as reversibility)."""
        if self.expand_uses:
            expand_all_uses_in_module(module)
            apply_augmentations(module)
            apply_extension_invocations(module)
            validate_semantics(module)

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
