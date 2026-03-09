"""
Statement registry for extensible parsing.
"""

from typing import Dict, Callable, Optional, TYPE_CHECKING
from .parser_context import TokenStream, ParserContext

if TYPE_CHECKING:
    from .ast import YangStatement


class StatementRegistry:
    """Registry for statement parsing handlers."""
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
    
    def register(self, statement_type: str, handler: Callable):
        """Register a handler for a statement type."""
        self._handlers[statement_type] = handler
    
    def get_handler(self, statement_type: str) -> Optional[Callable]:
        """Get handler for statement type, or None if not found."""
        return self._handlers.get(statement_type)
    
    def has_handler(self, statement_type: str) -> bool:
        """Check if a handler exists for statement type."""
        return statement_type in self._handlers

