"""
Optional document-validator extensions (opt-in via ``enable_extension``).
"""

from __future__ import annotations

from enum import Enum


class ValidatorExtension(Enum):
    """Known extensions for :class:`~xyang.validator.DocumentValidator`."""

    ANYDATA_VALIDATION = "anydata_validation"
