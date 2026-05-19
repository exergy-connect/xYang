"""CLI entry point for xyang (python -m xyang / xyang command)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

from xyang.errors import YangSemanticError, YangSyntaxError

_CLI_ERRORS: tuple[type[BaseException], ...] = (
    YangSyntaxError,
    YangSemanticError,
    OSError,
    ValueError,
    json.JSONDecodeError,
    ImportError,
    TypeError,
)
try:
    import yaml as _yaml

    _CLI_ERRORS = (*_CLI_ERRORS, _yaml.YAMLError)
except ImportError:
    pass


def _print_cli_error(exc: BaseException) -> None:
    print(f"Error: {exc}", file=sys.stderr)


def _add_include_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--include-path",
        type=Path,
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Directory to search for imported modules "
            "(repeatable; after the main file's directory)"
        ),
    )


def _include_path_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    return tuple(str(Path(p).resolve()) for p in args.include_path)


def _yang_files_in_dirs(dirs: Iterable[Path]) -> list[Path]:
    """Sorted ``*.yang`` files under each directory (non-recursive)."""
    seen: set[Path] = set()
    out: list[Path] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yang")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(path)
    return out


def _load_anydata_module_map(
    host_path: Path,
    host_module: Any,
    include_path: tuple[str, ...],
    extra_module_paths: list[Path],
) -> Dict[str, Any]:
    """Build ``module-name -> YangModule`` for anydata subtree validation."""
    from xyang.augment_expand import (
        apply_augmentations_across_module_map,
        register_module_closure,
    )
    from xyang.module import YangModule
    from xyang.parser import YangParser

    modules: Dict[str, YangModule] = {}
    register_module_closure(modules, host_module)

    if extra_module_paths:
        paths = extra_module_paths
    else:
        search_dirs = [host_path.parent, *[Path(p) for p in include_path]]
        paths = _yang_files_in_dirs(search_dirs)

    extras = tuple(Path(p) for p in include_path)
    parser = YangParser(include_path=extras)
    for yang_path in paths:
        if yang_path.resolve() == host_path.resolve():
            continue
        try:
            mod = parser.parse_file(yang_path)
        except _CLI_ERRORS as exc:
            print(f"Warning: skipping {yang_path}: {exc}", file=sys.stderr)
            continue
        register_module_closure(modules, mod)

    apply_augmentations_across_module_map(modules)
    return modules


def _load_instance_data(data_path: Path) -> Any:
    """Load JSON or YAML instance data from a file path."""
    text = data_path.read_text(encoding="utf-8")
    suffix = data_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "Reading .yaml or .yml requires PyYAML. "
                "Install it with: pip install PyYAML"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="xyang",
        description="xYang: YANG parsing and validation (subset for meta-model.yang)",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s 0.1.2",
    )
    subparsers = parser.add_subparsers(dest="cmd", help="Commands")
    path_parent = argparse.ArgumentParser(add_help=False)
    _add_include_path_argument(path_parent)

    parse_parser = subparsers.add_parser(
        "parse",
        parents=[path_parent],
        help="Parse a YANG file and print module info",
    )
    parse_parser.add_argument("yang_file", type=Path, help="Path to .yang file")

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[path_parent],
        help="Validate JSON data against a YANG module",
    )
    validate_parser.add_argument("yang_file", type=Path, help="Path to .yang file")
    validate_parser.add_argument(
        "data_file",
        type=Path,
        nargs="?",
        default=None,
        help="Path to JSON or YAML data file (.yaml/.yml need PyYAML; read from stdin if omitted)",
    )
    validate_parser.add_argument(
        "--anydata-validation",
        choices=("off", "complete", "candidate"),
        default="off",
        help=(
            "Optional draft-ietf-netmod-yang-anydata-validation: validate JSON under "
            "anydata using extra modules (RFC 7951 names). Default: off. "
            "When enabled, modules are taken from --anydata-module and/or every "
            "*.yang file in --include-path and the host file's directory."
        ),
    )
    validate_parser.add_argument(
        "--anydata-module",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Additional .yang file for the anydata module map (repeatable). "
            "If omitted, all *.yang files in --include-path and the host directory "
            "are loaded (unparseable files are skipped with a warning)."
        ),
    )

    convert_parser = subparsers.add_parser(
        "convert",
        parents=[path_parent],
        help="Convert .yang to .yang.json (JSON Schema with x-yang)",
    )
    convert_parser.add_argument("yang_file", type=Path, help="Path to .yang file")
    convert_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <stem>.yang.json alongside input)",
    )

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        return 0

    if args.cmd == "parse":
        from xyang import parse_yang_file

        p = Path(args.yang_file)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1
        try:
            module = parse_yang_file(str(p), include_path=_include_path_from_args(args))
            print(f"Module: {module.name}")
            print(f"  yang-version: {module.yang_version}")
            print(f"  namespace: {module.namespace}")
            print(f"  prefix: {module.prefix}")
            if module.organization:
                print(f"  organization: {module.organization}")
            print(f"  typedefs: {len(module.typedefs)}")
            print(f"  top-level statements: {len(module.statements)}")
        except _CLI_ERRORS as e:
            _print_cli_error(e)
            return 1
        return 0

    if args.cmd == "validate":
        from xyang import parse_yang_file, YangValidator
        from xyang.ext.anydata_validation import AnydataValidationMode
        from xyang.module import YangModule
        from xyang.validator import ValidatorExtension

        p = Path(args.yang_file)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1
        try:
            include_path = _include_path_from_args(args)
            module = parse_yang_file(str(p), include_path=include_path)
            validator = YangValidator(module)
            if args.anydata_validation != "off":
                extra_paths: list[Path] = list(args.anydata_module)
                for ep in extra_paths:
                    if not ep.exists():
                        print(f"Error: file not found: {ep}", file=sys.stderr)
                        return 1
                modules = _load_anydata_module_map(
                    p.resolve(),
                    module,
                    include_path,
                    extra_paths,
                )
                if len(modules) < 2 and not extra_paths:
                    print(
                        "Warning: --anydata-validation enabled but no extra modules "
                        "were loaded; use --include-path or --anydata-module",
                        file=sys.stderr,
                    )
                mode = (
                    AnydataValidationMode.COMPLETE
                    if args.anydata_validation == "complete"
                    else AnydataValidationMode.CANDIDATE
                )
                validator.enable_extension(
                    ValidatorExtension.ANYDATA_VALIDATION,
                    modules=modules,
                    mode=mode,
                )
            if args.data_file is not None:
                data_path = Path(args.data_file)
                if not data_path.exists():
                    print(f"Error: file not found: {data_path}", file=sys.stderr)
                    return 1
                data = _load_instance_data(data_path)
            else:
                data = json.load(sys.stdin)
            is_valid, errors, warnings = validator.validate(data)
            if is_valid:
                print("Valid.")
                for w in warnings:
                    print(f"  Warning: {w}")
                return 0
            print("Validation failed:", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            return 1
        except _CLI_ERRORS as e:
            _print_cli_error(e)
            return 1

    if args.cmd == "convert":
        from xyang.parser import YangParser
        from xyang.json import schema_to_yang_json

        p = Path(args.yang_file)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1
        out = args.output
        if out is None:
            out = p.with_suffix(".yang.json")
        else:
            out = Path(out)
            if not out.name.endswith(".yang.json"):
                out = out.parent / (out.stem + ".yang.json")
        try:
            include_path = tuple(Path(p) for p in _include_path_from_args(args))
            yang_parser = YangParser(expand_uses=False, include_path=include_path)
            module = yang_parser.parse_file(p)
            schema_to_yang_json(module, output_path=out)
            print(f"Wrote {out}")
        except _CLI_ERRORS as e:
            _print_cli_error(e)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
