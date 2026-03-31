"""
Tests for YANG ``identity`` / ``identityref`` and ``must`` with ``derived-from`` /
``derived-from-or-self`` (RFC 7950, Section 10).
"""

# Minimal YANG 1.1 module: base identity, derived identity, leaf with identityref.
MINIMAL_IDENTITY_YANG = """
module identity-test {
  yang-version 1.1;
  namespace "urn:identity-test";
  prefix "it";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
"""

# ``must`` on ``data``: ``kind`` must name an identity derived from ``mammal``
IDENTITY_YANG_MUST_DERIVED_FROM = """
module identity-must-derived-from {
  yang-version 1.1;
  namespace "urn:identity-must-derived-from";
  prefix "im";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    must "derived-from(kind, 'im:mammal')";

    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
"""

IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF = """
module identity-must-derived-from-or-self {
  yang-version 1.1;
  namespace "urn:identity-must-derived-from-or-self";
  prefix "io";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    must "derived-from-or-self(kind, 'io:mammal')";

    leaf kind {
      type identityref {
        base animal;
      }
    }
  }
}
"""

IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING = """
module identity-must-sibling {
  yang-version 1.1;
  namespace "urn:identity-must-sibling";
  prefix "is";

  identity animal;

  identity mammal {
    base animal;
  }

  identity dog {
    base mammal;
  }

  container data {
    leaf kind {
      type identityref {
        base animal;
      }
    }
    leaf label {
      type string;
      must "derived-from(../kind, 'is:mammal')";
    }
  }
}
"""


def test_parse_minimal_identity_module():
    """Parse a module with ``identity`` statements and an ``identityref`` leaf."""
    from xyang import parse_yang_string

    module = parse_yang_string(MINIMAL_IDENTITY_YANG)
    assert module.name == "identity-test"
    assert "animal" in module.identities
    assert module.identities["dog"].bases == ["mammal"]


def test_parse_identity_module_with_must_derived_from():
    """Parse ``must`` using ``derived-from(identityref, identity)`` (RFC 7950)."""
    from xyang import parse_yang_string

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM)
    assert module.name == "identity-must-derived-from"


def test_parse_identity_module_with_must_derived_from_or_self():
    """Parse ``must`` using ``derived-from-or-self(identityref, identity)`` (RFC 7950)."""
    from xyang import parse_yang_string

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF)
    assert module.name == "identity-must-derived-from-or-self"


def test_parse_identity_module_with_must_on_sibling_leaf():
    """Parse ``must`` on a leaf that constrains a sibling ``identityref`` via ``derived-from``."""
    from xyang import parse_yang_string

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING)
    assert module.name == "identity-must-sibling"


def test_validate_must_derived_from_accepts_mammal_descendant():
    from xyang import parse_yang_string, YangValidator

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM)
    validator = YangValidator(module)
    data = {"data": {"kind": "im:dog"}}
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, errors


def test_validate_must_derived_from_rejects_base_only():
    from xyang import parse_yang_string, YangValidator

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM)
    validator = YangValidator(module)
    data = {"data": {"kind": "im:animal"}}
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid
    assert errors


def test_validate_must_derived_from_or_self_accepts_exact_base():
    from xyang import parse_yang_string, YangValidator

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM_OR_SELF)
    validator = YangValidator(module)
    data = {"data": {"kind": "io:mammal"}}
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, errors


def test_validate_must_on_sibling_when_identityref_satisfies_derived_from():
    from xyang import parse_yang_string, YangValidator

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING)
    validator = YangValidator(module)
    data = {"data": {"kind": "is:dog", "label": "x"}}
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, errors


def test_validate_must_on_sibling_fails_when_identityref_not_mammal_lineage():
    from xyang import parse_yang_string, YangValidator

    module = parse_yang_string(IDENTITY_YANG_MUST_DERIVED_FROM_SIBLING)
    validator = YangValidator(module)
    data = {"data": {"kind": "is:animal", "label": "x"}}
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid
    assert errors
