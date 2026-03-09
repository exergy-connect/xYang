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
    message     -- human- and AI-readable description of what failed
    expression  -- the failing XPath expression string, if applicable
    severity    -- error or warning (default ERROR)
    """

    path: str
    message: str
    expression: Optional[str] = None
    severity: Severity = Severity.ERROR

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
