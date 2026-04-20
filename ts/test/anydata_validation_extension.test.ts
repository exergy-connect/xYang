import { describe, expect, it } from "vitest";
import { AnydataValidationMode, parseYangString, ValidatorExtension, YangValidator } from "../src";

describe("python parity: test_anydata_validation_extension", () => {
  const HOST_YANG = `
module example-push-host {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:host";
  prefix ph;
  container notification {
    anydata payload {
      description "Opaque subtree; draft §4 JSON uses module:node members.";
    }
  }
}
`;

  const PAYLOAD_YANG = `
module example-rfc8343-shape {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:8343-shape";
  prefix ifshape;
  container interfaces-state {
    list interface {
      key name;
      leaf name { type string; }
      leaf in-octets { type uint64; }
    }
  }
}
`;

  function buildValidator(mode: AnydataValidationMode): YangValidator {
    const host = parseYangString(HOST_YANG);
    const payload = parseYangString(PAYLOAD_YANG);
    const validator = new YangValidator(host);
    validator.enableExtension(ValidatorExtension.ANYDATA_VALIDATION, {
      modules: [payload],
      mode
    });
    return validator;
  }

  it("anydata complete accepts valid counters", () => {
    const validator = buildValidator(AnydataValidationMode.COMPLETE);
    const result = validator.validate({
      notification: {
        payload: {
          "example-rfc8343-shape:interfaces-state": {
            interface: [{ name: "eth0", "in-octets": 42 }]
          }
        }
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("anydata complete rejects invalid in-octets", () => {
    const validator = buildValidator(AnydataValidationMode.COMPLETE);
    const result = validator.validate({
      notification: {
        payload: {
          "example-rfc8343-shape:interfaces-state": {
            interface: [{ name: "eth0", "in-octets": "not-a-number" }]
          }
        }
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.some((error) => error.includes("in-octets") || error.toLowerCase().includes("integer"))).toBe(true);
  });

  it("anydata candidate allows invalid in-octets type", () => {
    const validator = buildValidator(AnydataValidationMode.CANDIDATE);
    const result = validator.validate({
      notification: {
        payload: {
          "example-rfc8343-shape:interfaces-state": {
            interface: [{ name: "eth0", "in-octets": "not-a-number" }]
          }
        }
      }
    });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("anydata unknown qualified member errors", () => {
    const validator = buildValidator(AnydataValidationMode.COMPLETE);
    const result = validator.validate({
      notification: {
        payload: {
          "example-rfc8343-shape:nonexistent": {}
        }
      }
    });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.includes("nonexistent"))).toBe(true);
  });

  it("enable extension rejects non-YangModule entries in modules array", () => {
    const host = parseYangString(HOST_YANG);
    const validator = new YangValidator(host);

    expect(() =>
      validator.enableExtension(ValidatorExtension.ANYDATA_VALIDATION, {
        modules: [PAYLOAD_YANG],
        mode: AnydataValidationMode.COMPLETE
      })
    ).toThrow(/YangModule|module/i);
  });
});
