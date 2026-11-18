# Netlab topology validation

[`netlab.yang`](netlab.yang) models the fields and BGP checks needed for Netlab's
`tests/integration/validate/01-bgp-session.yml` and
`tests/integration/bgp/02-ibgp-ebgp-session.yml`. It demonstrates how a YANG
model can describe normalization of a YAML topology before xYang validates it.
It includes additional attributes used by the numbered BGP labs. Some complex
attributes are retained as opaque data rather than validated. It is not a complete
model of every Netlab topology; some Netlab forms are not yet supported.

## Run the example

From the xYang repository root, install the local Python package and PyYAML:

```sh
python -m pip install -e . PyYAML
```

With the Netlab repository at `../3rd-party/netlab`, run:

```sh
xyang validate examples/netlab/netlab.yang \
  ../3rd-party/netlab/tests/integration/validate/01-bgp-session.yml

xyang validate examples/netlab/netlab.yang \
  ../3rd-party/netlab/tests/integration/bgp/02-ibgp-ebgp-session.yml
```

Expected output:

```json
{"valid": true, "errors": []}
```

For YAML data files, the Python CLI uses native encoding (including Netlab's
keyed lists) and JSON output by default. It reads `.yml` and `.yaml` files when
PyYAML is installed. Pass `--format text` for human-readable output. Substitute
the path to your Netlab checkout if it is in a different location.

## Model-defined normalization

The model imports the shared [`xyang-transform`](../../shared/xyang-transform.yang)
extensions. `xt:expand-dotted-keys true` is a module-wide setting: for example,
`bgp.as: 65000` inside a node is read as `bgp: {as: 65000}`. It also handles
root-level keys such as `defaults.bgp.as`. Conflicting paths produce a
`normalize` error instead of overwriting a value.

The `links` list has conditional `xt:normalize` rules. An empty YAML `links:`
value becomes an empty list, and `dut-x1` becomes
`{nodes: [{node: dut}, {node: x1}]}` in one step.
For mapping entries, `keys(/nodes/name)` selects keys matching topology node
names. The model moves those keys and their interface attributes into `nodes`,
while leaving other link attributes in place. A single node represents a stub.
A mapping containing `nodes` is treated as canonical, so a node named `nodes`
must use that form. Hyphens in node names are ambiguous in string shorthand.

After normalization, the YANG model checks node references in groups, links,
and validation targets. It requires an AS for each BGP-enabled node, accepting a
node, topology, or default AS. Links can connect nodes in the same AS (iBGP) or
different ASes (eBGP), but cannot connect a node to itself. Boolean loopbacks are retained as `loopback.enabled`, preserving whether they
were explicitly enabled or disabled. An empty keyed node entry is normalized to an empty object before the AS checks.
The `_adjust` rules are retained as opaque data: Netlab does not give those
array entries a guaranteed unique key, and this model does not validate their
contents.

Python, TypeScript, and Zig support these normalization annotations. For rule
syntax, error behavior, and the supported jq-style expression subset, see
[Instance normalization](../../docs/instance-normalization.md).
