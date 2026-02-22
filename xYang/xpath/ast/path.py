"""
Path navigation nodes.
"""

from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import XPathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode


class PathSegment:
    """A single segment in a path expression.
    
    Each segment represents one step in the path (e.g., 'entities', 'fields')
    and can optionally have a predicate (e.g., [name = 'value']).
    """
    
    def __init__(self, step: str, predicate: Optional[XPathNode] = None):
        """Initialize a path segment.
        
        Args:
            step: The step name (e.g., 'entities', '..', '.')
            predicate: Optional predicate expression for this step
        """
        self.step = step
        self.predicate = predicate
    
    def __repr__(self):
        pred_str = f"[{self.predicate}]" if self.predicate else ""
        return f"{self.step}{pred_str}"


class PathNode(XPathNode):
    """Path navigation node."""

    def __init__(self, segments: List[PathSegment], is_absolute: bool = False):
        """Initialize a path node.
        
        Args:
            segments: List of path segments, each with an optional predicate
            is_absolute: True if path starts with /
        """
        self.segments = segments  # List of PathSegment objects
        self.is_absolute = is_absolute  # True if starts with /

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        # pylint: disable=protected-access
        return evaluator._evaluate_path_node(self, context)

    def __repr__(self):
        prefix = "/" if self.is_absolute else ""
        segments_str = '/'.join(repr(seg) for seg in self.segments)
        return f"Path({prefix}{segments_str})"
