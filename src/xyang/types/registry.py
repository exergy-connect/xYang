"""One frozen table for how a YANG built-in maps to JSON.

``src/xyang/types/registry.py`` and ``ts/src/types/registry.ts`` are the only
places that name the built-in encodings. Schema export, schema import, and the
strict RFC 7951 value check call this table.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from ..ast import YangBitStmt, YangPatternSpec, YangTypeStmt
from ..identifier_ref import coerce_identifier_ref
from ..json.schema_keys import (
    JsonSchemaKey,
    XYangKey,
    XYangTypeValue,
    json_schema_defs_uri,
)

# Built-in names. The string ``int64`` lives only here.
INT8 = "int8"
INT16 = "int16"
INT32 = "int32"
INT64 = "int64"
UINT8 = "uint8"
UINT16 = "uint16"
UINT32 = "uint32"
UINT64 = "uint64"
DECIMAL64 = "decimal64"
STRING = "string"
BOOLEAN = "boolean"
EMPTY = "empty"
ENUMERATION = "enumeration"
BITS = "bits"
BINARY = "binary"
UNION = "union"
LEAFREF = "leafref"
IDENTITYREF = "identityref"
INSTANCE_IDENTIFIER = "instance-identifier"

_INT64_PATTERN = "^-?[0-9]+$"
_UINT64_PATTERN = "^[0-9]+$"
_DECIMAL_PATTERN = r"^-?[0-9]+(\.[0-9]+)?$"

TypeIssue = tuple[str, str]
_SchemaFn = Callable[["Builtin", YangTypeStmt], dict[str, Any]]
_ParseFn = Callable[["Builtin", "SchemaFragment"], YangTypeStmt | None]
_CheckFn = Callable[["Builtin", Any, YangTypeStmt], TypeIssue | None]

_EMIT: contextvars.ContextVar[tuple[Any, Any, Any]] = contextvars.ContextVar("xyang_builtin_emit")


def _json_type_name(value: Any) -> str:
    """RFC 8259 type name of an instance value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


class SchemaFragment:
    """JSON Schema piece plus the ``x-yang`` object and ``$defs`` for import."""

    __slots__ = ("schema", "xyang", "defs")

    def __init__(self, schema: Mapping[str, Any], xyang: Mapping[str, Any], defs: Mapping[str, Any]):
        self.schema = schema
        self.xyang = xyang
        self.defs = defs


def _parts(fragment: SchemaFragment | Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if isinstance(fragment, SchemaFragment):
        return fragment.schema, fragment.xyang, fragment.defs
    schema = fragment
    xyang = schema.get(JsonSchemaKey.X_YANG) or {}
    if not isinstance(xyang, Mapping):
        xyang = {}
    return schema, xyang, {}


@dataclass(frozen=True, slots=True)
class Builtin:
    """How one YANG built-in is encoded, exported, imported, and checked."""

    name: str
    json_encoding: str
    bounds: tuple[int, int] | None
    pattern: str | None

    @property
    def family(self) -> str:
        if self.bounds is not None:
            return "integer"
        if self.name == DECIMAL64:
            return "decimal"
        if self.name == STRING:
            return "string"
        return self.name

    def to_schema(self, type_stmt: YangTypeStmt) -> dict[str, Any]:
        return _TO_SCHEMA[self.name](self, type_stmt)

    def from_schema(self, fragment: SchemaFragment | Mapping[str, Any]) -> YangTypeStmt | None:
        schema, xyang, defs = _parts(fragment)
        return _FROM_SCHEMA[self.name](self, SchemaFragment(schema, xyang, defs))

    def check_value(self, value: Any, type_stmt: YangTypeStmt) -> TypeIssue | None:
        return _CHECK[self.name](self, value, type_stmt)


def _plain_string(_builtin: Builtin, _type_stmt: YangTypeStmt) -> dict[str, Any]:
    return {JsonSchemaKey.TYPE: "string"}


def _to_string(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    out: dict[str, Any] = {JsonSchemaKey.TYPE: "string"}
    specs = list(getattr(type_stmt, "patterns", None) or [])

    def _anchored(p: str) -> str:
        return p if (p.startswith("^") and p.endswith("$")) else f"^{p}$"

    if specs:
        if len(specs) == 1 and not bool(
            getattr(specs[0], "invert_match", False) if hasattr(specs[0], "invert_match") else specs[0].get("invert_match", False)
        ):
            p = getattr(specs[0], "pattern", None) if hasattr(specs[0], "pattern") else specs[0].get("pattern")
            if isinstance(p, str) and p:
                out[JsonSchemaKey.PATTERN] = _anchored(p)
        else:
            all_of: list[dict[str, Any]] = []
            for spec in specs:
                patt = getattr(spec, "pattern", None) if hasattr(spec, "pattern") else spec.get("pattern")
                if not isinstance(patt, str) or not patt:
                    continue
                anchored = _anchored(patt)
                inv = bool(
                    getattr(spec, "invert_match", False) if hasattr(spec, "invert_match") else spec.get("invert_match", False)
                )
                if inv:
                    all_of.append(
                        {
                            JsonSchemaKey.NOT: {
                                JsonSchemaKey.TYPE: "string",
                                JsonSchemaKey.PATTERN: anchored,
                            }
                        }
                    )
                else:
                    all_of.append({JsonSchemaKey.PATTERN: anchored})
            if all_of:
                out[JsonSchemaKey.ALL_OF] = all_of
    if type_stmt.length:
        parts = type_stmt.length.split("..")
        min_len = None
        max_len = None
        if len(parts) >= 1 and parts[0].strip():
            try:
                min_len = int(parts[0].strip())
            except ValueError:
                pass
        if len(parts) >= 2 and parts[1].strip() and parts[1].strip().lower() != "max":
            try:
                max_len = int(parts[1].strip())
            except ValueError:
                pass
        if min_len is not None:
            out[JsonSchemaKey.MIN_LENGTH] = min_len
        if max_len is not None:
            out[JsonSchemaKey.MAX_LENGTH] = max_len
    xyang_pattern: dict[str, Any] = {}
    if specs:
        entries: list[dict[str, Any]] = []
        for spec in specs:
            patt = getattr(spec, "pattern", None) if hasattr(spec, "pattern") else spec.get("pattern")
            if not isinstance(patt, str):
                continue
            entry: dict[str, Any] = {
                JsonSchemaKey.PATTERN: patt,
                "invert-match": bool(
                    getattr(spec, "invert_match", False) if hasattr(spec, "invert_match") else spec.get("invert_match", False)
                ),
            }
            em = getattr(spec, "error_message", None) if hasattr(spec, "error_message") else spec.get("error_message")
            et = getattr(spec, "error_app_tag", None) if hasattr(spec, "error_app_tag") else spec.get("error_app_tag")
            if isinstance(em, str):
                entry[XYangKey.PATTERN_ERROR_MESSAGE] = em
            if isinstance(et, str):
                entry[XYangKey.PATTERN_ERROR_APP_TAG] = et
            entries.append(entry)
        if entries:
            xyang_pattern[XYangKey.STRING_PATTERNS] = entries
            last = entries[-1]
            if XYangKey.PATTERN_ERROR_MESSAGE in last:
                xyang_pattern[XYangKey.PATTERN_ERROR_MESSAGE] = last[XYangKey.PATTERN_ERROR_MESSAGE]
            if XYangKey.PATTERN_ERROR_APP_TAG in last:
                xyang_pattern[XYangKey.PATTERN_ERROR_APP_TAG] = last[XYangKey.PATTERN_ERROR_APP_TAG]
    if xyang_pattern:
        out[JsonSchemaKey.X_YANG] = xyang_pattern
    return out


def _to_enumeration(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    if type_stmt.enums:
        return {JsonSchemaKey.TYPE: "string", JsonSchemaKey.ENUM: list(type_stmt.enums)}
    return {JsonSchemaKey.TYPE: "string"}


def _to_bits(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    if not type_stmt.bits:
        return {JsonSchemaKey.TYPE: "string"}
    from ..json.generator import _bits_space_separated_pattern, _with_description

    ordered = sorted(
        type_stmt.bits,
        key=lambda b: (
            b.position if b.position is not None else 0,
            b.name,
        ),
    )
    bits_obj: dict[str, int] = {}
    for bit in ordered:
        bits_obj[bit.name] = int(bit.position) if bit.position is not None else 0
    bit_names = [bit.name for bit in ordered]
    desc = (
        "YANG bits (RFC 7950): space-separated subset of these names (order irrelevant; "
        "no duplicate names in instance data). Positions: see x-yang.bits. "
        f"Names: {', '.join(bit_names)}."
    )
    examples: list[str] = ["", bit_names[0]]
    if len(bit_names) > 1:
        examples.append(" ".join(bit_names))
    out = {JsonSchemaKey.TYPE: "string"}
    _with_description(out, desc)
    out[JsonSchemaKey.PATTERN] = _bits_space_separated_pattern(bit_names)
    out[JsonSchemaKey.EXAMPLES] = examples
    out[JsonSchemaKey.X_YANG] = {
        XYangKey.TYPE: XYangTypeValue.BITS,
        XYangKey.BITS: bits_obj,
    }
    return out


def _to_boolean(_builtin: Builtin, _type_stmt: YangTypeStmt) -> dict[str, Any]:
    return {JsonSchemaKey.TYPE: "boolean"}


def _to_integer(builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    if builtin.json_encoding == "string-number":
        out: dict[str, Any] = {
            JsonSchemaKey.TYPE: "string",
            JsonSchemaKey.PATTERN: builtin.pattern,
        }
        xyang: dict[str, Any] = {XYangKey.TYPE: builtin.name}
        if type_stmt.range:
            xyang["range"] = type_stmt.range
        out[JsonSchemaKey.X_YANG] = xyang
        return out
    out = {JsonSchemaKey.TYPE: "integer"}
    min_v, max_v = json_integer_bounds_for_builtin(builtin.name, type_stmt.range or None)
    if min_v is not None:
        out[JsonSchemaKey.MINIMUM] = min_v
    if max_v is not None:
        out[JsonSchemaKey.MAXIMUM] = max_v
    return out


def _to_decimal(builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    out: dict[str, Any] = {
        JsonSchemaKey.TYPE: "string",
        JsonSchemaKey.PATTERN: builtin.pattern,
    }
    xyang: dict[str, Any] = {XYangKey.TYPE: DECIMAL64}
    if type_stmt.fraction_digits is not None:
        xyang["fraction-digits"] = int(type_stmt.fraction_digits)
    if type_stmt.range:
        xyang["range"] = type_stmt.range
    out[JsonSchemaKey.X_YANG] = xyang
    return out


def _to_empty(_builtin: Builtin, _type_stmt: YangTypeStmt) -> dict[str, Any]:
    return {JsonSchemaKey.TYPE: "object", JsonSchemaKey.MAX_PROPERTIES: 0}


def _to_union(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    if not type_stmt.types:
        return {JsonSchemaKey.TYPE: "string"}
    from ..json.generator import _type_to_schema

    typedef_names, module, anchor = _EMIT.get()
    return {
        JsonSchemaKey.ONE_OF: [
            _type_to_schema(member, typedef_names, module=module, leafref_anchor=anchor) for member in type_stmt.types
        ],
    }


def _to_identityref(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    from ..json.generator import _format_bases_for_json

    bases = _format_bases_for_json(list(type_stmt.identityref_bases or []))
    if not bases:
        return {JsonSchemaKey.TYPE: "string"}
    xyang = {
        XYangKey.TYPE: XYangTypeValue.IDENTITYREF,
        XYangKey.BASES: bases,
    }
    if len(bases) == 1:
        return {
            JsonSchemaKey.REF: json_schema_defs_uri(bases[0]),
            JsonSchemaKey.X_YANG: xyang,
        }
    return {
        JsonSchemaKey.ALL_OF: [{JsonSchemaKey.REF: json_schema_defs_uri(base)} for base in bases],
        JsonSchemaKey.X_YANG: xyang,
    }


def _to_leafref(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    from ..json.generator import _leafref_path_string, _resolve_leafref_target_leaf, _type_to_schema
    from ..xpath.ast import PathNode

    typedef_names, module, anchor = _EMIT.get()
    path_str = _leafref_path_string(type_stmt.path)
    require = getattr(type_stmt, "require_instance", True)
    path_node = type_stmt.path if isinstance(type_stmt.path, PathNode) else None
    target_leaf = _resolve_leafref_target_leaf(module, path_node, anchor)
    target_type = target_leaf.type if target_leaf and target_leaf.type else None
    if target_type is not None and module is not None:
        inner = _type_to_schema(target_type, typedef_names, module=module, leafref_anchor=None)
    else:
        inner = {JsonSchemaKey.TYPE: "string"}
    inner_clean = {key: value for key, value in inner.items() if key != JsonSchemaKey.X_YANG}
    return {
        **inner_clean,
        JsonSchemaKey.X_YANG: {
            XYangKey.TYPE: LEAFREF,
            XYangKey.PATH: path_str,
            XYangKey.REQUIRE_INSTANCE: require,
        },
    }


def _to_instance_identifier(_builtin: Builtin, type_stmt: YangTypeStmt) -> dict[str, Any]:
    require = getattr(type_stmt, "require_instance", True)
    return {
        JsonSchemaKey.TYPE: "string",
        JsonSchemaKey.X_YANG: {
            XYangKey.TYPE: XYangTypeValue.INSTANCE_IDENTIFIER,
            XYangKey.REQUIRE_INSTANCE: require,
        },
    }


def _unused(_builtin: Builtin, _fragment: SchemaFragment) -> YangTypeStmt | None:
    return None


def _from_number_integer(builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.schema.get(JsonSchemaKey.TYPE) != "integer":
        return None
    name, range_str = yang_integer_from_json_bounds(
        fragment.schema.get(JsonSchemaKey.MINIMUM),
        fragment.schema.get(JsonSchemaKey.MAXIMUM),
    )
    if name != builtin.name:
        return None
    type_stmt = YangTypeStmt(name=name)
    if range_str:
        type_stmt.range = range_str
    return type_stmt


def _from_quoted_integer(builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.schema.get(JsonSchemaKey.TYPE) != "string":
        return None
    if fragment.xyang.get(XYangKey.TYPE) != builtin.name:
        return None
    type_stmt = YangTypeStmt(name=builtin.name)
    rng = fragment.xyang.get("range")
    if isinstance(rng, str) and rng:
        type_stmt.range = rng
    return type_stmt


def _from_decimal(builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    xyang = fragment.xyang
    kind = schema.get(JsonSchemaKey.TYPE)
    if kind == "string" and xyang.get(XYangKey.TYPE) == DECIMAL64:
        type_stmt = YangTypeStmt(name=DECIMAL64)
        rng = xyang.get("range")
        if isinstance(rng, str) and rng:
            type_stmt.range = rng
        fd = xyang.get("fraction-digits")
        if isinstance(fd, int) and not isinstance(fd, bool):
            type_stmt.fraction_digits = fd
        return type_stmt
    if kind != "number":
        return None
    from ..json.parser import _format_decimal64_bound, _fraction_digits_from_multiple_of

    type_stmt = YangTypeStmt(name=DECIMAL64)
    legacy_fd = schema.get(JsonSchemaKey.X_FRACTION_DIGITS)
    if isinstance(legacy_fd, int) and legacy_fd > 0:
        type_stmt.fraction_digits = legacy_fd
    else:
        fd = _fraction_digits_from_multiple_of(schema.get(JsonSchemaKey.MULTIPLE_OF))
        if fd is not None:
            type_stmt.fraction_digits = fd
    min_val = schema.get(JsonSchemaKey.MINIMUM)
    max_val = schema.get(JsonSchemaKey.MAXIMUM)
    if min_val is not None or max_val is not None:
        digits = type_stmt.fraction_digits
        lo = "min" if min_val is None else _format_decimal64_bound(min_val, digits)
        hi = "max" if max_val is None else _format_decimal64_bound(max_val, digits)
        type_stmt.range = f"{lo}..{hi}"
    return type_stmt


def _from_boolean(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.schema.get(JsonSchemaKey.TYPE) == "boolean":
        return YangTypeStmt(name=BOOLEAN)
    return None


def _from_empty(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    if schema.get(JsonSchemaKey.TYPE) == "object" and schema.get(JsonSchemaKey.MAX_PROPERTIES) == 0:
        return YangTypeStmt(name=EMPTY)
    return None


def _from_enumeration(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    if JsonSchemaKey.ENUM not in schema:
        return None
    enums = list(schema[JsonSchemaKey.ENUM]) if isinstance(schema[JsonSchemaKey.ENUM], list) else []
    if len(enums) > 1:
        type_stmt = YangTypeStmt(name=ENUMERATION)
        type_stmt.enums = enums
        return type_stmt
    return None


def _from_bits(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.xyang.get(XYangKey.TYPE) != XYangTypeValue.BITS:
        return None
    raw = fragment.xyang.get(XYangKey.BITS)
    bits: list[YangBitStmt] = []
    if isinstance(raw, dict):
        for name, pos in raw.items():
            if not isinstance(name, str) or not name:
                continue
            try:
                position = int(pos)
            except (TypeError, ValueError):
                continue
            bits.append(YangBitStmt(name=name, position=position))
        bits.sort(key=lambda bit: (bit.position if bit.position is not None else 0, bit.name))
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            if isinstance(item, dict):
                name = item.get("name")
                if not isinstance(name, str) or not name:
                    continue
                pos = item.get("position", index)
                try:
                    position = int(pos)
                except (TypeError, ValueError):
                    position = index
                bits.append(YangBitStmt(name=name, position=position))
            elif isinstance(item, str) and item:
                bits.append(YangBitStmt(name=item, position=index))
    if bits:
        return YangTypeStmt(name=BITS, bits=bits)
    return None


def _from_leafref(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.xyang.get(XYangKey.TYPE) != LEAFREF:
        return None
    from ..xpath.parser import XPathParser

    path_val = fragment.xyang.get(XYangKey.PATH)
    require = fragment.xyang.get(XYangKey.REQUIRE_INSTANCE, True)
    path_node = None
    if path_val is not None and isinstance(path_val, str) and path_val.strip():
        path_node = XPathParser(path_val.strip()).parse_path()
    return YangTypeStmt(name=LEAFREF, path=path_node, require_instance=bool(require))


def _from_identityref(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.xyang.get(XYangKey.TYPE) != XYangTypeValue.IDENTITYREF:
        return None
    from ..json.parser import _bases_from_json

    bases = _bases_from_json(fragment.xyang.get(XYangKey.BASES))
    if not bases:
        base = fragment.xyang.get(XYangKey.BASE)
        if isinstance(base, str):
            ref = coerce_identifier_ref(base)
            if ref is not None:
                bases = [ref]
    return YangTypeStmt(name=IDENTITYREF, identityref_bases=bases)


def _from_instance_identifier(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    if fragment.xyang.get(XYangKey.TYPE) != XYangTypeValue.INSTANCE_IDENTIFIER:
        return None
    require = fragment.xyang.get(XYangKey.REQUIRE_INSTANCE, True)
    return YangTypeStmt(name=INSTANCE_IDENTIFIER, require_instance=bool(require))


def _from_union(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    if JsonSchemaKey.ONE_OF not in schema:
        return None
    from ..json.parser import _type_from_schema

    members = []
    for branch in schema.get(JsonSchemaKey.ONE_OF) or []:
        if isinstance(branch, dict):
            branch_xyang = branch.get(JsonSchemaKey.X_YANG) or {}
            parsed = _type_from_schema(fragment.defs, branch, branch_xyang)
            if parsed:
                members.append(parsed)
    if members:
        return YangTypeStmt(name=UNION, types=members)
    return None


def _from_string(_builtin: Builtin, fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    xyang = fragment.xyang
    if schema.get(JsonSchemaKey.TYPE) != "string":
        return None
    numeric = xyang.get(XYangKey.TYPE)
    if isinstance(numeric, str) and is_string_number(numeric):
        return None
    from ..json.parser import _apply_string_pattern_entries, _merge_schema_xyang, _pattern_metadata_from_xyang

    type_stmt = YangTypeStmt(name=STRING)
    raw_pat: str | None = None
    if JsonSchemaKey.PATTERN in schema:
        pattern = schema[JsonSchemaKey.PATTERN]
        if isinstance(pattern, str):
            if pattern.startswith("^") and pattern.endswith("$"):
                pattern = pattern[1:-1]
            raw_pat = pattern
    min_len = schema.get(JsonSchemaKey.MIN_LENGTH)
    max_len = schema.get(JsonSchemaKey.MAX_LENGTH)
    if min_len is not None and max_len is not None:
        type_stmt.length = f"{min_len}..{max_len}"
    elif max_len is not None:
        type_stmt.length = f"0..{max_len}"
    elif min_len is not None:
        type_stmt.length = f"{min_len}.."
    merged = _merge_schema_xyang(dict(schema), dict(xyang))
    message, tag = _pattern_metadata_from_xyang(merged)
    _apply_string_pattern_entries(type_stmt, merged)
    if not type_stmt.patterns and raw_pat is not None:
        type_stmt.patterns = [
            YangPatternSpec(
                pattern=raw_pat,
                invert_match=False,
                error_message=message,
                error_app_tag=tag,
            )
        ]
    return type_stmt


def _integer_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if isinstance(value, bool) or isinstance(value, str):
        return ("type", f"Expected integer, got {_json_type_name(value)}")
    if isinstance(value, int):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return ("type", f"Expected integer, got {_json_type_name(value)}")
        try:
            int(value)
        except (OverflowError, ValueError):
            return ("type", f"Expected integer, got {_json_type_name(value)}")
        return None
    try:
        int(value)
    except (TypeError, ValueError):
        return ("type", f"Expected integer, got {_json_type_name(value)}")
    return None


def _decimal_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if isinstance(value, bool):
        return ("type", f"Expected number, got {_json_type_name(value)}")
    if isinstance(value, str):
        return ("type", f"Expected number, got {_json_type_name(value)}")
    try:
        float(value)
    except (TypeError, ValueError):
        return ("type", f"Value {value!r} is not a valid number")
    return None


def _string_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not isinstance(value, str):
        return ("type", f"Expected string, got {_json_type_name(value)}")
    return None


def _boolean_check(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if value not in (True, False, "true", "false"):
        return ("type", f"Value {value!r} is not a valid boolean (expected true or false)")
    return None


def _empty_check(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if value is not None:
        return ("type", f"Empty type leaf should have no value, got {value!r}")
    return None


def _enumeration_check(_builtin: Builtin, value: Any, type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not type_stmt.enums:
        return (
            "enum",
            "enumeration type has no enum definitions in schema; cannot validate instance data",
        )
    allowed = [str(item) for item in type_stmt.enums]
    if str(value) not in allowed:
        return (
            "enum",
            f"Value {value!r} is not one of the allowed enum values: {', '.join(allowed)}",
        )
    return None


def _bits_check(_builtin: Builtin, value: Any, type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not isinstance(value, str):
        return ("bits", f"bits value must be a string (space-sep bit names), got {type(value).__name__}")
    bits = type_stmt.bits or []
    allowed = {bit.name for bit in bits}
    if not allowed:
        return ("bits", "bits type has no bit definitions")
    parts = [part for part in (piece.strip() for piece in value.split()) if part]
    seen: set[str] = set()
    for token in parts:
        if token in seen:
            return ("bits", f"Duplicate bit {token!r} in bits value")
        seen.add(token)
        if token not in allowed:
            return ("bits", f"Unknown bit {token!r}; allowed: {', '.join(sorted(allowed))}")
    return None


def _binary_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not isinstance(value, str):
        return ("type", f"binary value must be a base64-encoded string, got {type(value).__name__}")
    return None


def _identityref_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not isinstance(value, str):
        return ("identityref", f"identityref value must be a string, got {type(value).__name__}")
    return None


def _instance_identifier_json_error(_builtin: Builtin, value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    if not isinstance(value, str):
        return (
            "instance-identifier",
            f"instance-identifier value must be a string, got {type(value).__name__}",
        )
    return None


def _accept(_builtin: Builtin, _value: Any, _type_stmt: YangTypeStmt) -> TypeIssue | None:
    return None


def _builtin(
    name: str,
    json_encoding: str,
    bounds: tuple[int, int] | None,
    pattern: str | None,
) -> Builtin:
    return Builtin(name=name, json_encoding=json_encoding, bounds=bounds, pattern=pattern)


_BUILTINS: tuple[Builtin, ...] = (
    _builtin(INT8, "number", (-128, 127), None),
    _builtin(INT16, "number", (-32768, 32767), None),
    _builtin(INT32, "number", (-2147483648, 2147483647), None),
    _builtin(INT64, "string-number", (-9223372036854775808, 9223372036854775807), _INT64_PATTERN),
    _builtin(UINT8, "number", (0, 255), None),
    _builtin(UINT16, "number", (0, 65535), None),
    _builtin(UINT32, "number", (0, 4294967295), None),
    _builtin(UINT64, "string-number", (0, 18446744073709551615), _UINT64_PATTERN),
    _builtin(DECIMAL64, "string-number", None, _DECIMAL_PATTERN),
    _builtin(STRING, "string", None, None),
    _builtin(BOOLEAN, "boolean", None, None),
    _builtin(EMPTY, "empty", None, None),
    _builtin(ENUMERATION, "string", None, None),
    _builtin(BITS, "string", None, None),
    _builtin(BINARY, "string", None, None),
    _builtin(UNION, "string", None, None),
    _builtin(LEAFREF, "string", None, None),
    _builtin(IDENTITYREF, "string", None, None),
    _builtin(INSTANCE_IDENTIFIER, "string", None, None),
)

REGISTRY: Mapping[str, Builtin] = MappingProxyType({item.name: item for item in _BUILTINS})

_TO_SCHEMA: dict[str, _SchemaFn] = {
    INT8: _to_integer,
    INT16: _to_integer,
    INT32: _to_integer,
    INT64: _to_integer,
    UINT8: _to_integer,
    UINT16: _to_integer,
    UINT32: _to_integer,
    UINT64: _to_integer,
    DECIMAL64: _to_decimal,
    STRING: _to_string,
    BOOLEAN: _to_boolean,
    EMPTY: _to_empty,
    ENUMERATION: _to_enumeration,
    BITS: _to_bits,
    BINARY: _plain_string,
    UNION: _to_union,
    LEAFREF: _to_leafref,
    IDENTITYREF: _to_identityref,
    INSTANCE_IDENTIFIER: _to_instance_identifier,
}

_FROM_SCHEMA: dict[str, _ParseFn] = {
    INT8: _from_number_integer,
    INT16: _from_number_integer,
    INT32: _from_number_integer,
    INT64: _from_quoted_integer,
    UINT8: _from_number_integer,
    UINT16: _from_number_integer,
    UINT32: _from_number_integer,
    UINT64: _from_quoted_integer,
    DECIMAL64: _from_decimal,
    STRING: _from_string,
    BOOLEAN: _from_boolean,
    EMPTY: _from_empty,
    ENUMERATION: _from_enumeration,
    BITS: _from_bits,
    BINARY: _unused,
    UNION: _from_union,
    LEAFREF: _from_leafref,
    IDENTITYREF: _from_identityref,
    INSTANCE_IDENTIFIER: _from_instance_identifier,
}

_CHECK: dict[str, _CheckFn] = {
    INT8: _integer_json_error,
    INT16: _integer_json_error,
    INT32: _integer_json_error,
    INT64: _integer_json_error,
    UINT8: _integer_json_error,
    UINT16: _integer_json_error,
    UINT32: _integer_json_error,
    UINT64: _integer_json_error,
    DECIMAL64: _decimal_json_error,
    STRING: _string_json_error,
    BOOLEAN: _boolean_check,
    EMPTY: _empty_check,
    ENUMERATION: _enumeration_check,
    BITS: _bits_check,
    BINARY: _binary_json_error,
    UNION: _accept,
    LEAFREF: _accept,
    IDENTITYREF: _identityref_json_error,
    INSTANCE_IDENTIFIER: _instance_identifier_json_error,
}

# Inclusive JSON Schema bounds. Order matches the historical integer table.
YANG_INTEGER_BOUNDS: dict[str, tuple[int, int]] = {
    name: spec.bounds for name, spec in REGISTRY.items() if spec.bounds is not None
}
YANG_INTEGER_BUILTIN_NAMES = frozenset(YANG_INTEGER_BOUNDS)
YANG_INTEGER_NAMES = YANG_INTEGER_BUILTIN_NAMES
INTEGER_TYPE_NAMES = YANG_INTEGER_NAMES | {"integer"}
DECIMAL_TYPE_NAMES = frozenset({DECIMAL64, "number"})
QUOTED_INTEGER_NAMES = frozenset(
    name for name, spec in REGISTRY.items() if spec.json_encoding == "string-number" and spec.bounds is not None
)
NUMBER_INTEGER_NAMES = frozenset(name for name, spec in REGISTRY.items() if spec.json_encoding == "number")
STRINGISH_NAMES = frozenset(
    name for name, spec in REGISTRY.items() if spec.json_encoding == "string" and name != UNION
)


def _parse_range(range_str: str) -> tuple[Optional[int], Optional[int]]:
    parts = range_str.split("..", 1)
    lo: Optional[int] = None
    hi: Optional[int] = None
    if parts[0].strip() and parts[0].strip().lower() != "min":
        try:
            lo = int(parts[0].strip())
        except ValueError:
            pass
    if len(parts) > 1 and parts[1].strip() and parts[1].strip().lower() != "max":
        try:
            hi = int(parts[1].strip())
        except ValueError:
            pass
    return lo, hi


def json_integer_bounds_for_builtin(
    yang_type: str,
    range_str: Optional[str] = None,
) -> tuple[Optional[int], Optional[int]]:
    """Return JSON Schema ``minimum`` / ``maximum`` for a YANG integer built-in."""
    if yang_type not in YANG_INTEGER_BOUNDS:
        return None, None
    blo, bhi = YANG_INTEGER_BOUNDS[yang_type]
    if not range_str:
        return blo, bhi
    lo, hi = _parse_range(range_str)
    parts = range_str.split("..", 1)
    lo_s = parts[0].strip()
    hi_s = parts[1].strip() if len(parts) > 1 else ""
    if lo_s.lower() == "min":
        lo = blo
    if ".." in range_str and hi_s.lower() == "max":
        hi = bhi
    return lo, hi


def _coerce_int(value: object | None) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _signed_order() -> tuple[str, ...]:
    return tuple(name for name, spec in REGISTRY.items() if spec.bounds is not None and spec.bounds[0] < 0)


def _unsigned_order() -> tuple[str, ...]:
    return tuple(name for name, spec in REGISTRY.items() if spec.bounds is not None and spec.bounds[0] >= 0)


def _narrowest_integer_builtin(lo: Optional[int], hi: Optional[int]) -> str:
    """Pick the narrowest built-in that can hold the bounds (unsigned preferred when lo >= 0)."""
    signed = _signed_order()
    unsigned = _unsigned_order()
    if lo is not None and lo < 0:
        order = signed
    else:
        order = unsigned + signed
    effective_lo = lo if lo is not None else YANG_INTEGER_BOUNDS[order[0]][0]
    effective_hi = hi if hi is not None else YANG_INTEGER_BOUNDS[order[-1]][1]
    for name in order:
        blo, bhi = YANG_INTEGER_BOUNDS[name]
        if effective_lo >= blo and effective_hi <= bhi:
            return name
    return INT64


def yang_integer_from_json_bounds(
    min_val: object | None,
    max_val: object | None,
) -> tuple[str, Optional[str]]:
    """Infer a YANG integer built-in and optional ``range`` from JSON Schema bounds."""
    lo = _coerce_int(min_val)
    hi = _coerce_int(max_val)

    if lo is None and hi is None:
        return "integer", None

    if lo is not None and hi is not None:
        for name, (blo, bhi) in YANG_INTEGER_BOUNDS.items():
            if lo == blo and hi == bhi:
                return name, None

    if lo == 0 and hi is not None:
        for name in _signed_order():
            if hi == YANG_INTEGER_BOUNDS[name][1]:
                return name, "0..max"

    range_str: Optional[str] = None
    if lo is not None or hi is not None:
        min_part = str(lo) if lo is not None else "min"
        max_part = str(hi) if hi is not None else "max"
        range_str = f"{min_part}..{max_part}"

    base = _narrowest_integer_builtin(lo, hi)
    return base, range_str


def integer_bounds_for(name: str) -> tuple[int, int] | None:
    return YANG_INTEGER_BOUNDS.get(name)


def is_string_number(name: str) -> bool:
    spec = REGISTRY.get(name)
    return spec is not None and spec.json_encoding == "string-number"


def integer_json_error(value: Any) -> TypeIssue | None:
    return _integer_json_error(REGISTRY[INT32], value, YangTypeStmt(name=INT32))


def type_to_schema(
    type_stmt: YangTypeStmt,
    typedef_names: set[str],
    module: Any = None,
    leafref_anchor: Any = None,
) -> dict[str, Any]:
    """JSON Schema fragment for a type. Typedef names become ``$ref``."""
    name = type_stmt.name
    if name in typedef_names:
        return {JsonSchemaKey.REF: json_schema_defs_uri(name)}
    spec = REGISTRY.get(name)
    if spec is None:
        return {JsonSchemaKey.TYPE: "string"}
    token = _EMIT.set((typedef_names, module, leafref_anchor))
    try:
        return spec.to_schema(type_stmt)
    finally:
        _EMIT.reset(token)


def _singleton_enum_string(fragment: SchemaFragment) -> YangTypeStmt | None:
    schema = fragment.schema
    if JsonSchemaKey.ENUM not in schema:
        return None
    enums = list(schema[JsonSchemaKey.ENUM]) if isinstance(schema[JsonSchemaKey.ENUM], list) else []
    kind = schema.get(JsonSchemaKey.TYPE)
    if len(enums) == 1 and kind == "string" and isinstance(enums[0], str):
        from ..json.parser import _apply_string_pattern_entries, _merge_schema_xyang, _pattern_metadata_from_xyang

        type_stmt = YangTypeStmt(name=STRING)
        pattern = "\\*" if enums[0] == "*" else enums[0]
        merged = _merge_schema_xyang(dict(schema), dict(fragment.xyang))
        message, tag = _pattern_metadata_from_xyang(merged)
        _apply_string_pattern_entries(type_stmt, merged)
        if not type_stmt.patterns:
            type_stmt.patterns = [
                YangPatternSpec(
                    pattern=pattern,
                    invert_match=False,
                    error_message=message,
                    error_app_tag=tag,
                )
            ]
        return type_stmt
    return None


def _integer_stmt_from_bounds(fragment: SchemaFragment) -> YangTypeStmt:
    name, range_str = yang_integer_from_json_bounds(
        fragment.schema.get(JsonSchemaKey.MINIMUM),
        fragment.schema.get(JsonSchemaKey.MAXIMUM),
    )
    type_stmt = YangTypeStmt(name=name)
    if range_str:
        type_stmt.range = range_str
    return type_stmt


def type_stmt_from_schema(
    defs: Mapping[str, Any],
    schema: Mapping[str, Any],
    xyang: Mapping[str, Any],
) -> YangTypeStmt | None:
    """Rebuild a ``type`` statement from a JSON Schema fragment."""
    fragment = SchemaFragment(schema, xyang, defs)
    for name in (IDENTITYREF, INSTANCE_IDENTIFIER, BITS, LEAFREF):
        parsed = REGISTRY[name].from_schema(fragment)
        if parsed is not None:
            return parsed
    ref = schema.get(JsonSchemaKey.REF)
    if ref:
        from ..json.parser import _ref_to_typedef_name

        typedef_name = _ref_to_typedef_name(ref) if isinstance(ref, str) else None
        if typedef_name:
            return YangTypeStmt(name=typedef_name)
    parsed = REGISTRY[ENUMERATION].from_schema(fragment)
    if parsed is not None:
        return parsed
    parsed = _singleton_enum_string(fragment)
    if parsed is not None:
        return parsed
    if schema.get(JsonSchemaKey.TYPE) == "string":
        for name in (INT64, UINT64, DECIMAL64):
            parsed = REGISTRY[name].from_schema(fragment)
            if parsed is not None:
                return parsed
        return REGISTRY[STRING].from_schema(fragment)
    if schema.get(JsonSchemaKey.TYPE) == "integer":
        return _integer_stmt_from_bounds(fragment)
    parsed = REGISTRY[DECIMAL64].from_schema(fragment)
    if parsed is not None:
        return parsed
    for name in (BOOLEAN, EMPTY, UNION):
        parsed = REGISTRY[name].from_schema(fragment)
        if parsed is not None:
            return parsed
    return None


def registry_parity_snapshot() -> dict[str, dict[str, Any]]:
    """``json_encoding``, ``bounds``, and ``pattern`` for the cross-language check."""
    snapshot: dict[str, dict[str, Any]] = {}
    for name, spec in REGISTRY.items():
        bounds = None if spec.bounds is None else [str(spec.bounds[0]), str(spec.bounds[1])]
        snapshot[name] = {
            "json_encoding": spec.json_encoding,
            "bounds": bounds,
            "pattern": spec.pattern,
        }
    return snapshot
