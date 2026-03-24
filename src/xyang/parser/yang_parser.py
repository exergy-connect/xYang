"""
YANG parser implementation (refactored).

Parses YANG module files and builds an in-memory representation.
"""

import logging
from pathlib import Path
from typing import Optional

from ..errors import YangCircularUsesError
from ..module import YangModule
from ..refine_expand import (
    apply_refines_by_path,
    apply_refines_list_cardinality,
    copy_yang_statement,
    uses_refine_fingerprint,
)
from .tokenizer import YangTokenizer
from .parser_context import ParserContext
from .statement_registry import StatementRegistry
from .statement_parsers import StatementParsers
from ..ast import YangChoiceStmt, YangLeafListStmt, YangListStmt, YangUsesStmt

logger = logging.getLogger(__name__)


class YangParser:
    """Parser for YANG modules."""

    def __init__(self, *, expand_uses: bool = True):
        """
        Args:
            expand_uses: If True (default), expand uses and refine statements after
                parsing so that grouping content is inlined. If False, uses/refine
                statements are left as-is in the AST.
        """
        self.tokenizer = YangTokenizer()
        self.registry = StatementRegistry()
        self.parsers = StatementParsers(self.registry)
        self.expand_uses = expand_uses
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all statement handlers."""
        # Module-level statements
        self.registry.register('module', self.parsers.parse_module)
        self.registry.register('module:yang-version', self.parsers.parse_yang_version)
        self.registry.register('module:namespace', self.parsers.parse_namespace)
        self.registry.register('module:prefix', self.parsers.parse_prefix)
        self.registry.register('module:organization', self.parsers.parse_organization)
        self.registry.register('module:contact', self.parsers.parse_contact)
        self.registry.register('module:description', self.parsers.parse_description)
        self.registry.register('module:revision', self.parsers.parse_revision)
        self.registry.register('module:typedef', self.parsers.parse_typedef)
        self.registry.register('module:grouping', self.parsers.parse_grouping)
        self.registry.register('module:container', self.parsers.parse_container)
        self.registry.register('module:list', self.parsers.parse_list)
        self.registry.register('module:leaf', self.parsers.parse_leaf)
        self.registry.register('module:leaf-list', self.parsers.parse_leaf_list)
        
        # Container body statements
        self.registry.register('container:description', self.parsers.parse_description)
        self.registry.register('container:presence', self.parsers.parse_presence)
        self.registry.register('container:when', self.parsers.parse_when)
        self.registry.register('container:must', self.parsers.parse_must)
        self.registry.register('container:leaf', self.parsers.parse_leaf)
        self.registry.register('container:container', self.parsers.parse_container)
        self.registry.register('container:list', self.parsers.parse_list)
        self.registry.register('container:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('container:uses', self.parsers.parse_uses)
        self.registry.register('container:choice', self.parsers.parse_choice)
        
        # List body statements
        self.registry.register('list:key', self.parsers.parse_list_key)
        self.registry.register('list:min-elements', self.parsers.parse_min_elements)
        self.registry.register('list:max-elements', self.parsers.parse_max_elements)
        self.registry.register('list:description', self.parsers.parse_description)
        self.registry.register('list:when', self.parsers.parse_when)
        self.registry.register('list:leaf', self.parsers.parse_leaf)
        self.registry.register('list:container', self.parsers.parse_container)
        self.registry.register('list:list', self.parsers.parse_list)
        self.registry.register('list:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('list:must', self.parsers.parse_must)
        self.registry.register('list:uses', self.parsers.parse_uses)
        self.registry.register('list:choice', self.parsers.parse_choice)
        
        # Leaf body statements
        self.registry.register('leaf:type', self.parsers.parse_type)
        self.registry.register('leaf:mandatory', self.parsers.parse_leaf_mandatory)
        self.registry.register('leaf:default', self.parsers.parse_leaf_default)
        self.registry.register('leaf:description', self.parsers.parse_description)
        self.registry.register('leaf:must', self.parsers.parse_must)
        self.registry.register('leaf:when', self.parsers.parse_when)
        
        # Leaf-list body statements
        self.registry.register('leaf-list:type', self.parsers.parse_type)
        self.registry.register('leaf-list:min-elements', self.parsers.parse_min_elements)
        self.registry.register('leaf-list:max-elements', self.parsers.parse_max_elements)
        self.registry.register('leaf-list:description', self.parsers.parse_description)
        self.registry.register('leaf-list:must', self.parsers.parse_must)
        
        # Typedef body statements
        self.registry.register('typedef:type', self.parsers.parse_type)
        self.registry.register('typedef:description', self.parsers.parse_description)
        
        # Grouping body statements
        self.registry.register('grouping:description', self.parsers.parse_description)
        self.registry.register('grouping:choice', self.parsers.parse_choice)
        
        # Uses body statements
        self.registry.register('uses:refine', self.parsers.parse_refine)
        self.registry.register('uses:description', self.parsers.parse_description)
        
        # Refine body statements
        self.registry.register('refine:must', self.parsers.parse_must)
        self.registry.register('refine:description', self.parsers.parse_description)
        self.registry.register('refine:min-elements', self.parsers.parse_min_elements)
        self.registry.register('refine:max-elements', self.parsers.parse_max_elements)
        
        # Type constraint statements
        self.registry.register('type:type', self.parsers.parse_type)  # For union types
        self.registry.register('type:pattern', self.parsers.parse_type_pattern)
        self.registry.register('type:length', self.parsers.parse_type_length)
        self.registry.register('type:range', self.parsers.parse_type_range)
        self.registry.register('type:fraction-digits', self.parsers.parse_type_fraction_digits)
        self.registry.register('type:enum', self.parsers.parse_type_enum)
        self.registry.register('type:path', self.parsers.parse_type_path)
        self.registry.register('type:require-instance', self.parsers.parse_type_require_instance)
        
        # Choice body statements
        self.registry.register('choice:mandatory', self.parsers.parse_choice_mandatory)
        self.registry.register('choice:description', self.parsers.parse_description)
        self.registry.register('choice:case', self.parsers.parse_case)
        
        # Case body statements
        self.registry.register('case:description', self.parsers.parse_description)
    
    def parse_file(self, file_path: Path) -> YangModule:
        """Parse a YANG file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_string(content, filename=str(file_path))
    
    def parse_string(self, content: str, filename: Optional[str] = None) -> YangModule:
        """
        Parse YANG content from a string.
        
        Args:
            content: YANG file content
            filename: Optional filename for error reporting
            
        Returns:
            Parsed YangModule
        """
        # Create fresh module
        module = YangModule()
        
        # Tokenize
        tokens = self.tokenizer.tokenize(content, filename)
        
        # Check for module statement
        if not tokens.has_more() or tokens.peek() != 'module':
            raise tokens._make_error("Expected 'module' statement at start of file")
        
        # Create context (module is the root statement list)
        context = ParserContext(module=module, current_parent=module)
        
        # Parse module
        self.parsers.parse_module(tokens, context)

        # Expand uses and refine statements if enabled (default)
        if self.expand_uses:
            self._expand_all_uses(module)

        return module
    
    def _expand_all_uses(self, module: YangModule) -> None:
        """Expand all uses statements in the module after parsing is complete.
        
        This recursively finds all YangUsesStmt nodes and replaces them with
        the expanded statements from their groupings.
        """
        # Expand uses statements in module-level statements
        module.statements = self._expand_uses_in_statements(module.statements, module, ())
        
        # Expand uses statements in groupings (for nested uses)
        for grouping_name, grouping in module.groupings.items():
            grouping.statements = self._expand_uses_in_statements(grouping.statements, module, ())
    
    def _expand_uses_in_statements(
        self,
        statements,
        module: YangModule,
        expanding_chain: tuple[tuple[str, tuple], ...],
    ):
        """Recursively expand uses statements in a list of statements.

        ``expanding_chain`` is the stack of ``(grouping_name, refine_fingerprint)``
        for each ``uses`` being expanded; the same grouping may appear twice if
        refine fingerprints differ. A true cycle repeats the same link.
        """
        expanded = []
        for stmt in statements:
            if isinstance(stmt, YangUsesStmt):
                gname = stmt.grouping_name
                grouping = module.get_grouping(gname)
                if grouping:
                    link = (gname, uses_refine_fingerprint(stmt.refines))
                    if link in expanding_chain:
                        raise YangCircularUsesError(expanding_chain, link)
                    inner_chain = expanding_chain + (link,)
                    body_copies = [copy_yang_statement(s) for s in grouping.statements]
                    apply_refines_list_cardinality(body_copies, stmt.refines)
                    expanded_grouping_statements = self._expand_uses_in_statements(
                        body_copies, module, inner_chain
                    )
                    apply_refines_by_path(expanded_grouping_statements, stmt.refines)
                    expanded.extend(expanded_grouping_statements)
                else:
                    logger.warning(
                        "Grouping '%s' not found when expanding uses statement", gname
                    )
            elif isinstance(stmt, YangChoiceStmt):
                for case in stmt.cases:
                    case.statements = self._expand_uses_in_statements(
                        case.statements, module, expanding_chain
                    )
                expanded.append(stmt)
            elif isinstance(stmt, (YangListStmt, YangLeafListStmt)) and getattr(
                stmt, "max_elements", None
            ) == 0:
                expanded.append(stmt)
            elif hasattr(stmt, "statements"):
                stmt.statements = self._expand_uses_in_statements(
                    stmt.statements, module, expanding_chain
                )
                expanded.append(stmt)
            else:
                expanded.append(stmt)
        return expanded


def parse_yang_file(file_path: str) -> YangModule:
    """Parse a YANG file and return a YangModule."""
    parser = YangParser()
    return parser.parse_file(Path(file_path))


def parse_yang_string(content: str) -> YangModule:
    """Parse YANG content from a string and return a YangModule."""
    parser = YangParser()
    return parser.parse_string(content)