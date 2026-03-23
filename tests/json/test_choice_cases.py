"""
JSON schema tests for YANG choice: generated schema shape and validation.

Covers both mandatory choice (oneOf with required) and optional choice
(not { required: all_keys }). Asserts the generator emits no x-yang on the
choice node and validates payloads against the YANG module.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.ast import YangChoiceStmt
from xyang.json import generate_json_schema
from xyang.module import YangModule

_DATA_DIR = Path(__file__).resolve().parent / "data" / "choice_cases"
YANG_FILE = _DATA_DIR / "choice_cases.yang"


def _minimal_data_model(
    req_choice_container: dict | None = None,
    opt_choice_container: dict | None = None,
) -> dict:
    """Build data-model payload. Choice case leaves are direct under the container (no choice key)."""
    data: dict = {"data-model": {}}
    if req_choice_container is not None:
        data["data-model"]["req_choice_container"] = req_choice_container
    if opt_choice_container is not None:
        data["data-model"]["opt_choice_container"] = opt_choice_container
    return data


# ---- Mandatory choice: exactly one of primitive | entity (leaves under container) ----
DATA_MANDATORY_PRIMITIVE = _minimal_data_model(req_choice_container={"primitive": "string"})
DATA_MANDATORY_ENTITY = _minimal_data_model(req_choice_container={"entity": "e1"})
DATA_MANDATORY_EMPTY = _minimal_data_model(req_choice_container={})
DATA_MANDATORY_BOTH = _minimal_data_model(
    req_choice_container={"primitive": "string", "entity": "e1"}
)

# ---- Optional choice: zero or one of a | b ----
DATA_OPTIONAL_EMPTY = _minimal_data_model(opt_choice_container={})
DATA_OPTIONAL_A = _minimal_data_model(opt_choice_container={"a": "x"})
DATA_OPTIONAL_B = _minimal_data_model(opt_choice_container={"b": "y"})
DATA_OPTIONAL_BOTH = _minimal_data_model(opt_choice_container={"a": "x", "b": "y"})


@pytest.fixture
def module_from_yang():
    """Load choice-cases model from .yang."""
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture
def generated_schema(module_from_yang):
    """Generate JSON schema from the YANG module."""
    return generate_json_schema(module_from_yang)


def _get_choice_schemas(schema: dict) -> tuple[dict, dict]:
    """Return (req_container_schema, opt_container_schema) from generated root.

    Choice is hoisted into the parent container (no ``choice`` data node in YANG).
    ``oneOf`` / ``not`` sit on the same object as ``x-yang.type: container``.
    """
    dm = schema.get("properties", {}).get("data-model", {})
    props = dm.get("properties", {})
    req_container = props.get("req_choice_container", {})
    opt_container = props.get("opt_choice_container", {})
    return req_container, opt_container


def _collect_xyang_choice_schema_paths(node: Any, path: str = "$") -> list[str]:
    """
    DFS over JSON Schema dicts: paths where ``x-yang.type`` is ``choice``.

    That shape implies a named instance property for the YANG choice; hoisted
    choices must use ``oneOf`` on the parent plus ``x-yang.choice`` metadata instead.
    """
    found: list[str] = []
    if isinstance(node, dict):
        xy = node.get("x-yang")
        if isinstance(xy, dict) and xy.get("type") == "choice":
            found.append(path)
        props = node.get("properties")
        if isinstance(props, dict):
            for key, val in props.items():
                found.extend(
                    _collect_xyang_choice_schema_paths(val, f"{path}.properties.{key}")
                )
        items = node.get("items")
        if isinstance(items, dict):
            found.extend(_collect_xyang_choice_schema_paths(items, f"{path}.items"))
        for combo in ("oneOf", "anyOf", "allOf"):
            branch = node.get(combo)
            if isinstance(branch, list):
                for i, item in enumerate(branch):
                    if isinstance(item, dict):
                        found.extend(
                            _collect_xyang_choice_schema_paths(item, f"{path}.{combo}[{i}]")
                        )
        defs = node.get("$defs")
        if isinstance(defs, dict):
            for dname, dval in defs.items():
                if isinstance(dval, dict):
                    found.extend(
                        _collect_xyang_choice_schema_paths(dval, f"{path}.$defs.{dname}")
                    )
    return found


def _iter_json_schema_property_keys(node: Any) -> Iterator[str]:
    """Yield every key that appears under a JSON Schema ``properties`` object (any depth)."""
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        yield from props.keys()
        for val in props.values():
            yield from _iter_json_schema_property_keys(val)
    items = node.get("items")
    if isinstance(items, dict):
        yield from _iter_json_schema_property_keys(items)
    for combo in ("oneOf", "anyOf", "allOf"):
        branch = node.get(combo)
        if isinstance(branch, list):
            for item in branch:
                yield from _iter_json_schema_property_keys(item)
    defs = node.get("$defs")
    if isinstance(defs, dict):
        for dval in defs.values():
            yield from _iter_json_schema_property_keys(dval)


def _yang_choice_statement_names(module: YangModule) -> set[str]:
    """All ``choice`` statement names in the module (any depth)."""
    names: set[str] = set()

    def visit(stmts: list[Any]) -> None:
        for s in stmts:
            if isinstance(s, YangChoiceStmt):
                names.add(s.name)
            children = getattr(s, "statements", None) or []
            if children:
                visit(children)

    visit(getattr(module, "statements", []) or [])
    return names


def test_yang_choices_are_not_json_schema_property_nodes(
    module_from_yang, generated_schema
):
    """Hoisted choices: no ``x-yang.type: choice`` subtree and no property named like the YANG choice."""
    xyang_choice_paths = _collect_xyang_choice_schema_paths(generated_schema)
    assert not xyang_choice_paths, (
        "YANG choice must not be emitted as a JSON Schema node with x-yang.type "
        f"'choice' (implies a bogus instance key). Found: {xyang_choice_paths}"
    )

    choice_names = _yang_choice_statement_names(module_from_yang)
    prop_keys = set(_iter_json_schema_property_keys(generated_schema))
    clash = choice_names & prop_keys
    assert not clash, (
        "YANG choice statement names must not appear as JSON Schema property keys "
        f"(choices are not data nodes). Clash: {sorted(clash)}"
    )


# ---- Generated schema structure (choice hoisted: oneOf only, no merged properties) ----
def test_choice_mandatory_schema_has_one_of_on_container(generated_schema):
    """Mandatory choice: oneOf on parent container; each branch is self-contained."""
    req, _ = _get_choice_schemas(generated_schema)
    assert "oneOf" in req, "Mandatory choice must have oneOf on hoisted container"
    assert "properties" not in req or not req["properties"]
    one_of = req["oneOf"]
    assert len(one_of) == 2
    keys_seen = set()
    for br in one_of:
        assert br.get("type") == "object"
        assert br.get("additionalProperties") is False
        assert set(br["required"]) == set(br["properties"])
        keys_seen |= set(br["properties"])
    assert keys_seen == {"primitive", "entity"}
    assert "req_choice" not in req.get("properties", {})


def test_choice_optional_schema_has_one_of_with_empty_branch(generated_schema):
    """Optional choice: oneOf with empty object branch, then one branch per case."""
    _, opt = _get_choice_schemas(generated_schema)
    assert "not" not in opt
    assert "properties" not in opt or not opt["properties"]
    branches = opt["oneOf"]
    assert len(branches) == 3
    assert branches[0] == {"type": "object", "maxProperties": 0}
    keys_seen = set()
    for br in branches[1:]:
        assert br.get("type") == "object"
        assert br.get("additionalProperties") is False
        assert set(br["required"]) == set(br["properties"])
        keys_seen |= set(br["properties"])
    assert keys_seen == {"a", "b"}


# ---- Validation: mandatory choice ----
def test_mandatory_choice_primitive_valid(module_from_yang):
    """Mandatory choice with only primitive is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_PRIMITIVE)
    assert valid, f"Expected valid. Errors: {errors}"


def test_mandatory_choice_entity_valid(module_from_yang):
    """Mandatory choice with only entity is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_ENTITY)
    assert valid, f"Expected valid. Errors: {errors}"


def test_mandatory_choice_empty_invalid(module_from_yang):
    """Mandatory choice with empty object is invalid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_EMPTY)
    assert not valid, "Expected invalid when no case selected"
    assert len(errors) > 0


def test_mandatory_choice_both_invalid(module_from_yang):
    """Mandatory choice with both primitive and entity is invalid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_BOTH)
    assert not valid, "Expected invalid when both cases present"
    assert len(errors) > 0


# ---- Validation: optional choice ----
def test_optional_choice_empty_valid(module_from_yang):
    """Optional choice with empty object is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_EMPTY)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_a_valid(module_from_yang):
    """Optional choice with only a is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_A)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_b_valid(module_from_yang):
    """Optional choice with only b is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_B)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_both_invalid(module_from_yang):
    """Optional choice with both a and b is invalid (not required forbids both)."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_BOTH)
    assert not valid, "Expected invalid when both cases present"
    assert len(errors) > 0
