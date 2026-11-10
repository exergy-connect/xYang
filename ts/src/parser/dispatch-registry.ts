/**
 * Parent statement → allowed substatements.
 *
 * Same table as `src/xyang/parser/dispatch_registry.py`. StatementParsers builds
 * the keyword→handler maps from it. The sets are the keywords Python accepts
 * today, including known RFC drift.
 *
 * Groups:
 * - METADATA_SUBSTATEMENTS: description, reference, units, status
 * - DATA_NODE_SUBSTATEMENTS: metadata plus config and typedef
 * - DATA_DEF_SUBSTATEMENTS: leaf, leaf-list, container, list, choice, anydata, anyxml, uses
 */

import * as kw from "./keywords";

export const METADATA_SUBSTATEMENTS: ReadonlySet<string> = new Set([
  kw.DESCRIPTION,
  kw.REFERENCE,
  kw.UNITS,
  kw.STATUS
]);

export const DATA_NODE_SUBSTATEMENTS: ReadonlySet<string> = new Set([
  ...METADATA_SUBSTATEMENTS,
  kw.CONFIG,
  kw.TYPEDEF
]);

export const DATA_DEF_SUBSTATEMENTS: ReadonlySet<string> = new Set([
  kw.LEAF,
  kw.LEAF_LIST,
  kw.CONTAINER,
  kw.LIST,
  kw.CHOICE,
  kw.ANYDATA,
  kw.ANYXML,
  kw.USES
]);

export type DispatchParent = {
  rfc: string;
  keywords: ReadonlySet<string>;
};

function parent(rfc: string, ...parts: ReadonlySet<string>[]): DispatchParent {
  const keywords = new Set<string>();
  for (const part of parts) {
    for (const keyword of part) {
      keywords.add(keyword);
    }
  }
  return { rfc, keywords };
}

const ioBody = parent(
  "7.14.2",
  METADATA_SUBSTATEMENTS,
  DATA_DEF_SUBSTATEMENTS,
  new Set([kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE])
);

/** Insertion order is the parity snapshot order. Keep it aligned with Python. */
const PARENTS: Array<[string, DispatchParent]> = [
  [
    "module",
    parent(
      "7.1.1",
      new Set([
        kw.LEAF,
        kw.LIST,
        kw.LEAF_LIST,
        kw.CONTAINER,
        kw.NOTIFICATION,
        kw.RPC,
        kw.ANYDATA,
        kw.ANYXML,
        kw.TYPEDEF,
        kw.GROUPING,
        kw.IMPORT,
        kw.INCLUDE,
        kw.REVISION,
        kw.DESCRIPTION,
        kw.REFERENCE,
        kw.FEATURE,
        kw.IDENTITY,
        kw.EXTENSION,
        kw.AUGMENT,
        kw.DEVIATION,
        kw.YANG_VERSION,
        kw.NAMESPACE,
        kw.PREFIX,
        kw.ORGANIZATION,
        kw.CONTACT
      ])
    )
  ],
  [
    "submodule",
    parent(
      "7.2.1",
      new Set([
        kw.YANG_VERSION,
        kw.ORGANIZATION,
        kw.CONTACT,
        kw.DESCRIPTION,
        kw.REFERENCE,
        kw.IMPORT,
        kw.INCLUDE,
        kw.REVISION,
        kw.FEATURE,
        kw.EXTENSION,
        kw.TYPEDEF,
        kw.IDENTITY,
        kw.GROUPING,
        kw.AUGMENT,
        kw.DEVIATION,
        kw.CONTAINER,
        kw.LIST,
        kw.LEAF,
        kw.LEAF_LIST,
        kw.ANYDATA,
        kw.ANYXML,
        kw.NOTIFICATION
      ])
    )
  ],
  ["belongs-to", parent("7.2.2", new Set([kw.PREFIX]))],
  ["import", parent("7.1.5", new Set([kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION]))],
  ["include", parent("7.1.6", new Set([kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION]))],
  ["typedef", parent("7.3.1", METADATA_SUBSTATEMENTS, new Set([kw.TYPE, kw.DEFAULT]))],
  [
    "type",
    parent(
      "7.4.1",
      new Set([
        kw.TYPE,
        kw.PATTERN,
        kw.LENGTH,
        kw.RANGE,
        kw.FRACTION_DIGITS,
        kw.ENUM,
        kw.BIT,
        kw.PATH,
        kw.REQUIRE_INSTANCE,
        kw.BASE,
        kw.UNITS,
        kw.DESCRIPTION,
        kw.REFERENCE
      ])
    )
  ],
  [
    "pattern",
    parent(
      "9.4.5",
      new Set([kw.DESCRIPTION, kw.REFERENCE, kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.MODIFIER])
    )
  ],
  ["enum", parent("9.6.4", new Set([kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE, kw.VALUE, kw.STATUS]))],
  ["bit", parent("9.7.4", new Set([kw.POSITION, kw.DESCRIPTION, kw.REFERENCE]))],
  ["identity", parent("7.18.1", METADATA_SUBSTATEMENTS, new Set([kw.BASE, kw.IF_FEATURE]))],
  [
    "leaf",
    parent(
      "7.6.2",
      DATA_NODE_SUBSTATEMENTS,
      new Set([kw.TYPE, kw.MANDATORY, kw.DEFAULT, kw.MUST, kw.WHEN, kw.IF_FEATURE])
    )
  ],
  [
    "leaf-list",
    parent(
      "7.7.3",
      DATA_NODE_SUBSTATEMENTS,
      new Set([kw.TYPE, kw.MIN_ELEMENTS, kw.MAX_ELEMENTS, kw.ORDERED_BY, kw.WHEN, kw.MUST, kw.IF_FEATURE])
    )
  ],
  [
    "list",
    parent(
      "7.8.1",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      new Set([
        kw.KEY,
        kw.UNIQUE,
        kw.MIN_ELEMENTS,
        kw.MAX_ELEMENTS,
        kw.ORDERED_BY,
        kw.WHEN,
        kw.MUST,
        kw.IF_FEATURE,
        kw.NOTIFICATION
      ])
    )
  ],
  [
    "container",
    parent(
      "7.5.2",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      new Set([kw.PRESENCE, kw.WHEN, kw.MUST, kw.GROUPING, kw.IF_FEATURE, kw.NOTIFICATION])
    )
  ],
  [
    "grouping",
    parent(
      "7.12.1",
      METADATA_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      new Set([kw.TYPEDEF, kw.GROUPING, kw.IF_FEATURE, kw.WHEN, kw.MUST, kw.NOTIFICATION])
    )
  ],
  [
    "notification",
    parent(
      "7.16.1",
      METADATA_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      new Set([kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE])
    )
  ],
  [
    "rpc",
    parent("7.14.1", METADATA_SUBSTATEMENTS, new Set([kw.WHEN, kw.MUST, kw.INPUT, kw.OUTPUT, kw.IF_FEATURE]))
  ],
  ["input", ioBody],
  ["output", { rfc: "7.14.3", keywords: ioBody.keywords }],
  [
    "choice",
    parent(
      "7.9.1",
      DATA_NODE_SUBSTATEMENTS,
      new Set([kw.WHEN, kw.IF_FEATURE, kw.CASE, kw.MANDATORY, kw.DEFAULT])
    )
  ],
  ["case", parent("7.9.2", DATA_NODE_SUBSTATEMENTS, DATA_DEF_SUBSTATEMENTS, new Set([kw.WHEN, kw.IF_FEATURE]))],
  [
    "augment",
    parent(
      "7.17.1",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      new Set([kw.IF_FEATURE, kw.CASE, kw.WHEN, kw.MUST, kw.NOTIFICATION])
    )
  ],
  ["uses", parent("7.13.1", METADATA_SUBSTATEMENTS, new Set([kw.WHEN, kw.IF_FEATURE, kw.REFINE, kw.AUGMENT]))],
  [
    "refine",
    parent(
      "7.13.2",
      DATA_NODE_SUBSTATEMENTS,
      new Set([
        kw.MUST,
        kw.MIN_ELEMENTS,
        kw.MAX_ELEMENTS,
        kw.ORDERED_BY,
        kw.MANDATORY,
        kw.DEFAULT,
        kw.IF_FEATURE,
        kw.TYPE
      ])
    )
  ],
  ["anydata", parent("7.10.1", DATA_NODE_SUBSTATEMENTS, new Set([kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY]))],
  ["anyxml", parent("7.11.1", DATA_NODE_SUBSTATEMENTS, new Set([kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY]))],
  ["must", parent("7.5.4", new Set([kw.ERROR_MESSAGE, kw.DESCRIPTION, kw.REFERENCE]))],
  ["when", parent("7.21.5", new Set([kw.DESCRIPTION, kw.REFERENCE]))],
  ["feature", parent("7.20.1", new Set([kw.DESCRIPTION, kw.IF_FEATURE, kw.REFERENCE]))],
  ["if-feature", parent("7.20.2", new Set([kw.DESCRIPTION, kw.REFERENCE]))],
  ["extension", parent("7.19.1", new Set([kw.ARGUMENT, kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE]))],
  ["argument", parent("7.19.2", new Set([kw.YIN_ELEMENT]))],
  ["deviation", parent("7.20.3", new Set([kw.DESCRIPTION, kw.REFERENCE, kw.DEVIATE]))],
  ["revision", parent("7.1.9", new Set([kw.DESCRIPTION, kw.REFERENCE]))],
  [
    "extension-invocation",
    parent(
      "6.3.1",
      new Set([
        kw.IF_FEATURE,
        kw.WHEN,
        kw.MUST,
        kw.DESCRIPTION,
        kw.REFERENCE,
        kw.TYPE,
        kw.USES,
        kw.LEAF,
        kw.LEAF_LIST,
        kw.CONTAINER,
        kw.LIST,
        kw.CHOICE,
        kw.CASE,
        kw.ANYDATA,
        kw.ANYXML
      ])
    )
  ],
  // Argument only. A braced body is not dispatched (known drift).
  ["length", { rfc: "9.4.4", keywords: new Set() }],
  ["range", { rfc: "9.2.4", keywords: new Set() }]
];

export const DISPATCH_REGISTRY: Record<string, DispatchParent> = Object.fromEntries(PARENTS);

export function dispatchRegistryParitySnapshot(): Record<string, { rfc: string; keywords: string[] }> {
  const snapshot: Record<string, { rfc: string; keywords: string[] }> = {};
  for (const [name, spec] of PARENTS) {
    snapshot[name] = { rfc: spec.rfc, keywords: [...spec.keywords].sort() };
  }
  return snapshot;
}
