"""
Test to ensure YANG XPath expressions are parsed only once.

This test monkey patches the XPathTokenizer to track how many times
each expression is tokenized, ensuring that YANG must/when statements
are parsed once during module parsing and reused during validation.
"""

import pytest
from unittest.mock import patch
from collections import defaultdict

from xYang import parse_yang_string, YangValidator


def test_yang_expressions_parsed_once():
    """Test that YANG XPath expressions are parsed at most once per occurrence.
    
    This test verifies that:
    1. Each unique expression in YANG is parsed once during YANG parsing
    2. During validation, pre-parsed ASTs are reused (no re-parsing)
    """
    
    # Track tokenization calls - separate tracking for parsing vs validation
    parse_phase_count = defaultdict(int)
    validation_phase_count = defaultdict(int)
    original_tokenize = None
    yang_parsing_complete = False
    
    def tracked_tokenize(self):
        """Track tokenization calls."""
        expr = getattr(self, 'expression', 'unknown')
        
        if yang_parsing_complete:
            # This is during validation - should not happen if AST is reused
            validation_phase_count[expr] += 1
        else:
            # This is during YANG parsing
            parse_phase_count[expr] += 1
        
        # Call original tokenize
        return original_tokenize(self)
    
    # YANG module with multiple must and when statements
    # Note: Some expressions appear multiple times (e.g., "string-length(.) > 0")
    # Each occurrence should be parsed once during YANG parsing
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
      must "string-length(.) > 0";
      must "string-length(.) <= 64";
    }
    
    leaf count {
      type uint8;
      must ". >= 0";
      must ". <= 255";
    }
    
    leaf status {
      type string;
      when "../count > 0";
      must ". != ''";
    }
    
    list items {
      key "id";
      leaf id {
        type string;
        must "string-length(.) > 0";  # Same expression as leaf name
      }
      leaf value {
        type uint8;
        must ". >= 0";  # Same expression as leaf count
      }
    }
  }
}
"""
    
    # Monkey patch XPathTokenizer.tokenize before parsing
    from xYang.xpath.parser import XPathTokenizer
    original_tokenize = XPathTokenizer.tokenize
    
    with patch.object(XPathTokenizer, 'tokenize', tracked_tokenize):
        # Parse YANG module - this should parse all must/when expressions
        module = parse_yang_string(yang_content)
        
        # Mark parsing as complete
        yang_parsing_complete = True
        
        # Create validator
        validator = YangValidator(module)
        
        # Validate data multiple times to ensure expressions aren't re-parsed
        test_data = {
            "data": {
                "name": "test",
                "count": 10,
                "status": "active",
                "items": [
                    {"id": "item1", "value": 5},
                    {"id": "item2", "value": 10}
                ]
            }
        }
        
        # Validate multiple times - should not trigger any new parsing
        for _ in range(3):
            is_valid, errors, warnings = validator.validate(test_data)
            assert is_valid, f"Validation failed: {errors}"
    
    # Check results
    print("\nTokenization during YANG parsing:")
    for expr, count in sorted(parse_phase_count.items()):
        print(f"  '{expr}': {count} time(s)")
    
    print("\nTokenization during validation (should be 0):")
    for expr, count in sorted(validation_phase_count.items()):
        print(f"  '{expr}': {count} time(s)")
    
    # During validation, no expressions should be tokenized (AST should be reused)
    assert len(validation_phase_count) == 0, (
        f"Found {len(validation_phase_count)} expressions tokenized during validation. "
        f"This indicates ASTs are not being reused. Expressions: {list(validation_phase_count.keys())}"
    )
    
    # Verify we have the expected expressions parsed during YANG parsing
    expected_expressions = {
        "string-length(.) > 0",
        "string-length(.) <= 64",
        ". >= 0",
        ". <= 255",
        "../count > 0",
        ". != ''",
    }
    
    # Check that all expected expressions were tokenized during parsing
    parsed_expressions = set(parse_phase_count.keys())
    for expected in expected_expressions:
        assert expected in parsed_expressions, (
            f"Expected expression '{expected}' was not tokenized during YANG parsing"
        )
    
    # Note: Expressions that appear multiple times in YANG will be parsed multiple times
    # during YANG parsing (once per occurrence), which is correct behavior.
    # The key is that during validation, they should not be parsed again.


def test_yang_expressions_parsed_once_with_meta_model():
    """Test with actual meta-model to ensure real-world expressions are parsed once."""
    from pathlib import Path
    
    # Load meta-model
    meta_model_path = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    if not meta_model_path.exists():
        pytest.skip("meta-model.yang not found")
    
    # Track tokenization calls - separate tracking for parsing vs validation
    parse_phase_count = defaultdict(int)
    validation_phase_count = defaultdict(int)
    original_tokenize = None
    yang_parsing_complete = False
    
    def tracked_tokenize(self):
        """Track tokenization calls."""
        expr = getattr(self, 'expression', 'unknown')
        
        if yang_parsing_complete:
            # This is during validation - should not happen if AST is reused
            validation_phase_count[expr] += 1
        else:
            # This is during YANG parsing
            parse_phase_count[expr] += 1
        
        return original_tokenize(self)
    
    from xYang import parse_yang_file
    from xYang.xpath.parser import XPathTokenizer
    original_tokenize = XPathTokenizer.tokenize
    
    with patch.object(XPathTokenizer, 'tokenize', tracked_tokenize):
        # Parse YANG module
        module = parse_yang_file(str(meta_model_path))
        
        # Mark parsing as complete
        yang_parsing_complete = True
        
        # Create validator
        validator = YangValidator(module)
        
        # Sample data model for validation
        test_data = {
            "data-model": {
                "name": "Test Model",
                "version": "1.0.0",
                "author": "Test",
                "entities": [
                    {
                        "name": "test_entity",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "type": "string"}
                        ]
                    }
                ]
            }
        }
        
        # Validate multiple times - should not trigger any new parsing
        for _ in range(2):
            is_valid, errors, warnings = validator.validate(test_data)
            # Don't assert is_valid - meta-model has strict constraints
    
    # Check results
    print(f"\nTotal unique expressions tokenized during YANG parsing: {len(parse_phase_count)}")
    print("Sample tokenization counts during parsing (first 10):")
    for expr, count in list(sorted(parse_phase_count.items()))[:10]:
        print(f"  '{expr[:60]}...': {count} time(s)")
    
    print(f"\nTotal unique expressions tokenized during validation: {len(validation_phase_count)}")
    if validation_phase_count:
        print("Sample tokenization counts during validation (first 10):")
        for expr, count in list(sorted(validation_phase_count.items()))[:10]:
            print(f"  '{expr[:60]}...': {count} time(s)")
    
    # During validation, no expressions should be tokenized (AST should be reused)
    assert len(validation_phase_count) == 0, (
        f"Found {len(validation_phase_count)} expressions tokenized during validation. "
        f"This indicates ASTs are not being reused. "
        f"Sample expressions: {list(validation_phase_count.keys())[:5]}"
    )
    
    # Verify that expressions were parsed during YANG parsing
    assert len(parse_phase_count) > 0, (
        "No expressions were tokenized during YANG parsing. This indicates a problem with the test setup."
    )
    
    # Note: Expressions that appear multiple times in YANG will be parsed multiple times
    # during YANG parsing (once per occurrence), which is correct behavior.
    # The key is that during validation, they should not be parsed again.
