"""
Core objects for xpath.

Context(current, root) - fixed for the lifetime of one expression evaluation.
Node(data, schema, parent) - variable evaluation cursor; constructed on every path step.
"""

from __future__ import annotations

from typing import Any, Optional


class Context:
    """
    Fixed for the lifetime of one expression evaluation.

    current     -- the node being validated (what current() returns).
    root        -- root Node (entry point for absolute paths).
    path_cache  -- dict for path result cache (key -> node list), or None to disable caching.
    """

    __slots__ = ("current", "root", "path_cache")

    def __init__(
        self,
        current: Node,
        root: Node,
        path_cache: dict | None = None,
    ):
        self.current = current
        self.root = root
        self.path_cache = path_cache

    def child(self, current: Node) -> Context:
        """Return a new Context with current set to the child node, retaining root and path_cache."""
        return Context(current=current, root=self.root, path_cache=self.path_cache)


class Node:
    """
    Variable evaluation cursor.

    data    -- current data value.
    schema  -- corresponding schema node (None if unknown).
    parent  -- parent Node; None at root. Enables '..' at any depth.
    """

    __slots__ = ("data", "schema", "parent")

    def __init__(self, data: Any, schema: Any, parent: Optional[Node]):
        self.data = data
        self.schema = schema
        self.parent = parent

    def step(self, data: Any, schema: Any) -> Node:
        """Return a child Node one step down, with self as parent."""
        return Node(data, schema, self)
