"""
YANG document validator package.

Validates data documents against a YANG schema with when, structural,
must, and type (including leafref require-instance) checks.
"""

from .validation_error import Severity, ValidationError
from .document_validator import DocumentValidator
from .validator_extension import ValidatorExtension

__all__ = [
    "DocumentValidator",
    "Severity",
    "ValidationError",
    "ValidatorExtension",
]
