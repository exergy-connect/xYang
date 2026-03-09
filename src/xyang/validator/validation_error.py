"""
Validation error for YANG document validation.
"""

from dataclasses import dataclass


@dataclass
class ValidationError:
    """
    A single validation failure.

    path        -- XPath-like location, e.g.
                   /data-model/entities[name='foo']/fields[name='bar']/minDate
    message     -- human- and AI-readable description of what failed
    expression  -- the failing XPath expression string, if applicable
    """

    path: str
    message: str
    expression: str = ""

    def __str__(self) -> str:
        if self.expression:
            return f"{self.path}: {self.message} (expression: {self.expression})"
        return f"{self.path}: {self.message}"
