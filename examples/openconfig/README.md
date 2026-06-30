# OpenConfig Netlink Example

`openconfig_netlink.py` maps a small OpenConfig-shaped RFC 7951 JSON subset to
Linux interface configuration through Netlink. It is meant as a focused example,
not a complete OpenConfig implementation.

## Supported Subset

- Interface MTU from `openconfig-interfaces:interfaces/interface/config/mtu`
- Interface enabled state from `config/enabled`
- Linux bond creation from aggregate interfaces
- Bond membership from `openconfig-if-ethernet:ethernet/config/aggregate-id`
- VLAN subinterfaces from `subinterfaces/subinterface/openconfig-vlan:vlan/config/vlan-id`

When an interface is a bond member, configure VLAN subinterfaces on the bond
interface, not on the member port. The sample creates `bond0.100` on `bond0`.

The schema includes one xYang example-specific validation rule for this policy:
a standard YANG `must` statement rejects VLAN subinterfaces on ports that have
`aggregate-id` set. This captures the Linux behavior expected by this
translator, but it is not an upstream OpenConfig constraint.

The local schema in `openconfig-interfaces-subset.yang` mirrors only this subset.
The script accepts RFC 7951 module-qualified JSON keys such as
`openconfig-vlan:vlan`, then normalizes those keys for validation with xYang.

## Requirements

Dry-run planning and default xYang validation use only this repository.

Real Netlink operations require Linux, root or `CAP_NET_ADMIN`, and `pyroute2`:

```bash
pip install -r examples/openconfig/requirements.txt
```

For validation from a source checkout, run with `PYTHONPATH=src` or install xYang:

```bash
pip install -e .
```

## Apply Configuration

Preview the Netlink operations without changing the host:

```bash
python3 examples/openconfig/openconfig_netlink.py \
  apply examples/openconfig/sample_interfaces.json \
  --dry-run
```

Validation runs by default before planning or applying:

```bash
PYTHONPATH=src python3 examples/openconfig/openconfig_netlink.py \
  apply examples/openconfig/sample_interfaces.json \
  --dry-run
```

Skip schema validation only when intentionally testing parser or Netlink behavior:

```bash
python3 examples/openconfig/openconfig_netlink.py \
  apply examples/openconfig/sample_interfaces.json \
  --no-validate \
  --dry-run
```

Apply the configuration:

```bash
sudo PYTHONPATH=src python3 examples/openconfig/openconfig_netlink.py \
  apply examples/openconfig/sample_interfaces.json
```

`apply` is idempotent where practical: existing bonds and VLAN links are reused,
while MTU, link state, and bond membership are set through Netlink.

To operate inside a network namespace, add `--ns NAME`. The namespace is created
if it does not exist. Dry-run mode still only prints planned operations and does
not create the namespace.

```bash
sudo PYTHONPATH=src python3 examples/openconfig/openconfig_netlink.py \
  apply examples/openconfig/sample_interfaces.json \
  --ns oc-demo
```

## Read Current Configuration

Write the current Linux link state as OpenConfig-shaped JSON:

```bash
PYTHONPATH=src python3 examples/openconfig/openconfig_netlink.py \
  read /tmp/openconfig-current.json
```

Read from a network namespace, creating it first if needed:

```bash
sudo PYTHONPATH=src python3 examples/openconfig/openconfig_netlink.py \
  read /tmp/openconfig-current.json \
  --ns oc-demo
```

The readback maps physical and bond links into `interface` entries. VLAN links
are represented as subinterfaces under their parent when the kernel reports VLAN
metadata. Bond slaves include `openconfig-if-ethernet:ethernet/config/aggregate-id`.

## Limitations

- The example covers only MTU, enabled state, VLAN links, bonds, and bond
  membership.
- It does not reconcile deletions or remove configuration absent from the input.
- Bond mode support is intentionally small: `LACP` maps to Linux `802.3ad`, and
  `STATIC` maps to `balance-rr`.
- The bundled YANG file is a validation aid for this example, not the full
  OpenConfig interfaces model.
