"""CLI entry point for xyang (python -m xyang / xyang command)."""

import argparse
import json
import sys
from pathlib import Path


def _parse_cmd(parser: argparse.ArgumentParser, args: list[str]) -> int:
    sub = parser.add_parser("parse", help="Parse a YANG file and print module info")
    sub.add_argument("yang_file", type=Path, help="Path to .yang file")
    sub.set_defaults(cmd="parse")
    return 0


def _validate_cmd(parser: argparse.ArgumentParser, args: list[str]) -> int:
    sub = parser.add_parser("validate", help="Validate JSON data against a YANG module")
    sub.add_argument("yang_file", type=Path, help="Path to .yang file")
    sub.add_argument("data_file", type=Path, nargs="?", default=None, help="Path to JSON data (stdin if omitted)")
    sub.set_defaults(cmd="validate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="xyang",
        description="xYang: YANG parsing and validation (subset for meta-model.yang)",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    subparsers = parser.add_subparsers(dest="cmd", help="Commands")

    parse_parser = subparsers.add_parser("parse", help="Parse a YANG file and print module info")
    parse_parser.add_argument("yang_file", type=Path, help="Path to .yang file")

    validate_parser = subparsers.add_parser("validate", help="Validate JSON data against a YANG module")
    validate_parser.add_argument("yang_file", type=Path, help="Path to .yang file")
    validate_parser.add_argument(
        "data_file", type=Path, nargs="?", default=None,
        help="Path to JSON data file (read from stdin if omitted)",
    )

    convert_parser = subparsers.add_parser("convert", help="Convert .yang to .yang.json (JSON Schema with x-yang)")
    convert_parser.add_argument("yang_file", type=Path, help="Path to .yang file")
    convert_parser.add_argument(
        "-o", "--output",
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
        p = Path(args.yang_file)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1
        try:
            module = parse_yang_file(str(p))
            validator = YangValidator(module)
            if args.data_file is not None:
                data_path = Path(args.data_file)
                if not data_path.exists():
                    print(f"Error: file not found: {data_path}", file=sys.stderr)
                    return 1
                data = json.loads(data_path.read_text(encoding="utf-8"))
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
