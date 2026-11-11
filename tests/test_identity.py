"""
Tests for YANG ``identity`` / ``identityref`` parsing (RFC 7950).

Validation coverage: tests/cases/references/identityref,
tests/cases/references/identityref-must-derived-from.
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


def test_parse_minimal_identity_module():
    """Parse a module with ``identity`` statements and an ``identityref`` leaf."""
    from xyang import parse_yang_string
    from xyang.identifier_ref import identifier_ref

    module = parse_yang_string(MINIMAL_IDENTITY_YANG)
    assert module.name == "identity-test"
    assert "animal" in module.identities
    assert module.identities["dog"].bases == [identifier_ref("mammal")]


def test_identityref_base_accepts_prefixed_qname():
    """``base sn:foo`` inside identityref (ietf-yang-push yang-data pattern)."""
    from xyang import parse_yang_string
    from xyang.ast import YangLeafStmt
    from xyang.identifier_ref import identifier_ref

    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;

  identity error;

  container c {
    leaf reason {
      type identityref {
        base m:error;
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    leaf = module.find_statement("c")
    assert leaf is not None
    reason = leaf.find_statement("reason")
    assert isinstance(reason, YangLeafStmt)
    assert reason.type is not None
    assert reason.type.identityref_bases == [identifier_ref("error", "m")]


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
