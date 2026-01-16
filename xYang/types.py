"""
YANG type system implementation.
"""

import re
from typing import Any, Optional, Dict, List, Callable
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class TypeConstraint:
    """Type constraint."""
    pattern: Optional[str] = None
    length: Optional[str] = None
    range: Optional[str] = None
    fraction_digits: Optional[int] = None
    enums: List[str] = None

    def __post_init__(self):
        if self.enums is None:
            self.enums = []


class TypeSystem:
    """YANG type system for validation."""

    def __init__(self):
        self.typedefs: Dict[str, 'TypeDefinition'] = {}
        self._pattern_cache: Dict[str, re.Pattern] = {}  # Cache compiled regex patterns
        self._validators: Dict[str, Callable] = {}
        self._init_builtin_types()
        # Register built-in validators after all methods are defined
        # This is done lazily on first use to avoid forward reference issues
        if not self._validators:
            self._register_builtin_validators()

    def _init_builtin_types(self):
        """Initialize built-in YANG types."""
        # Register built-in type validators
        # Note: These are registered after class definition to avoid forward reference issues
        pass
    
    def _register_builtin_validators(self):
        """Register built-in type validators (called after all methods are defined)."""
        self.register_type('string', self._validate_string)
        self.register_type('int32', self._validate_int32)
        self.register_type('uint8', self._validate_uint8)
        self.register_type('boolean', self._validate_boolean)
        self.register_type('decimal64', self._validate_decimal64)
    
    def register_type(self, name: str, validator: Callable):
        """
        Register a type validator.
        
        Args:
            name: Type name
            validator: Validator function that takes (value, constraints) and returns (bool, Optional[str])
        """
        self._validators[name] = validator

    @lru_cache(maxsize=128)
    def _get_compiled_pattern(self, pattern: str) -> Optional[re.Pattern]:
        """Get or compile a regex pattern with caching."""
        try:
            return re.compile(pattern)
        except re.error:
            return None

    def register_typedef(self, name: str, base_type: str, constraints: Optional[TypeConstraint] = None):
        """Register a typedef."""
        self.typedefs[name] = TypeDefinition(name, base_type, constraints)

    def validate(self, value: Any, type_name: str, constraints: Optional[TypeConstraint] = None) -> tuple[bool, Optional[str]]:
        """
        Validate a value against a type.

        Returns:
            (is_valid, error_message)
        """
        # Check if it's a typedef
        if type_name in self.typedefs:
            typedef = self.typedefs[type_name]
            return self.validate(value, typedef.base_type, typedef.constraints)

        # Use registered validator if available
        if type_name in self._validators:
            return self._validators[type_name](value, constraints)
        
        # Unknown type - fail closed instead of assuming valid
        return False, f"Unknown type: {type_name}"

    def _validate_string(self, value: Any, constraints: Optional[TypeConstraint]) -> tuple[bool, Optional[str]]:
        """Validate string value."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"

        if constraints:
            # Check pattern (use cached compiled regex)
            if constraints.pattern:
                pattern = constraints.pattern.strip("'\"")
                compiled = self._get_compiled_pattern(pattern)
                if compiled and not compiled.match(value):
                    return False, f"String does not match pattern: {pattern}"

            # Check length
            if constraints.length:
                length_valid, msg = self._validate_length(len(value), constraints.length)
                if not length_valid:
                    return False, msg

        return True, None

    def _validate_int32(self, value: Any, constraints: Optional[TypeConstraint]) -> tuple[bool, Optional[str]]:
        """Validate int32 value."""
        try:
            int_val = int(value)
            if int_val < -2147483648 or int_val > 2147483647:
                return False, "Value out of int32 range"

            if constraints and constraints.range:
                range_valid, msg = self._validate_range(int_val, constraints.range)
                if not range_valid:
                    return False, msg

            return True, None
        except (ValueError, TypeError):
            return False, f"Expected int32, got {type(value).__name__}"

    def _validate_uint8(self, value: Any, constraints: Optional[TypeConstraint]) -> tuple[bool, Optional[str]]:
        """Validate uint8 value."""
        try:
            int_val = int(value)
            if int_val < 0 or int_val > 255:
                return False, "Value out of uint8 range (0-255)"

            if constraints and constraints.range:
                range_valid, msg = self._validate_range(int_val, constraints.range)
                if not range_valid:
                    return False, msg

            return True, None
        except (ValueError, TypeError):
            return False, f"Expected uint8, got {type(value).__name__}"

    def _validate_boolean(self, value: Any, constraints: Optional[TypeConstraint]) -> tuple[bool, Optional[str]]:
        """Validate boolean value."""
        if isinstance(value, bool):
            return True, None
        if isinstance(value, str):
            if value.lower() in ('true', 'false'):
                return True, None
        return False, f"Expected boolean, got {type(value).__name__}"

    def _validate_decimal64(self, value: Any, constraints: Optional[TypeConstraint]) -> tuple[bool, Optional[str]]:
        """Validate decimal64 value."""
        try:
            float_val = float(value)
            if constraints and constraints.fraction_digits:
                # Check fraction digits
                str_val = str(value)
                if '.' in str_val:
                    fraction_part = str_val.split('.')[1]
                    if len(fraction_part) > constraints.fraction_digits:
                        return False, f"Too many fraction digits (max {constraints.fraction_digits})"

            return True, None
        except (ValueError, TypeError):
            return False, f"Expected decimal64, got {type(value).__name__}"

    def _validate_length(self, length: int, length_spec: str) -> tuple[bool, Optional[str]]:
        """Validate length constraint."""
        # Parse length spec like "1..64" or "min..max"
        if '..' in length_spec:
            parts = length_spec.split('..')
            if len(parts) == 2:
                min_len = parts[0].strip()
                max_len = parts[1].strip()

                min_val = 0 if min_len == 'min' else int(min_len)
                max_val = 999999 if max_len == 'max' else int(max_len)

                if length < min_val or length > max_val:
                    return False, f"Length {length} not in range {length_spec}"

        return True, None

    def _validate_range(self, value: int, range_spec: str) -> tuple[bool, Optional[str]]:
        """Validate range constraint."""
        # Parse range spec like "0..max" or "min..max"
        if '..' in range_spec:
            parts = range_spec.split('..')
            if len(parts) == 2:
                min_val_str = parts[0].strip()
                max_val_str = parts[1].strip()

                min_val = -2147483648 if min_val_str == 'min' else int(min_val_str)
                max_val = 2147483647 if max_val_str == 'max' else int(max_val_str)

                if value < min_val or value > max_val:
                    return False, f"Value {value} not in range {range_spec}"

        return True, None


@dataclass
class TypeDefinition:
    """Type definition."""
    name: str
    base_type: str
    constraints: Optional[TypeConstraint] = None
