"""
xYang - A Python library implementing a subset of YANG features.

This library provides parsing, validation, and data structure support for YANG modules,
focusing on the features used in meta-model.yang.
"""

from .parser import parse_yang_file, parse_yang_string
from .module import YangModule
from .types import TypeSystem
from .validator import YangValidator
from .xpath import XPathEvaluator

__version__ = "0.1.0"
__all__ = [
    "parse_yang_file",
    "parse_yang_string",
    "YangModule",
    "TypeSystem",
    "YangValidator",
    "XPathEvaluator",
]
