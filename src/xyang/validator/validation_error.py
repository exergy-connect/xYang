"""
Validation error for YANG document validation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationError:
    """
    A single validation failure.

    path        -- XPath-like location, e.g.
                   /data-model/entities[name='foo']/fields[name='bar']/minDate
                   (this is what ``str(error)`` and ``YangValidator.validate`` print)
    pointer     -- JSON Pointer into the instance (list entries by position)
    code        -- stable error code (``range``, ``must``, ``unknown-field``, ...)
    message     -- human- and AI-readable description of what failed
    expression  -- the failing XPath expression string, if applicable
    severity    -- error or warning (default ERROR)
    document    -- which document ``pointer`` addresses: ``"data"`` (the instance) or
                   ``"context"`` (the server data given with an rpc or action)
    """

    path: str
    message: str
    expression: Optional[str] = None
    severity: Severity = Severity.ERROR
    code: str = ""
    pointer: str = ""
    document: str = "data"

    def __str__(self) -> str:
        out = f"{self.path}: {self.message}"
        extras = []
        if self.expression:
            extras.append(f"expression: {self.expression}")
        if self.severity != Severity.ERROR:
            extras.append(f"severity: {self.severity.value}")
        if extras:
            out += " (" + ", ".join(extras) + ")"
        return out
