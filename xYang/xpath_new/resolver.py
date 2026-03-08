"""
Resolver visitor: evaluates XPath AST against data and schema.

Uses (data, context_path, root_data, module) to resolve paths and
current(). Returns JSON-like values; for when/must the result is
coerced to bool via yang_bool.
"""

from typing import Any, List, Optional

from ..xpath.utils import yang_bool

from .ast import (
    PathNode,
    PathSegment,
    LiteralNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
)
from .visitor import Visitor


def _compare_equal(left: Any, right: Any) -> bool:
    """YANG/XPath equality: type coercion for bool/int/string."""
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return yang_bool(left) == yang_bool(right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return str(left).strip() == str(right).strip()


def _compare_less(left: Any, right: Any) -> bool:
    try:
        return float(left) < float(right)
    except (TypeError, ValueError):
        return str(left) < str(right)


def _compare_greater(left: Any, right: Any) -> bool:
    try:
        return float(left) > float(right)
    except (TypeError, ValueError):
        return str(left) > str(right)


class ResolverVisitor(Visitor):
    """Visitor that resolves XPath AST against data and schema."""

    def __init__(
        self,
        data: Any,
        context_path: List[Any],
        root_data: Optional[Any] = None,
        module: Any = None,
        original_context_path: Optional[List[Any]] = None,
        original_data: Optional[Any] = None,
    ):
        self.data = data
        self.context_path = list(context_path)
        self.root_data = root_data if root_data is not None else data
        self.module = module
        self.original_context_path = (
            list(original_context_path) if original_context_path is not None
            else self.context_path
        )
        self.original_data = original_data if original_data is not None else data
        self._current_cache: dict = {}

    def resolve(self, node: Any) -> Any:
        """Resolve an AST node to a value. Entry point."""
        return node.accept(self)

    def visit_path_node(self, node: PathNode) -> Any:
        """Resolve path: navigate from current or root by segments."""
        if node.is_absolute:
            current = self.root_data
            path: List[Any] = []
        else:
            current = self._get_at_path(
                self.root_data, self.context_path
            )
            path = list(self.context_path)
        for seg in node.segments:
            if seg.step == '..':
                path, current = self._go_up(path, current)
            elif seg.step == '.':
                pass
            else:
                parent = current
                current = self._step_down(current, seg.step, seg.predicate)
                if current is None and isinstance(parent, dict) and seg.step in parent and parent[seg.step] is None:
                    # Key present with value None: node exists (e.g. empty-type leaf), evaluate as present
                    current = True
                if current is None:
                    return "" if node.segments else None
                if isinstance(current, list) and len(current) == 1:
                    current = current[0]
                path = path + [seg.step]
        if isinstance(current, list):
            return current
        return current if current is not None else ""

    def _get_at_path(self, root: Any, path: List[Any]) -> Any:
        """Get value at path from root (path = list of keys/indices)."""
        cur = root
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and isinstance(part, int) and 0 <= part < len(cur):
                cur = cur[part]
            else:
                return None
        return cur

    def _go_up(self, path: List[Any], current: Any) -> tuple:
        """Go up one level; return (new_path, new_current).
        - From a list item (path ends with int), ".." stays so ../sibling reads from same node.
        - From a single-segment path (e.g. ['data']), ".." stays so ../type means current's type.
        - Otherwise pop one to get parent.
        """
        if not path:
            return [], current
        if isinstance(path[-1], int):
            return path, current
        if len(path) == 1:
            return path, current
        new_path = path[:-1]
        return new_path, self._get_at_path(self.root_data, new_path)

    def _step_down(
        self,
        current: Any,
        step: str,
        predicate: Optional[Any],
    ) -> Any:
        """Step down into current by key (and optional predicate for lists)."""
        if isinstance(current, dict) and step in current:
            val = current[step]
            if isinstance(val, list) and predicate is not None:
                return self._filter_list(val, predicate)
            return val
        if isinstance(current, list):
            if predicate is not None:
                filtered = self._filter_list(current, predicate)
                return [item.get(step) if isinstance(item, dict) else item for item in filtered]
            return [item.get(step) if isinstance(item, dict) else item for item in current]
        return None

    def _filter_list(
        self,
        items: List[Any],
        predicate: Any,
        key: Optional[str] = None,
    ) -> List[Any]:
        """Filter list items by predicate (or by key if key given)."""
        if key:
            out = []
            for item in items:
                if isinstance(item, dict) and key in item:
                    out.append(item[key])
                elif isinstance(item, dict):
                    out.append(None)
                else:
                    out.append(item)
            return out
        out = []
        for item in items:
            sub = ResolverVisitor(
                item if isinstance(item, dict) else {'value': item},
                [],
                self.root_data,
                self.module,
                original_context_path=self.original_context_path,
                original_data=self.original_data,
            )
            if yang_bool(predicate.accept(sub)):
                out.append(item)
        return out

    def visit_literal(self, node: LiteralNode) -> Any:
        return node.value

    def visit_binary_op(self, node: BinaryOpNode) -> Any:
        left = node.left.accept(self)
        if node.operator == 'or':
            if yang_bool(left):
                return True
            return yang_bool(node.right.accept(self))
        if node.operator == 'and':
            if not yang_bool(left):
                return False
            return yang_bool(node.right.accept(self))
        right = node.right.accept(self)
        if node.operator == '=':
            return _compare_equal(left, right)
        if node.operator == '!=':
            return not _compare_equal(left, right)
        if node.operator == '<':
            return _compare_less(left, right)
        if node.operator == '>':
            return _compare_greater(left, right)
        if node.operator == '<=':
            return _compare_equal(left, right) or _compare_less(left, right)
        if node.operator == '>=':
            return _compare_equal(left, right) or _compare_greater(left, right)
        if node.operator == '+':
            try:
                return float(left) + float(right)
            except (TypeError, ValueError):
                return str(left) + str(right)
        if node.operator == '-':
            try:
                return float(left) - float(right)
            except (TypeError, ValueError):
                return None
        return None

    def visit_unary_op(self, node: UnaryOpNode) -> Any:
        if node.operator == 'not':
            return not yang_bool(node.operand.accept(self))
        if node.operator == '-':
            val = node.operand.accept(self)
            try:
                return -float(val)
            except (TypeError, ValueError):
                return None
        return None

    def visit_function_call(self, node: FunctionCallNode) -> Any:
        name = node.name.lower()
        if name == 'current':
            return self._current_value()
        if name == 'true':
            return True
        if name == 'false':
            return False
        if name == 'not':
            if len(node.args) != 1:
                return None
            return not yang_bool(node.args[0].accept(self))
        if name == 'count':
            if len(node.args) != 1:
                return 0
            val = node.args[0].accept(self)
            if isinstance(val, list):
                return len(val)
            return 1 if val not in (None, "") else 0
        if name == 'string':
            if len(node.args) != 1:
                return ""
            v = node.args[0].accept(self)
            if v is None:
                return ""
            return str(v)
        if name == 'number':
            if len(node.args) != 1:
                return float('nan')
            try:
                return float(node.args[0].accept(self))
            except (TypeError, ValueError):
                return float('nan')
        return None

    def _current_value(self) -> Any:
        """Value at original context path (current() semantics)."""
        path = self.original_context_path
        if not path:
            return self.original_data if self.original_data is not None else ""
        cur = self._get_at_path(self.root_data, path)
        return cur if cur is not None else ""
