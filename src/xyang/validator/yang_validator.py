"""
xYang validator: uses xpath DocumentValidator for validation.
"""

from typing import Any, Dict, List, Optional, Tuple

from ..ast import YangStatementList
from ..encoding import resolve_structure_instance
from ..module import YangModule
from .document_validator import DocumentValidator
from .validation_error import Severity, ValidationError
from .validator_extension import ValidatorExtension


class YangValidator:
    """
    YANG data validator using DocumentValidator.

    Expects module to have must/when .ast produced by xpath parser
    (e.g. from xyang.parser.parse_yang_string / parse_yang_file).
    """

    def __init__(self, module: YangModule) -> None:
        self.module = module
        self._enabled_features_by_module: Optional[Dict[str, Any]] = None
        self._extensions: List[Tuple[ValidatorExtension, Dict[str, Any]]] = []

    def enable_extension(self, extension: ValidatorExtension, /, **kwargs: Any) -> None:
        """Enable a :class:`DocumentValidator` extension (see ``ValidatorExtension``)."""
        if extension is ValidatorExtension.ANYDATA_VALIDATION:
            from ..ext.anydata_validation import parse_anydata_extension_kwargs

            parse_anydata_extension_kwargs(dict(kwargs))
        self._extensions.append((extension, dict(kwargs)))

    def _document_validator(self, root_schema: YangStatementList) -> DocumentValidator:
        dv = DocumentValidator(
            root_schema,
            enabled_features_by_module=self._enabled_features_by_module,
        )
        for extension, kwargs in self._extensions:
            dv.enable_extension(extension, **kwargs)
        return dv

    @property
    def _doc_validator(self) -> DocumentValidator:
        """Default document validator for the host module (tests, benchmarks)."""
        return self._document_validator(self.module)

    def validate(
        self,
        data: Dict[str, Any],
        *,
        leafref_severity: Severity = Severity.ERROR,
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module.

        Returns:
            (is_valid, errors, warnings)
        """
        root_schema: YangStatementList = self.module
        instance: Dict[str, Any] = data
        structure = resolve_structure_instance(data, self.module)
        if structure is not None:
            root_schema, instance = structure
        doc_errors: List[ValidationError] = self._document_validator(root_schema).validate(
            instance, leafref_severity=leafref_severity
        )
        errors = [self._format_error(e) for e in doc_errors if e.severity == Severity.ERROR]
        warnings = [self._format_error(e) for e in doc_errors if e.severity == Severity.WARNING]
        return len(errors) == 0, errors, warnings

    @staticmethod
    def _format_error(e: ValidationError) -> str:
        if e.expression:
            return f"{e.path}: {e.message} (expression: {e.expression})"
        return f"{e.path}: {e.message}"
