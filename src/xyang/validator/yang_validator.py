"""
xYang validator: uses xpath DocumentValidator for validation.
"""

from typing import Any, Dict, List, Tuple

from ..module import YangModule
from .document_validator import DocumentValidator, ValidationError


class YangValidator:
    """
    YANG data validator using DocumentValidator.

    Expects module to have must/when .ast produced by xpath parser
    (e.g. from xyang.parser.parse_yang_string / parse_yang_file).
    """

    def __init__(self, module: YangModule) -> None:
        self.module = module
        self._doc_validator = DocumentValidator(module)

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module.

        Returns:
            (is_valid, errors, warnings)
        """
        doc_errors: List[ValidationError] = self._doc_validator.validate(data)
        errors = [self._format_error(e) for e in doc_errors]
        return len(errors) == 0, errors, []

    @staticmethod
    def _format_error(e: ValidationError) -> str:
        if e.expression:
            return f"{e.path}: {e.message} (expression: {e.expression})"
        return f"{e.path}: {e.message}"
