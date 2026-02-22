"""
Context object for XPath evaluation state.

The Context object holds all the state needed for XPath evaluation, including
the current data context, path, and the original context for current().
When deref() or other operations need a different context, they create a new
Context object instead of modifying the original, ensuring current() always
refers to the original must statement context.
"""

from typing import Any, List, Optional, Union
from dataclasses import dataclass

# Type alias for JSON-like values that XPath can evaluate to
# Note: This is a recursive type, so we use Any for nested structures
JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]


@dataclass(frozen=True)
class Context:
    """Context for XPath evaluation.
    
    Usage Guidelines:
    - Context should ONLY be used as a parameter type or local variable type.
    - Context should NEVER be stored as an instance member/attribute of a class.
    - When used as a parameter, Context is NEVER optional - it cannot be None.
      All methods that accept Context must require it as a non-optional parameter.
    
    This ensures that context is always explicitly passed and never accidentally
    shared or mutated across method calls.
    
    Attributes:
        data: Current data context for path navigation
        context_path: Current path in the data structure
        original_context_path: Original context path where must statement was evaluated (for current())
        original_data: Original data where must statement was evaluated (for current())
        root_data: Root data for absolute path resolution
    """
    data: JsonValue
    context_path: List[str]
    original_context_path: List[str]
    original_data: JsonValue
    root_data: JsonValue
    
    @classmethod
    def clear_current_cache(cls) -> None:
        """Clear the current() result cache."""
        cls._current_cache.clear()
    
    @classmethod
    def get_cache_size(cls) -> int:
        """Get the number of cached current() results.
        
        Returns:
            Number of cached entries
        """
        return len(cls._current_cache)
    
    def with_data(self, data: JsonValue, context_path: Optional[List[str]] = None) -> 'Context':
        """Create a new context with different data and context_path.
        
        The original_context_path and original_data are preserved from this context.
        
        Args:
            data: New data context
            context_path: New context path (defaults to empty list)
            
        Returns:
            New Context object with updated data and context_path
        """
        return Context(
            data=data,
            context_path=context_path if context_path is not None else [],
            original_context_path=self.original_context_path,
            original_data=self.original_data,
            root_data=self.root_data
        )
    
    def with_context_path(self, context_path: List[str]) -> 'Context':
        """Create a new context with different context_path.
        
        The data, original_context_path, and original_data are preserved.
        
        Args:
            context_path: New context path
            
        Returns:
            New Context object with updated context_path
        """
        return Context(
            data=self.data,
            context_path=context_path,
            original_context_path=self.original_context_path,
            original_data=self.original_data,
            root_data=self.root_data
        )
    
    def for_item(self, item: JsonValue) -> 'Context':
        """Create a new context for evaluating an item in a list/collection.
        
        Wraps non-dict items in {'value': item} so they can be accessed via path navigation.
        Creates a new context with the item as data and empty context_path.
        Preserves original_context_path and original_data for current().
        
        Args:
            item: The item to create context for (dict or any other value)
            
        Returns:
            New Context object with item as data and empty context_path
        """
        item_data = item if isinstance(item, dict) else {'value': item}
        return self.with_data(item_data, [])
    
    def current(self) -> JsonValue:
        """Get the current value from the original context path.
        
        In XPath, current() always refers to the original context node where
        the expression is being evaluated, not the current iteration context.
        
        Returns:
            The value at the original context path, or empty string if not found (XPath spec)
        """
        # Check cache first (using path and data identity as key)
        cache_key = (tuple(self.original_context_path) if self.original_context_path else (), id(self.original_data))
        if cache_key in self._current_cache:
            return self._current_cache[cache_key]
        
        # Always use original context for current()
        if self.original_context_path:
            # Navigate directly from original_data using the original_context_path
            # This avoids issues with get_path_value's context-aware navigation
            current = self.original_data
            path_to_use = list(self.original_context_path)
            
            # If the first part of the path doesn't exist in original_data, try without it
            # This handles the case where root_data is data['data-model'] but context_path includes 'data-model'
            if (path_to_use and isinstance(current, dict) and 
                isinstance(path_to_use[0], str) and path_to_use[0] not in current):
                # Try navigating from root_data instead (which might be the full data structure)
                if self.root_data is not current:
                    # Check if root_data has the first part
                    if isinstance(self.root_data, dict) and path_to_use[0] in self.root_data:
                        current = self.root_data
                    else:
                        # Remove the first part and try again
                        path_to_use = path_to_use[1:]
            
            for part in path_to_use:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
                    current = current[part]
                else:
                    # Path not found - return empty string (XPath spec for current())
                    result = ""
                    self._current_cache[cache_key] = result
                    return result
            # Return the value, or empty string if None (XPath spec for current())
            result = current if current is not None else ""
            self._current_cache[cache_key] = result
            return result
        # If no original context path, try to get value from current data
        if isinstance(self.data, (str, int, float, bool)):
            result = self.data
            self._current_cache[cache_key] = result
            return result
        # If data is a dict and we're at a leaf, try to get the value
        if isinstance(self.data, dict) and self.context_path:
            last_part = self.context_path[-1]
            if isinstance(last_part, str) and last_part in self.data:
                result = self.data[last_part]
                self._current_cache[cache_key] = result
                return result
        result = ""
        self._current_cache[cache_key] = result
        return result


# Initialize class-level cache (after class definition since it's a frozen dataclass)
Context._current_cache: dict = {}
