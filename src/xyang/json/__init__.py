"""Build YANG AST (xyang.ast, YangModule) from JSON Schema with x-yang annotations."""

from .parser import parse_json_schema

__all__ = ["parse_json_schema"]
