"""CLI entry point for xyang (python -m xyang / xyang command)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _load_instance_data(data_path: Path) -> Any:
    """Load JSON or YAML instance data from a file path."""
    text = data_path.read_text(encoding="utf-8")
    suffix = data_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("Reading .yaml or .yml requires PyYAML. Install it with: pip install PyYAML") from exc
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
        version="%(prog)s 0.1.0",
    )
    subparsers = parser.add_subparsers(dest="cmd", help="Commands")

    parse_parser = subparsers.add_parser("parse", help="Parse a YANG file and print module info")
    parse_parser.add_argument("yang_file", type=Path, help="Path to .yang file")

    validate_parser = subparsers.add_parser("validate", help="Validate JSON data against a YANG module")
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
            "anydata using extra modules (RFC 7951 names). Default: off."
        ),
    )
    validate_parser.add_argument(
        "--anydata-module",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="Additional .yang file to load into the anydata module map (repeatable).",
    )

    convert_parser = subparsers.add_parser("convert", help="Convert .yang to .yang.json (JSON Schema with x-yang)")
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
            module = parse_yang_file(str(p))
            print(f"Module: {module.name}")
            print(f"  yang-version: {module.yang_version}")
            print(f"  namespace: {module.namespace}")
            print(f"  prefix: {module.prefix}")
            if module.organization:
                print(f"  organization: {module.organization}")
            print(f"  typedefs: {len(module.typedefs)}")
            print(f"  top-level statements: {len(module.statements)}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
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
            module = parse_yang_file(str(p))
            validator = YangValidator(module)
            if args.anydata_validation != "off":
                extra_paths: list[Path] = list(args.anydata_module)
                if not extra_paths:
                    print(
                        "Error: --anydata-validation requires at least one --anydata-module",
                        file=sys.stderr,
                    )
                    return 1
                modules: Dict[str, YangModule] = {module.name: module}
                for ep in extra_paths:
                    if not ep.exists():
                        print(f"Error: file not found: {ep}", file=sys.stderr)
                        return 1
                    m = parse_yang_file(str(ep))
                    modules[m.name] = m
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
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
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
            parser = YangParser(expand_uses=False)
            module = parser.parse_file(p)
            schema_to_yang_json(module, output_path=out)
            print(f"Wrote {out}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
