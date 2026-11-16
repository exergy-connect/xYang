"""Opaque JSON-LD / JSON Schema annotation families, enabled by default."""
import re
from .annotation_families import FAMILIES


def is_annotation(key: str, allow_jsonld: bool = True, allow_json_schema: bool = True) -> bool:
    return any(enabled and re.fullmatch(FAMILIES[family]['pattern'], key) is not None
               for family, enabled in [('jsonld', allow_jsonld), ('json_schema', allow_json_schema)])


def annotate_schema(schema: dict, allow_jsonld: bool, allow_json_schema: bool) -> None:
    """Visit schema positions only; never rewrite opaque x-yang, defaults, or examples."""
    patterns = {FAMILIES[family]['pattern']: True for family, enabled in
                [('jsonld', allow_jsonld), ('json_schema', allow_json_schema)] if enabled}
    if not patterns:
        return
    if schema.get('type') == 'object' or 'properties' in schema:
        # An optional choice's empty branch means no model members, not no annotations.
        if schema.get('maxProperties') == 0:
            del schema['maxProperties']
            schema['properties'] = {}
            schema['additionalProperties'] = False
        schema['patternProperties'] = dict(patterns)
    for key in ('properties', '$defs'):
        for child in schema.get(key, {}).values():
            if isinstance(child, dict):
                annotate_schema(child, allow_jsonld, allow_json_schema)
    for key in ('items', 'not', 'additionalProperties'):
        child = schema.get(key)
        if isinstance(child, dict):
            annotate_schema(child, allow_jsonld, allow_json_schema)
    for key in ('oneOf', 'anyOf', 'allOf'):
        for child in schema.get(key, []):
            if isinstance(child, dict):
                annotate_schema(child, allow_jsonld, allow_json_schema)
