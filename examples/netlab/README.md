# Netlab topology validation

[`netlab.yang`](netlab.yang) models the fields and BGP checks needed for Netlab's
`tests/integration/validate/01-bgp-session.yml` and
`tests/integration/bgp/02-ibgp-ebgp-session.yml`. It demonstrates how a YANG
model can describe normalization of a YAML topology before xYang validates it.
It is not a complete model of every Netlab topology.

## Run the example

From the xYang repository root, install the local Python package and PyYAML:

```sh
python -m pip install -e . PyYAML
```

With the Netlab repository at `../3rd-party/netlab`, run:

```sh
xyang validate --native-json --format json examples/netlab/netlab.yang \
  ../3rd-party/netlab/tests/integration/validate/01-bgp-session.yml

xyang validate --native-json --format json examples/netlab/netlab.yang \
  ../3rd-party/netlab/tests/integration/bgp/02-ibgp-ebgp-session.yml
```

Expected output:

```json
{"valid": true, "errors": []}
```

`--native-json` accepts Netlab's mappings keyed by name for the `nodes`,
`groups`, and `validate` lists. The Python CLI reads `.yml` and `.yaml` files
when PyYAML is installed. Substitute the path to your Netlab checkout if it is
in a different location.

## Model-defined normalization

The model imports the shared [`xyang-transform`](../../shared/xyang-transform.yang)
extensions. `xt:expand-dotted-keys true` is a module-wide setting: for example,
`bgp.as: 65000` inside a node is read as `bgp: {as: 65000}`. It also handles
root-level keys such as `defaults.bgp.as`. Conflicting paths produce a
`normalize` error instead of overwriting a value.

The `links` list has conditional `xt:normalize` rules. For a string containing
`-`, its `xt:apply` expression splits the value and constructs a link object:
`dut-x1` becomes `{left: dut, right: x1}`. A two-endpoint mapping with null
values, such as `{dut: null, x1: null}`, becomes the same link object. Mappings
with interface attributes are not transformed; the model reports them as
unsupported instead of discarding the attributes. An object with both `left` and
`right` keys is treated as the model's canonical link form.
The expression uses the first two parts of the split, so this shorthand does not
represent endpoint names containing hyphens unambiguously.

After normalization, the YANG model checks node references in groups, links,
and validation targets. It requires an AS for each BGP-enabled node, accepting a
node, topology, or default AS. Links can connect nodes in the same AS (iBGP) or
different ASes (eBGP), but cannot connect a node to itself. An empty keyed node
entry is normalized to an empty object before the AS checks.
The `_adjust` rules are retained as opaque data: Netlab does not give those
array entries a guaranteed unique key, and this model does not validate their
contents.

Normalization is currently implemented in Python; the TypeScript implementation
preserves these annotations but does not execute them. For rule syntax, error
behavior, and the supported jq-style expression subset, see
[Instance normalization](../../docs/instance-normalization.md).
