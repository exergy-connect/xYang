"""
Basic usage examples for the xYang Python library.

Parsing builds a module AST; ``YangValidator`` walks instance data against
that schema (types, mandatory nodes, lists, and related rules). ``when``
and ``must`` are evaluated during validation using the built-in XPath
evaluator (coverage grows with the expression subset the parser supports).
"""

from xyang import parse_yang_file, parse_yang_string, YangValidator

def example_parse_file():
    """Example: Parse a YANG file."""
    print("=== Parsing YANG File ===")
    try:
        module = parse_yang_file("examples/meta-model.yang")
        print(f"Module name: {module.name}")
        print(f"YANG version: {module.yang_version}")
        print(f"Namespace: {module.namespace}")
        print(f"Prefix: {module.prefix}")
        print(f"Organization: {module.organization}")
        print(f"Number of typedefs: {len(module.typedefs)}")
        print(f"Number of top-level statements: {len(module.statements)}")
    except Exception as e:
        print(f"Error: {e}")


def example_parse_string():
    """Example: Parse YANG from string."""
    print("\n=== Parsing YANG String ===")
    yang_content = """
module example {
  yang-version 1.1;
  namespace "urn:example";
  prefix "ex";

  organization "Example Org";
  contact "contact@example.com";
  description "Example YANG module";

  revision "2026-01-15" {
    description "Initial version";
  }

  typedef entity-name {
    type string {
      length "1..64";
      pattern '[a-z_][a-z0-9_]*';
    }
    description "Entity name type";
  }

  container data-model {
    description "Root container";
    leaf name {
      type string;
      mandatory true;
      description "Model name";
    }
    leaf version {
      type string;
      description "Model version";
    }
    list entities {
      key name;
      min-elements 1;
      description "List of entities";
      leaf name {
        type entity-name;
        mandatory true;
        description "Entity name";
      }
    }
  }
}
"""
    try:
        module = parse_yang_string(yang_content)
        print(f"Module name: {module.name}")
        print(f"Namespace: {module.namespace}")
        print(f"Typedefs: {list(module.typedefs.keys())}")
    except Exception as e:
        print(f"Error: {e}")


def example_validate_data():
    """Example: Validate data against YANG module."""
    print("\n=== Validating Data ===")
    yang_content = """
module example {
  yang-version 1.1;
  namespace "urn:example";
  prefix "ex";

  container data-model {
    leaf name {
      type string;
      mandatory true;
    }
    leaf max_underscores {
      type uint8;
      default 2;
    }
    list entities {
      key name;
      min-elements 1;
      leaf name {
        type string;
        mandatory true;
      }
    }
  }
}
"""
    try:
        module = parse_yang_string(yang_content)
        validator = YangValidator(module)

        # Valid data
        valid_data = {
            "data-model": {
                "name": "example",
                "max_underscores": 2,
                "entities": [
                    {"name": "server"},
                    {"name": "switch"}
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(valid_data)
        print(f"Valid data - Valid: {is_valid}, Errors: {len(errors)}, Warnings: {len(warnings)}")

        # Invalid data (missing mandatory field)
        invalid_data = {
            "data-model": {
                "entities": [
                    {"name": "server"}
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(invalid_data)
        print(f"Invalid data - Valid: {is_valid}")
        for error in errors:
            print(f"  Error: {error}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    example_parse_file()
    example_parse_string()
    example_validate_data()
