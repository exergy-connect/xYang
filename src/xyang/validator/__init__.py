"""
YANG document validator package.

Validates data documents against a YANG schema with when, structural,
must, and type (including leafref require-instance) checks.
"""

from .validation_error import ValidationError
from .document_validator import DocumentValidator

__all__ = [
    "DocumentValidator",
    "ValidationError",
]
