"""
Resolver visitor: evaluates XPath AST against data and schema.

Uses (data, context_path, root_data, module) to resolve paths and
current(). Each node in the data tree is represented with an explicit
parent pointer so ".." is current = current.parent (like most XPath engines).
Returns JSON-like values; for when/must the result is coerced to bool via yang_bool.
"""

from typing import Any, Dict, List, Optional

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


class Node:
    """A node in the data tree with explicit parent. .. becomes current = current.parent."""

    __slots__ = ('data', 'parent')

    def __init__(self, data: Any, parent: Optional['Node'] = None):
        self.data = data
        self.parent = parent


def _node_set_values(val: Any) -> List[Any]:
    """Extract comparable values from a path result (node-set or scalar)."""
    if isinstance(val, list):
        if not val or isinstance(val[0], Node):
            return [n.data for n in val]
        return val
    return [val] if val is not None else []


def _compare_equal(left: Any, right: Any) -> bool:
    """XPath equality: node-set vs scalar → true if any node matches; type coercion."""
    left_vals = _node_set_values(left)
    right_vals = _node_set_values(right)
    if not left_vals or not right_vals:
        return not left_vals and not right_vals
    for lv in left_vals:
        for rv in right_vals:
            if lv is None and rv is None:
                return True
            if lv is None or rv is None:
                continue
            if isinstance(lv, bool) or isinstance(rv, bool):
                if yang_bool(lv) == yang_bool(rv):
                    return True
            elif isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                if float(lv) == float(rv):
                    return True
            elif str(lv).strip() == str(rv).strip():
                return True
    return False


def _compare_less(left: Any, right: Any) -> bool:
    """XPath: node-set op scalar/node-set → true if any pair satisfies <."""
    left_vals = _node_set_values(left)
    right_vals = _node_set_values(right)
    for lv in left_vals:
        for rv in right_vals:
            try:
                if float(lv) < float(rv):
                    return True
            except (TypeError, ValueError):
                if str(lv) < str(rv):
                    return True
    return False


def _compare_greater(left: Any, right: Any) -> bool:
    """XPath: node-set op scalar/node-set → true if any pair satisfies >."""
    left_vals = _node_set_values(left)
    right_vals = _node_set_values(right)
    for lv in left_vals:
        for rv in right_vals:
            try:
                if float(lv) > float(rv):
                    return True
            except (TypeError, ValueError):
                if str(lv) > str(rv):
                    return True
    return False


def _bin_or(self: 'ResolverVisitor', node: BinaryOpNode) -> Any:
    if yang_bool(node.left.accept(self)):
        return True
    return yang_bool(node.right.accept(self))


def _bin_and(self: 'ResolverVisitor', node: BinaryOpNode) -> Any:
    if not yang_bool(node.left.accept(self)):
        return False
    return yang_bool(node.right.accept(self))


def _bin_compare(
    self: 'ResolverVisitor', node: BinaryOpNode, compare: Any
) -> Any:
    left = node.left.accept(self)
    right = node.right.accept(self)
    return compare(left, right)


def _bin_plus(self: 'ResolverVisitor', node: BinaryOpNode) -> Any:
    """XPath + is numeric addition only; string concatenation uses concat()."""
    left = node.left.accept(self)
    right = node.right.accept(self)
    lv = _node_set_values(left)
    rv = _node_set_values(right)
    l = lv[0] if lv else None
    r = rv[0] if rv else None
    try:
        return float(l) + float(r)
    except (TypeError, ValueError):
        return float('nan')


def _bin_minus(self: 'ResolverVisitor', node: BinaryOpNode) -> Any:
    """XPath - is numeric subtraction; node-sets use first value."""
    left = node.left.accept(self)
    right = node.right.accept(self)
    lv = _node_set_values(left)
    rv = _node_set_values(right)
    l = lv[0] if lv else None
    r = rv[0] if rv else None
    try:
        return float(l) - float(r)
    except (TypeError, ValueError):
        return float('nan')


_BINARY_OP_HANDLERS = {
    'or': _bin_or,
    'and': _bin_and,
    '=': lambda self, n: _bin_compare(self, n, _compare_equal),
    '!=': lambda self, n: _bin_compare(self, n, lambda l, r: not _compare_equal(l, r)),
    '<': lambda self, n: _bin_compare(self, n, _compare_less),
    '>': lambda self, n: _bin_compare(self, n, _compare_greater),
    '<=': lambda self, n: _bin_compare(
        self, n, lambda l, r: _compare_equal(l, r) or _compare_less(l, r)
    ),
    '>=': lambda self, n: _bin_compare(
        self, n, lambda l, r: _compare_equal(l, r) or _compare_greater(l, r)
    ),
    '+': _bin_plus,
    '-': _bin_minus,
}


def _fn_current(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    return self._current_value()


def _fn_not(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    if len(node.args) != 1:
        return None
    return not yang_bool(node.args[0].accept(self))


def _fn_count(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    """XPath count(node-set) = number of nodes. Only node-sets; scalars count as 1."""
    if len(node.args) != 1:
        return 0
    val = node.args[0].accept(self)
    if isinstance(val, list) and (not val or isinstance(val[0], Node)):
        return len(val)
    return 1


def _fn_string(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    if len(node.args) != 1:
        return ""
    v = node.args[0].accept(self)
    vals = _node_set_values(v)
    v = vals[0] if vals else None
    return "" if v is None else str(v)


def _fn_number(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    if len(node.args) != 1:
        return float('nan')
    v = node.args[0].accept(self)
    vals = _node_set_values(v)
    v = vals[0] if vals else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return float('nan')


def _fn_bool(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    if len(node.args) != 1:
        return False
    return yang_bool(node.args[0].accept(self))


def _fn_string_length(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    if len(node.args) != 1:
        return 0
    v = node.args[0].accept(self)
    vals = _node_set_values(v)
    v = vals[0] if vals else None
    return 0 if v is None else len(str(v))


def _fn_translate(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    """XPath translate(source, from_chars, to_chars): replace/delete chars in source."""
    if len(node.args) != 3:
        return ""
    s = node.args[0].accept(self)
    sv = _node_set_values(s)
    source = str(sv[0] if sv else None or "")
    from_chars = str(node.args[1].accept(self) or "").strip("'\"")
    to_chars = str(node.args[2].accept(self) or "").strip("'\"")
    if not from_chars:
        return source
    if not to_chars:
        return "".join(c for c in source if c not in from_chars)
    trans = {}
    to_len = len(to_chars)
    for i, c in enumerate(from_chars):
        trans[ord(c)] = to_chars[i] if i < to_len else None
    return source.translate(trans)


def _fn_concat(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    """XPath concat(str1, str2, ...): string concatenation (use this instead of + for strings)."""
    parts = []
    for arg in node.args:
        v = arg.accept(self)
        vals = _node_set_values(v)
        parts.append("" if not vals else str(vals[0]))
    return "".join(parts)


def _build_path_string_from_ast(node: Any) -> str:
    """Build path string from xpath_new AST for deref() (current(), path, or path/path)."""
    if isinstance(node, PathNode):
        steps = [seg.step for seg in node.segments]
        s = "/".join(steps)
        return ("/" + s) if node.is_absolute else s
    if isinstance(node, FunctionCallNode):
        if node.name == 'current' and len(node.args) == 0:
            return 'current()'
        return f"{node.name}()"
    if isinstance(node, BinaryOpNode) and node.operator == '/':
        left = _build_path_string_from_ast(node.left)
        right = _build_path_string_from_ast(node.right)
        if left and right:
            return f"{left}/{right}"
        return left or right or ""
    return str(getattr(node, 'value', node))


def _fn_deref(self: 'ResolverVisitor', node: FunctionCallNode) -> Any:
    """deref(path): resolve leafref; uses SchemaLeafrefResolver when deref_evaluator is set."""
    if not node.args or self.deref_evaluator is None:
        return None
    arg = node.args[0]
    path_str = _build_path_string_from_ast(arg)
    from ..xpath.context import Context
    ctx_path = self.original_context_path or self.context_path
    data_at_path = self._get_at_path(self.root_data, ctx_path) if ctx_path else self.root_data
    if data_at_path is None:
        data_at_path = self.original_data if self.original_data is not None else self.root_data
    context = Context(
        data=data_at_path,
        context_path=list(ctx_path) if ctx_path else [],
        original_context_path=list(self.original_context_path) if self.original_context_path else [],
        original_data=self.original_data,
        root_data=self.root_data,
    )
    try:
        return self.deref_evaluator.evaluate_deref(path_str, context)
    except Exception:  # pylint: disable=broad-except
        return None


_FUNCTION_HANDLERS = {
    'current': _fn_current,
    'concat': _fn_concat,
    'deref': _fn_deref,
    'true': lambda self, node: True,
    'false': lambda self, node: False,
    'not': _fn_not,
    'count': _fn_count,
    'string': _fn_string,
    'number': _fn_number,
    'bool': _fn_bool,
    'string-length': _fn_string_length,
    'translate': _fn_translate,
}


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
        initial_node: Optional[Node] = None,
        current_from_outer: bool = False,
        deref_evaluator: Optional[Any] = None,
    ) -> None:
        self.data = data
        self.context_path = list(context_path)
        self.root_data = root_data if root_data is not None else data
        self.module = module
        self.original_context_path = (
            list(original_context_path) if original_context_path is not None
            else self.context_path
        )
        self.original_data = original_data if original_data is not None else data
        self.initial_node = initial_node
        self.current_from_outer = current_from_outer
        self.deref_evaluator = deref_evaluator
        self._current_cache: dict = {}
        self._schema_default_cache: Dict[tuple, Optional[Any]] = {}

    def resolve(self, node: Any) -> Any:
        """Resolve an AST node to a value. Entry point."""
        return node.accept(self)

    def _build_initial_node(self, root_data: Any, path: List[Any]) -> Node:
        """Build a Node at path from root; parent is always the actual parent (list or container)."""
        if not path:
            return Node(root_data, None)
        cur_data = root_data
        cur_node: Optional[Node] = Node(root_data, None)
        for part in path:
            if cur_data is None:
                return Node(None, cur_node)
            if isinstance(cur_data, dict) and part in cur_data:
                cur_data = cur_data[part]
            elif isinstance(cur_data, list) and isinstance(part, int) and 0 <= part < len(cur_data):
                cur_data = cur_data[part]
            else:
                cur_data = None
            cur_node = Node(cur_data, cur_node)
        # Leaf-list value: path ends with list index and value is scalar. For .. we need the
        # container (sibling of the list), not the list, so ../min_value etc. resolve.
        if (
            len(path) >= 2
            and isinstance(path[-1], int)
            and cur_data is not None
            and not isinstance(cur_data, (dict, list))
            and cur_node.parent is not None
            and cur_node.parent.parent is not None
        ):
            cur_node = Node(cur_data, cur_node.parent.parent)
        return cur_node

    def visit_path_node(self, node: PathNode) -> Any:
        """Resolve path; returns node-set (list of Node). .. = actual parent; no collapsing."""
        if self.initial_node is not None:
            nodes: List[Node] = [self.initial_node]
            path: List[Any] = []  # optional; not tracked for initial_node
        elif node.is_absolute:
            nodes = [Node(self.root_data, None)]
            path = []
        else:
            if not self.context_path:
                nodes = [Node(self.data, None)]
            else:
                nodes = [self._build_initial_node(self.root_data, self.context_path)]
            path = list(self.context_path)
        for seg in node.segments:
            if seg.step == '..':
                nodes = [n.parent for n in nodes if n.parent is not None]
                if path:
                    path = path[:-1]
            elif seg.step == '.':
                pass
            else:
                new_nodes: List[Node] = []
                for n in nodes:
                    parent_data = n.data
                    raw = self._step_down_from_node(n, seg.step, seg.predicate)
                    if raw is None and isinstance(parent_data, dict) and seg.step in parent_data and parent_data[seg.step] is None:
                        raw = True
                    if raw is None and self.module and len(nodes) == 1:
                        full_path = path + [seg.step]
                        default_val = self._get_schema_default_at_path(full_path)
                        if default_val is not None:
                            raw = default_val
                    if raw is None:
                        continue
                    if isinstance(raw, list):
                        for item in raw:
                            new_nodes.append(Node(item, n))
                    else:
                        new_nodes.append(Node(raw, n))
                nodes = new_nodes
                if path is not None:
                    path = (path + [seg.step]) if len(nodes) == 1 else None
        return nodes

    def _get_schema_default_at_path(self, path_parts: List[Any]) -> Optional[Any]:
        """Return schema default for the leaf at path_parts, or None. Drops list indices."""
        if not self.module or not path_parts:
            return None
        # Early exit: path with list index is not a leaf schema path
        if any(isinstance(p, int) for p in path_parts):
            return None
        schema_path = [p for p in path_parts if isinstance(p, str)]
        if not schema_path:
            return None
        cache_key = tuple(schema_path)
        if cache_key in self._schema_default_cache:
            return self._schema_default_cache[cache_key]
        statements = getattr(self.module, 'statements', [])
        for i, part in enumerate(schema_path):
            found = None
            for stmt in statements:
                if getattr(stmt, 'name', None) == part:
                    found = stmt
                    break
            if found is None:
                self._schema_default_cache[cache_key] = None
                return None
            if i == len(schema_path) - 1:
                # Reached the target node; only leaves have default
                default = getattr(found, 'default', None)
                self._schema_default_cache[cache_key] = default
                return default
            if hasattr(found, 'statements') and found.statements:
                statements = found.statements
            elif hasattr(found, 'cases'):
                statements = []
                for case in getattr(found, 'cases', []):
                    statements.extend(getattr(case, 'statements', []))
            else:
                self._schema_default_cache[cache_key] = None
                return None
        self._schema_default_cache[cache_key] = None
        return None

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

    def _step_down_from_node(
        self,
        n: Node,
        step: str,
        predicate: Optional[Any],
    ) -> Any:
        """Step from node by key; returns value or list of values (node-set). Predicate context = list item as Node."""
        current = n.data
        if isinstance(current, dict) and step in current:
            val = current[step]
            if isinstance(val, list) and predicate is not None:
                return self._filter_list(val, predicate, n)
            # Type empty / presence: key present with value None is truthy (node exists)
            if val is None:
                return True
            return val
        if isinstance(current, list):
            if predicate is not None:
                filtered = self._filter_list(current, predicate, n)
                return [item.get(step) if isinstance(item, dict) else item for item in filtered]
            return [item.get(step) if isinstance(item, dict) else item for item in current]
        return None

    def _filter_list(
        self,
        items: List[Any],
        predicate: Any,
        parent_node: Node,
        key: Optional[str] = None,
    ) -> List[Any]:
        """Filter list items by predicate. Context node for predicate = each list item as Node(parent=parent_node)."""
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
        old_initial = self.initial_node
        old_current_outer = self.current_from_outer
        for item in items:
            ctx_node = Node(item if isinstance(item, dict) else item, parent_node)
            self.initial_node = ctx_node
            self.current_from_outer = True
            if yang_bool(predicate.accept(self)):
                out.append(item)
        self.initial_node = old_initial
        self.current_from_outer = old_current_outer
        return out

    def visit_literal(self, node: LiteralNode) -> Any:
        return node.value

    def visit_binary_op(self, node: BinaryOpNode) -> Any:
        handler = _BINARY_OP_HANDLERS.get(node.operator)
        if handler is None:
            return None
        return handler(self, node)

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
        handler = _FUNCTION_HANDLERS.get(node.name.lower())
        if handler is None:
            return None
        return handler(self, node)

    def _current_value(self) -> Any:
        """Value at original context path (current() semantics). In predicates, current() is the outer context."""
        if self.current_from_outer and self.original_context_path:
            cur = self._get_at_path(self.original_data, self.original_context_path)
            return cur if cur is not None else ""
        if self.initial_node is not None:
            return self.initial_node.data if self.initial_node.data is not None else ""
        path = self.original_context_path
        if not path:
            return self.original_data if self.original_data is not None else ""
        cur = self._get_at_path(self.root_data, path)
        return cur if cur is not None else ""
