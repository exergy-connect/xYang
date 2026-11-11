"""
xYang validator: uses xpath DocumentValidator for validation.
"""

from typing import AbstractSet, Any, Dict, List, Optional, Tuple

from ..ast import YangStatementList
from ..encoding import resolve_structure_instance
from ..module import YangModule
from . import operation as _operation
from .document_validator import DocumentValidator
from .validation_error import Severity, ValidationError
from .validator_extension import ValidatorExtension


class YangValidator:
    """
    YANG data validator using DocumentValidator.

    Expects module to have must/when .ast produced by xpath parser
    (e.g. from xyang.parser.parse_yang_string / parse_yang_file).
    """

    def __init__(
        self,
        module: YangModule,
        *,
        enabled_features_by_module: Optional[Dict[str, AbstractSet[str]]] = None,
    ) -> None:
        """
        Args:
            module: Parsed host module.
            enabled_features_by_module: Module name -> enabled feature names. ``None`` enables every
                declared feature; a module missing from the mapping keeps all its features enabled.
                Same semantics as TypeScript ``YangValidator(module, { enabledFeaturesByModule })``.
        """
        self.module = module
        self._enabled_features_by_module: Optional[Dict[str, AbstractSet[str]]] = (
            {name: frozenset(feats) for name, feats in enabled_features_by_module.items()}
            if enabled_features_by_module is not None
            else None
        )
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
        native_json: bool = False,
        rpc: Optional[str] = None,
        action: Optional[str] = None,
        direction: str = "input",
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module, or against one rpc's or action's input or output.

        With ``rpc`` (an rpc name) or ``action`` (the RFC 8040 §3.5.3 data resource identifier
        of an action node, ``/module:list=key/action``) set, ``data`` is that operation's
        ``direction`` (``"input"`` or ``"output"``) instance: the RFC 8040 §3.6
        ``{"module:input": {...}}`` wrapper in RFC 7951 mode, or the bare parameter object with
        ``native_json=True``. ``context`` is server data (optional for an rpc, required for an
        action, whose parent instance must be in it). It is validated against the module first;
        if it has errors they are returned with ``document="context"`` and the operation is not
        checked. Otherwise the operation's ``must`` and ``leafref`` can reach it (RFC 7950 §6.4.1).
        An unknown rpc or action, or a bad option combination, raises ``ValueError``.

        Returns:
            (is_valid, errors, warnings) as display strings ``"<path>: <message>"``.
        """
        doc_errors = self._collect(
            data,
            leafref_severity=leafref_severity,
            native_json=native_json,
            rpc=rpc,
            action=action,
            direction=direction,
            context=context,
        )
        errors = [self._format_error(e) for e in doc_errors if e.severity == Severity.ERROR]
        warnings = [self._format_error(e) for e in doc_errors if e.severity == Severity.WARNING]
        return len(errors) == 0, errors, warnings

    def validate_detailed(
        self,
        data: Dict[str, Any],
        *,
        leafref_severity: Severity = Severity.ERROR,
        native_json: bool = False,
        rpc: Optional[str] = None,
        action: Optional[str] = None,
        direction: str = "input",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validate data and return structured issues.

        Each issue is ``{code, path, message, expression?, severity}``. ``path`` is a
        JSON Pointer into ``data`` (list and leaf-list entries by position). ``validate``
        string output is unchanged. ``rpc``, ``action``, ``direction`` and ``context`` are as in
        ``validate``; paths address the data as written, including the RFC 8040 wrapper. An issue
        about the context carries ``"document": "context"`` and a pointer into the context.
        """
        doc_errors = self._collect(
            data,
            leafref_severity=leafref_severity,
            native_json=native_json,
            rpc=rpc,
            action=action,
            direction=direction,
            context=context,
        )
        errors = [self._issue(e) for e in doc_errors if e.severity == Severity.ERROR]
        warnings = [self._issue(e) for e in doc_errors if e.severity == Severity.WARNING]
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _collect(
        self,
        data: Dict[str, Any],
        *,
        leafref_severity: Severity,
        native_json: bool = False,
        rpc: Optional[str] = None,
        action: Optional[str] = None,
        direction: str = "input",
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ValidationError]:
        _operation.check_operation_options(rpc, action, direction, context)
        if rpc is not None or action is not None:
            return self._collect_operation(
                data,
                rpc=rpc,
                action=action,
                direction=direction,
                context=context,
                leafref_severity=leafref_severity,
                native_json=native_json,
            )
        root_schema: YangStatementList = self.module
        instance: Dict[str, Any] = data
        structure_key: Optional[str] = None
        structure = resolve_structure_instance(data, self.module)
        if structure is not None:
            root_schema, instance, structure_key = structure
        errors = self._document_validator(root_schema).validate(
            instance,
            leafref_severity=leafref_severity,
            native_json=native_json,
            module=self.module,
            from_iterator=True,
        )
        if structure_key is not None:
            for err in errors:
                err.pointer = _prefix_member(structure_key, err.pointer)
                err.path = _prefix_member(structure_key, err.path)
        return errors

    def _collect_operation(
        self,
        data: Any,
        *,
        rpc: Optional[str],
        action: Optional[str],
        direction: str,
        context: Optional[Dict[str, Any]],
        leafref_severity: Severity,
        native_json: bool,
    ) -> List[ValidationError]:
        if rpc is not None:
            target = _operation.find_rpc(self.module, rpc)
        else:
            target = _operation.resolve_action(self.module, action or "")
        operation = _operation.operation_node(target.operation, _operation.find_body(target.operation, direction))
        context_issues: List[ValidationError] = []
        if context is not None:
            # RFC 7950 §6.4.1: the operation reads the server data, so it must be valid data first.
            context_issues = self._collect(context, leafref_severity=leafref_severity, native_json=native_json)
            for issue in context_issues:
                issue.document = "context"
            if any(issue.severity == Severity.ERROR for issue in context_issues):
                return context_issues
        member: Optional[str] = None
        params: Any = data
        if not native_json:
            member = _operation.wrapper_member(target.module_name, direction)
            if not isinstance(data, dict) or list(data) != [member]:
                found = ", ".join(repr(k) for k in data) if isinstance(data, dict) else type(data).__name__
                kind = "rpc" if rpc is not None else "action"
                return [
                    ValidationError(
                        path="/",
                        message=(
                            f"{kind} {direction} must be an object with the single member '{member}' "
                            f"(RFC 8040 §3.6); found {found or 'no members'}. "
                            "Pass native_json=True for the bare parameter object"
                        ),
                        code="operation-wrapper",
                        pointer="",
                    )
                ]
            params = data[member]
            if not isinstance(params, dict):
                return [
                    ValidationError(
                        path=f"/{member}",
                        message=f"{direction} must be an object",
                        code="type",
                        pointer=_prefix_member(member, ""),
                    )
                ]
        accessible, parent_copies = _operation.accessible_module(self.module, target, operation)
        errors = self._document_validator(accessible).validate_operation(
            params,
            target=target,
            operation=operation,
            parent_copies=parent_copies,
            host=self.module,
            context=context,
            leafref_severity=leafref_severity,
            native_json=native_json,
        )
        if member is not None:
            for err in errors:
                if err.document == "data":
                    err.pointer = _prefix_member(member, err.pointer)
                    err.path = _prefix_member(member, err.path)
        return context_issues + errors

    @staticmethod
    def _issue(e: ValidationError) -> Dict[str, Any]:
        issue: Dict[str, Any] = {
            "code": e.code,
            "path": e.pointer,
            "message": e.message,
        }
        if e.document != "data":
            issue["document"] = e.document
        if e.expression:
            issue["expression"] = e.expression
        issue["severity"] = e.severity.value
        return issue

    @staticmethod
    def _format_error(e: ValidationError) -> str:
        where = e.path if e.document == "data" else f"{e.document} {e.path}"
        if e.expression:
            return f"{where}: {e.message} (expression: {e.expression})"
        return f"{where}: {e.message}"


def _prefix_member(json_key: str, location: str) -> str:
    """Prefix a path or JSON Pointer with the structure member as written."""
    token = json_key.replace("~", "~0").replace("/", "~1")
    if location in ("", "/"):
        return f"/{token}"
    if location.startswith("/"):
        return f"/{token}{location}"
    return f"/{token}/{location}"
