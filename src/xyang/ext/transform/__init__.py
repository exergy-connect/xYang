"""Evaluate model-defined, jq-style instance normalization rules.

This is a deliberately small expression language, not a complete jq interpreter.
Expressions are compiled before any data is processed and input is never mutated.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from dataclasses import dataclass
from typing import Any

from ...ast import YangExtensionInvocationStmt
from ..capabilities import ExtensionIdentity, InstanceExtensionHandler, instance_handler, register_instance_handler

_TOKEN = re.compile(r'\s*(?:("(?:[^"\\]|\\.)*")|([A-Za-z_][A-Za-z_0-9-]*)|([0-9]+)|(==|!=|[.\[\]{}():,|]))')


class ExpressionError(ValueError):
    """Malformed or unsupported normalization expression."""


class _Parser:
    def __init__(self, text: str):
        self.tokens: list[tuple[str, Any]] = []
        pos = 0
        while pos < len(text):
            if not text[pos:].strip():
                break
            match = _TOKEN.match(text, pos)
            if not match:
                raise ExpressionError(f"unsupported expression syntax at offset {pos}")
            string, word, number, symbol = match.groups()
            if string is not None:
                try:
                    self.tokens.append(("literal", json.loads(string)))
                except ValueError as exc:
                    raise ExpressionError(f"invalid string: {exc}") from exc
            elif word is not None:
                self.tokens.append(("word", word))
            elif number is not None:
                self.tokens.append(("number", int(number)))
            else:
                self.tokens.append((symbol, symbol))
            pos = match.end()
        self.i = 0

    def take(self, value: str) -> bool:
        if self.i < len(self.tokens) and (self.tokens[self.i][0] == value or self.tokens[self.i][1] == value):
            self.i += 1
            return True
        return False

    def require(self, value: str) -> None:
        if not self.take(value):
            raise ExpressionError(f"expected {value!r}")

    def parse(self):
        result = self.pipeline()
        if self.i != len(self.tokens):
            raise ExpressionError(f"unexpected token {self.tokens[self.i][1]!r}")
        return result

    def pipeline(self):
        node = self.boolean()
        while self.take("|"):
            node = ("pipe", node, self.boolean())
        return node

    def boolean(self):
        node = self.equality()
        while self.i < len(self.tokens) and self.tokens[self.i][1] in ("and", "or"):
            op = self.tokens[self.i][1]
            self.i += 1
            node = (op, node, self.equality())
        return node

    def equality(self):
        node = self.primary()
        if self.take("=="):
            return ("eq", node, self.primary())
        if self.take("!="):
            return ("ne", node, self.primary())
        return node

    def primary(self):
        if self.take("("):
            node = self.pipeline()
            self.require(")")
            return node
        if self.take("{"):
            fields = []
            if not self.take("}"):
                while True:
                    if self.i >= len(self.tokens) or self.tokens[self.i][0] not in ("word", "literal"):
                        raise ExpressionError("expected object field name")
                    key = self.tokens[self.i][1]
                    self.i += 1
                    if any(existing == key for existing, _ in fields):
                        raise ExpressionError(f"duplicate object field {key!r}")
                    self.require(":")
                    fields.append((key, self.pipeline()))
                    if self.take("}"):
                        break
                    self.require(",")
            return ("object", fields)
        if self.take("."):
            node = ("input",)
            while self.take("["):
                if self.i >= len(self.tokens) or self.tokens[self.i][0] not in ("number", "literal"):
                    raise ExpressionError("expected array index or object key")
                key = self.tokens[self.i][1]
                self.i += 1
                self.require("]")
                node = ("index", node, key)
            return node
        if self.i >= len(self.tokens):
            raise ExpressionError("expected expression")
        kind, value = self.tokens[self.i]
        self.i += 1
        if kind in ("literal", "number"):
            return ("literal", value)
        if kind != "word":
            raise ExpressionError(f"unexpected token {value!r}")
        if value in ("true", "false", "null"):
            return ("literal", {"true": True, "false": False, "null": None}[value])
        if value in ("type", "length", "to_entries"):
            return (value,)
        if value in ("contains", "split", "has"):
            self.require("(")
            arg = self.pipeline()
            self.require(")")
            return (value, arg)
        raise ExpressionError(f"unsupported function or identifier {value!r}")


@lru_cache(maxsize=512)
def _compile(expression: str):
    try:
        return _Parser(expression).parse()
    except ExpressionError as exc:
        raise ExpressionError(f"invalid normalization expression {expression!r}: {exc}") from exc


def _truth(value: Any) -> bool:
    return value is not None and value is not False


def _evaluate(expr, value):
    op = expr[0]
    if op == "input":
        return value
    if op == "literal":
        return expr[1]
    if op == "pipe":
        return _evaluate(expr[2], _evaluate(expr[1], value))
    if op == "type":
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, str):
            return "string"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        raise ExpressionError("value is not JSON data")
    if op == "object":
        return {key: _evaluate(child, value) for key, child in expr[1]}
    if op == "length":
        if isinstance(value, (str, list, dict)):
            return len(value)
        raise ExpressionError("length requires a string, array, or object")
    if op == "to_entries":
        if isinstance(value, dict):
            return [{"key": key, "value": item} for key, item in value.items()]
        if isinstance(value, list):
            return [{"key": index, "value": item} for index, item in enumerate(value)]
        raise ExpressionError("to_entries requires an array or object")
    if op == "index":
        obj, key = _evaluate(expr[1], value), expr[2]
        if isinstance(obj, list) and isinstance(key, int):
            return obj[key] if 0 <= key < len(obj) else None
        if isinstance(obj, dict) and isinstance(key, str):
            return obj.get(key)
        raise ExpressionError("index requires an array index or object key")
    if op in ("eq", "ne"):
        a, b = _evaluate(expr[1], value), _evaluate(expr[2], value)
        equal = type(a) is type(b) and a == b
        return equal if op == "eq" else not equal
    if op in ("and", "or"):
        left = _truth(_evaluate(expr[1], value))
        return (left and _truth(_evaluate(expr[2], value))) if op == "and" else (left or _truth(_evaluate(expr[2], value)))
    if op == "has":
        arg = _evaluate(expr[1], value)
        if isinstance(value, dict) and isinstance(arg, str):
            return arg in value
        if isinstance(value, list) and isinstance(arg, int) and not isinstance(arg, bool):
            return 0 <= arg < len(value)
        raise ExpressionError("has requires an object key or array index")
    if op in ("contains", "split"):
        arg = _evaluate(expr[1], value)
        if not isinstance(value, str) or not isinstance(arg, str):
            raise ExpressionError(f"{op} requires string input and argument")
        if op == "contains":
            return arg in value
        return list(value) if arg == "" else value.split(arg)
    raise ExpressionError(f"unsupported operation {op!r}")


@dataclass(frozen=True)
class _Condition:
    expression: Any


@dataclass(frozen=True)
class _Action:
    expression: Any


class _ConditionHandler(InstanceExtensionHandler):
    def normalization_clause(self, invocation):
        return _Condition(_clause_expression(invocation))


class _ActionHandler(InstanceExtensionHandler):
    def normalization_clause(self, invocation):
        return _Action(_clause_expression(invocation))


def _clause_expression(invocation):
    if invocation.argument is None or invocation.statements:
        raise ExpressionError("xt:if and xt:apply each require an expression and no body")
    return _compile(invocation.argument)


class _NormalizeHandler(InstanceExtensionHandler):
    def normalization_rule(self, invocation):
        if invocation.argument is not None:
            raise ExpressionError("xt:normalize does not take an argument")
        clauses = []
        for part in invocation.statements:
            handler = instance_handler(part)
            clauses.append(handler.normalization_clause(part) if handler else None)
        if len(clauses) != 2 or not isinstance(clauses[0], _Condition) or not isinstance(clauses[1], _Action):
            raise ExpressionError("xt:normalize requires exactly xt:if followed by xt:apply")
        return clauses[0].expression, clauses[1].expression


class _ExpandDottedKeysHandler(InstanceExtensionHandler):
    def module_option(self, invocation):
        if invocation.argument not in ("true", "false") or invocation.statements:
            raise ExpressionError("xt:expand-dotted-keys requires true or false and no body")
        return "expand_dotted_keys", invocation.argument == "true"


register_instance_handler(ExtensionIdentity("xyang-transform", "normalize"), _NormalizeHandler())
register_instance_handler(ExtensionIdentity("xyang-transform", "if"), _ConditionHandler())
register_instance_handler(ExtensionIdentity("xyang-transform", "apply"), _ActionHandler())
register_instance_handler(ExtensionIdentity("xyang-transform", "expand-dotted-keys"), _ExpandDottedKeysHandler())


class NormalizationVisitor:
    """Compile schema rules and transform values as the instance visitor reaches them."""

    def __init__(self, module):
        self._compiled: dict[int, list] = {}
        self.expand_dotted_keys = False
        seen = set()
        for statement in module.statements:
            handler = instance_handler(statement)
            option = handler.module_option(statement) if handler else None
            if option is not None:
                name, value = option
                if name in seen:
                    raise ExpressionError(f"duplicate module option {name!r}")
                seen.add(name)
                if name == "expand_dotted_keys":
                    self.expand_dotted_keys = value

    def rules(self, schema):
        marker = id(schema)
        if marker not in self._compiled:
            rules = []
            for statement in getattr(schema, "statements", ()):
                handler = instance_handler(statement)
                if handler is not None:
                    rule = handler.normalization_rule(statement)
                    if rule is not None:
                        rules.append(rule)
            self._compiled[marker] = rules
        return self._compiled[marker]

    def prepare(self, schema, children):
        """Check all rules, including rules on absent instance nodes."""
        from ...module import YangModule

        if not isinstance(schema, YangModule):
            for statement in getattr(schema, "statements", ()):
                handler = instance_handler(statement)
                if handler and handler.module_option(statement) is not None:
                    raise ExpressionError("xt:expand-dotted-keys is allowed only at module level")
        self.rules(schema)
        for child in children(schema):
            self.prepare(child, children)

    def visit(self, schema, value):
        """Return the transformed value and an optional error message."""
        for condition, expression in self.rules(schema):
            try:
                if _truth(_evaluate(condition, value)):
                    value = _evaluate(expression, value)
            except ExpressionError as exc:
                return value, str(exc)
        return value, None
