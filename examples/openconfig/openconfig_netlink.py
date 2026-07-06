#!/usr/bin/env python3
"""
Apply and read a small OpenConfig interfaces subset using Linux Netlink.

This example intentionally supports a narrow RFC 7951 JSON shape: interface MTU,
VLAN subinterfaces, Linux bonding interfaces, and bond membership. It uses
``pyroute2`` only when it needs to talk to Netlink.
"""
# pylint: disable=import-outside-toplevel

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SCHEMA = Path(__file__).with_name("openconfig-interfaces-subset.yang")
ROOT_KEY = "openconfig-interfaces:interfaces"
BOND_MODES = {
    "balance-rr": 0,
    "active-backup": 1,
    "balance-xor": 2,
    "broadcast": 3,
    "802.3ad": 4,
    "balance-tlb": 5,
    "balance-alb": 6,
}


@dataclass(frozen=True)
class LinkOperation:
    """A normalized Linux link operation derived from OpenConfig-shaped input."""

    kind: str
    name: str
    attrs: dict[str, object]


class ConfigError(ValueError):
    """Raised when the supported OpenConfig subset is malformed."""


def validate_namespace_name(namespace: str) -> str:
    """Reject path-like namespace values before passing a name to pyroute2."""

    if not namespace or "/" in namespace or "\0" in namespace:
        raise ConfigError("--ns must be a non-empty network namespace name, not a path")
    return namespace


def load_json(path: Path) -> dict[str, Any]:
    """Load an RFC 7951 JSON object from disk."""

    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ConfigError("top-level JSON value must be an object")
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write readback data as stable, pretty-printed JSON."""

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def local_name(key: str) -> str:
    """Return the local identifier from an RFC 7951 ``module:name`` key."""

    return key.split(":", 1)[1] if ":" in key else key


def localize_keys(value: Any) -> Any:
    """Strip RFC 7951 module prefixes for the local subset validation schema."""
    if isinstance(value, dict):
        return {local_name(str(k)): localize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [localize_keys(item) for item in value]
    return value


def get_child(data: dict[str, Any], name: str, default: Any = None) -> Any:
    """Look up a child by local name, accepting qualified or unqualified keys."""

    if name in data:
        return data[name]
    for key, value in data.items():
        if isinstance(key, str) and local_name(key) == name:
            return value
    return default


def require_dict(value: Any, path: str) -> dict[str, Any]:
    """Return *value* as a dict or raise a path-qualified config error."""

    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be an object")
    return value


def optional_dict(value: Any, path: str) -> dict[str, Any]:
    """Return an optional object value, treating a missing node as empty."""

    if value is None:
        return {}
    return require_dict(value, path)


def optional_list(value: Any, path: str) -> list[Any]:
    """Return an optional list value, treating a missing node as empty."""

    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    return value


def as_int(value: Any, path: str) -> int:
    """Coerce a parsed JSON value to int, excluding bool."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path} must be an integer")
    return value


def as_str(value: Any, path: str) -> str:
    """Coerce a parsed JSON value to a non-empty string."""

    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path} must be a non-empty string")
    return value


def validate_with_xyang(data: dict[str, Any], schema: Path) -> None:
    """Validate the supported OpenConfig subset with xYang."""

    try:
        from xyang import YangValidator, parse_yang_file
    except ImportError as exc:
        raise ConfigError(
            "xYang is not importable; run from the repository with PYTHONPATH=src "
            "or install the package before using validation"
        ) from exc

    module = parse_yang_file(str(schema))
    validator = YangValidator(module)
    localized = localize_keys(data)
    ok, errors, warnings = validator.validate(localized)
    for warning in warnings:
        print(f"validation warning: {warning}", file=sys.stderr)
    if not ok:
        for error in errors:
            print(f"validation error: {error}", file=sys.stderr)
        raise ConfigError("xYang validation failed")


def interfaces_root(data: dict[str, Any]) -> dict[str, Any]:
    """Return the OpenConfig interfaces root container."""

    root = get_child(data, "interfaces")
    if root is None:
        raise ConfigError(f"missing {ROOT_KEY}")
    return require_dict(root, ROOT_KEY)


def interface_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return validated interface list entries from the input document."""

    root = interfaces_root(data)
    entries = optional_list(get_child(root, "interface"), f"{ROOT_KEY}/interface")
    return [
        require_dict(entry, f"{ROOT_KEY}/interface[{idx}]")
        for idx, entry in enumerate(entries)
    ]


def interface_name(entry: dict[str, Any], idx: int) -> str:
    """Return the list key for an interface entry."""

    config = optional_dict(get_child(entry, "config"), f"interface[{idx}]/config")
    name = get_child(entry, "name", get_child(config, "name"))
    return as_str(name, f"interface[{idx}]/name")


def is_bond_interface(name: str, entry: dict[str, Any]) -> bool:
    """Infer whether an interface entry should create a Linux bond link."""

    config = optional_dict(get_child(entry, "config"), f"interface[{name}]/config")
    iface_type = str(get_child(config, "type", ""))
    return (
        bool(get_child(entry, "aggregation"))
        or name.startswith("bond")
        or "ieee8023adLag" in iface_type
        or "aggregate" in iface_type.lower()
    )


def bond_mode(entry: dict[str, Any]) -> str | None:
    """Translate the supported OpenConfig LAG type values to Linux mode names."""

    aggregation = optional_dict(get_child(entry, "aggregation"), "aggregation")
    config = optional_dict(get_child(aggregation, "config"), "aggregation/config")
    lag_type = get_child(config, "lag-type")
    if lag_type is None:
        return None
    normalized = str(lag_type).upper()
    if normalized == "LACP":
        return "802.3ad"
    if normalized == "STATIC":
        return "balance-rr"
    return str(lag_type)


def enabled_value(entry: dict[str, Any]) -> bool | None:
    """Return the requested administrative enabled state, if present."""

    config = optional_dict(get_child(entry, "config"), "config")
    enabled = get_child(config, "enabled")
    if enabled is None:
        return None
    if not isinstance(enabled, bool):
        raise ConfigError("interface config/enabled must be a boolean")
    return enabled


def mtu_value(entry: dict[str, Any], path: str) -> int | None:
    """Return the requested interface MTU, if present."""

    config = optional_dict(get_child(entry, "config"), f"{path}/config")
    mtu = get_child(config, "mtu")
    if mtu is None:
        return None
    return as_int(mtu, f"{path}/config/mtu")


def bond_membership(entry: dict[str, Any]) -> str | None:
    """Return the aggregate interface name referenced by an Ethernet member."""

    ethernet = optional_dict(get_child(entry, "ethernet"), "ethernet")
    config = optional_dict(get_child(ethernet, "config"), "ethernet/config")
    aggregate_id = get_child(config, "aggregate-id")
    if aggregate_id is None:
        return None
    return as_str(aggregate_id, "ethernet/config/aggregate-id")


def vlan_subinterfaces(parent: str, entry: dict[str, Any]) -> Iterable[LinkOperation]:
    """Yield VLAN creation operations for subinterfaces under *parent*."""

    subinterfaces = optional_dict(get_child(entry, "subinterfaces"), f"{parent}/subinterfaces")
    raw_subinterfaces = optional_list(
        get_child(subinterfaces, "subinterface"),
        f"{parent}/subinterfaces/subinterface",
    )
    for idx, raw_subinterface in enumerate(raw_subinterfaces):
        op = vlan_subinterface(parent, idx, raw_subinterface)
        if op is not None:
            yield op


def vlan_subinterface(parent: str, idx: int, raw_subinterface: Any) -> LinkOperation | None:
    """Convert one OpenConfig subinterface entry to a VLAN operation."""

    subinterface_path = f"{parent}/subinterfaces/subinterface[{idx}]"
    subinterface = require_dict(raw_subinterface, subinterface_path)
    vlan = optional_dict(get_child(subinterface, "vlan"), f"{subinterface_path}/vlan")
    vlan_config = optional_dict(get_child(vlan, "config"), f"{subinterface_path}/vlan/config")
    vlan_id = get_child(vlan_config, "vlan-id")
    if vlan_id is None:
        return None

    vlan_id_int = as_int(vlan_id, f"{subinterface_path}/vlan/config/vlan-id")

    config = optional_dict(get_child(subinterface, "config"), f"{subinterface_path}/config")
    name = get_child(config, "name", f"{parent}.{vlan_id_int}")
    attrs: dict[str, object] = {"parent": parent, "vlan_id": vlan_id_int}
    sub_mtu = get_child(config, "mtu")
    if sub_mtu is not None:
        attrs["mtu"] = as_int(sub_mtu, f"{subinterface_path}/config/mtu")

    return LinkOperation(
        "create_vlan",
        as_str(name, f"{subinterface_path}/config/name"),
        attrs,
    )


def plan_operations(data: dict[str, Any]) -> list[LinkOperation]:
    """Translate supported OpenConfig interface config into ordered link operations."""

    entries = interface_entries(data)
    operations: list[LinkOperation] = []
    mtu_operations: list[LinkOperation] = []
    enslave_operations: list[LinkOperation] = []
    state_operations: list[LinkOperation] = []

    for idx, entry in enumerate(entries):
        name = interface_name(entry, idx)
        if is_bond_interface(name, entry):
            attrs: dict[str, object] = {}
            mode = bond_mode(entry)
            if mode:
                attrs["mode"] = mode
            operations.append(LinkOperation("create_bond", name, attrs))

    for idx, entry in enumerate(entries):
        name = interface_name(entry, idx)
        master = bond_membership(entry)
        operations.extend(vlan_subinterfaces(name, entry))

        mtu = mtu_value(entry, f"interface[{idx}]")
        if mtu is not None:
            mtu_operations.append(LinkOperation("set_mtu", name, {"mtu": mtu}))

        enabled = enabled_value(entry)
        if enabled is not None:
            state_operations.append(
                LinkOperation("set_state", name, {"state": "up" if enabled else "down"})
            )

        if master is not None:
            enslave_operations.append(LinkOperation("enslave", name, {"master": master}))

    for op in list(operations):
        if op.kind == "create_vlan" and "mtu" in op.attrs:
            mtu_operations.append(LinkOperation("set_mtu", op.name, {"mtu": op.attrs["mtu"]}))

    operations.extend(mtu_operations)
    operations.extend(enslave_operations)
    operations.extend(state_operations)
    return operations


def operation_dict(op: LinkOperation) -> dict[str, object]:
    """Convert an operation to a JSON-serializable dictionary."""

    return {"kind": op.kind, "name": op.name, "attrs": op.attrs}


def print_operations(operations: list[LinkOperation]) -> None:
    """Print planned or applied operations for dry-run and verbose output."""

    print(json.dumps([operation_dict(op) for op in operations], indent=2, sort_keys=True))


class NetlinkBackend:
    """Small pyroute2 wrapper for applying and reading Linux link state."""

    def __init__(self, namespace: str | None = None) -> None:
        """Open Netlink in the host namespace or a named network namespace."""

        try:
            from pyroute2 import IPRoute, NetNS, netns  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ConfigError(
                "pyroute2 is required for Netlink operations; "
                "install it with `pip install pyroute2`"
            ) from exc

        if namespace is None:
            self.ipr = IPRoute()
            return

        namespace = validate_namespace_name(namespace)
        if namespace not in netns.listnetns():
            netns.create(namespace)
        self.ipr = NetNS(namespace)

    def close(self) -> None:
        """Close the underlying pyroute2 socket."""

        self.ipr.close()

    def link_index(self, name: str) -> int | None:
        """Return a Linux interface index by name, or ``None`` if absent."""

        matches = self.ipr.link_lookup(ifname=name)
        return int(matches[0]) if matches else None

    def require_link_index(self, name: str) -> int:
        """Return a Linux interface index or raise a configuration error."""

        index = self.link_index(name)
        if index is None:
            raise ConfigError(f"Linux link {name!r} does not exist")
        return index

    def apply(self, operations: list[LinkOperation]) -> None:
        """Apply normalized link operations in order."""

        for op in operations:
            getattr(self, f"apply_{op.kind}")(op)

    def apply_create_bond(self, op: LinkOperation) -> None:
        """Create a Linux bond link if it does not already exist."""

        if self.link_index(op.name) is not None:
            return
        kwargs: dict[str, object] = {"ifname": op.name, "kind": "bond"}
        if op.attrs.get("mode"):
            kwargs["bond_mode"] = bond_mode_id(as_str(op.attrs.get("mode"), f"{op.name}/mode"))
        self.ipr.link("add", **kwargs)

    def apply_create_vlan(self, op: LinkOperation) -> None:
        """Create a Linux VLAN link if it does not already exist."""

        if self.link_index(op.name) is not None:
            return
        parent = as_str(op.attrs.get("parent"), f"{op.name}/parent")
        vlan_id = as_int(op.attrs.get("vlan_id"), f"{op.name}/vlan_id")
        parent_index = self.require_link_index(parent)
        self.ipr.link("add", ifname=op.name, kind="vlan", link=parent_index, vlan_id=vlan_id)

    def apply_set_mtu(self, op: LinkOperation) -> None:
        """Set MTU on an existing Linux link."""

        index = self.require_link_index(op.name)
        mtu = as_int(op.attrs.get("mtu"), f"{op.name}/mtu")
        self.ipr.link("set", index=index, mtu=mtu)

    def apply_set_state(self, op: LinkOperation) -> None:
        """Set administrative link state on an existing Linux link."""

        index = self.require_link_index(op.name)
        state = as_str(op.attrs.get("state"), f"{op.name}/state")
        self.ipr.link("set", index=index, state=state)

    def apply_enslave(self, op: LinkOperation) -> None:
        """Attach an interface to a bond master."""

        index = self.require_link_index(op.name)
        master = as_str(op.attrs.get("master"), f"{op.name}/master")
        master_index = self.require_link_index(master)
        self.ipr.link("set", index=index, state="down")
        self.ipr.link("set", index=index, master=master_index)

    def read_config(self) -> dict[str, Any]:
        """Read Linux link state and return the supported OpenConfig-shaped JSON."""

        links = self.ipr.get_links()
        by_index = {int(link["index"]): link for link in links}
        entries: dict[str, dict[str, Any]] = {}

        for link in links:
            name = attr(link, "IFLA_IFNAME")
            if not name or name == "lo":
                continue
            kind = link_kind(link)
            if kind == "vlan":
                continue
            entries[name] = link_entry(link, kind)

        for link in links:
            name = attr(link, "IFLA_IFNAME")
            if not name or name == "lo":
                continue
            kind = link_kind(link)
            master_index = attr(link, "IFLA_MASTER")
            if master_index and int(master_index) in by_index:
                master = attr(by_index[int(master_index)], "IFLA_IFNAME")
                if master and link_kind(by_index[int(master_index)]) == "bond":
                    entries.setdefault(name, link_entry(link, kind))
                    entries[name]["openconfig-if-ethernet:ethernet"] = {
                        "config": {"aggregate-id": master},
                    }

            if kind != "vlan":
                continue
            parent_index = attr(link, "IFLA_LINK")
            vlan_id = vlan_id_from_link(link)
            if parent_index is None or vlan_id is None or int(parent_index) not in by_index:
                continue
            parent_name = attr(by_index[int(parent_index)], "IFLA_IFNAME")
            if not parent_name:
                continue
            parent_link = by_index[int(parent_index)]
            parent_entry = entries.setdefault(
                parent_name,
                link_entry(parent_link, link_kind(parent_link)),
            )
            subinterfaces = parent_entry.setdefault("subinterfaces", {"subinterface": []})
            subinterfaces["subinterface"].append(
                {
                    "index": vlan_id,
                    "config": {"index": vlan_id, "name": name, "mtu": attr(link, "IFLA_MTU")},
                    "openconfig-vlan:vlan": {"config": {"vlan-id": vlan_id}},
                }
            )

        return {
            ROOT_KEY: {"interface": sorted(entries.values(), key=lambda item: item["name"])}
        }


def attr(link: Any, name: str) -> Any:
    """Read a top-level pyroute2 netlink attribute from a link message."""

    if hasattr(link, "get_attr"):
        return link.get_attr(name)
    attrs = link.get("attrs", []) if isinstance(link, dict) else []
    return dict(attrs).get(name)


def nested_attr(value: Any, name: str) -> Any:
    """Read a nested pyroute2 netlink attribute from a decoded value."""

    if hasattr(value, "get_attr"):
        return value.get_attr(name)
    attrs = value.get("attrs", []) if isinstance(value, dict) else []
    return dict(attrs).get(name)


def link_info(link: Any) -> Any:
    """Return the ``IFLA_LINKINFO`` payload for a link message."""

    return attr(link, "IFLA_LINKINFO") or {}


def link_kind(link: Any) -> str | None:
    """Return the Linux link kind, such as ``bond`` or ``vlan``."""

    return nested_attr(link_info(link), "IFLA_INFO_KIND")


def vlan_id_from_link(link: Any) -> int | None:
    """Return the VLAN ID from a Linux VLAN link message."""

    info_data = nested_attr(link_info(link), "IFLA_INFO_DATA")
    vlan_id = nested_attr(info_data or {}, "IFLA_VLAN_ID")
    return int(vlan_id) if vlan_id is not None else None


def link_entry(link: Any, kind: str | None) -> dict[str, Any]:
    """Convert one non-VLAN Linux link into an OpenConfig interface entry."""

    name = attr(link, "IFLA_IFNAME")
    mtu = attr(link, "IFLA_MTU")
    flags = int(link.get("flags", 0))
    config: dict[str, Any] = {
        "name": name,
        "type": interface_type(name, kind),
        "enabled": bool(flags & 1),
    }
    if mtu is not None:
        config["mtu"] = int(mtu)
    entry: dict[str, Any] = {"name": name, "config": config}
    if kind == "bond":
        entry["openconfig-if-aggregate:aggregation"] = {"config": {"lag-type": "STATIC"}}
    return entry


def interface_type(name: str, kind: str | None) -> str:
    """Map a Linux link kind to the example's OpenConfig interface type string."""

    if name == "lo":
        return "iana-if-type:softwareLoopback"
    if kind == "bond":
        return "iana-if-type:ieee8023adLag"
    return "iana-if-type:ethernetCsmacd"


def bond_mode_id(mode: str) -> int:
    """Map a Linux bond mode name to the numeric value expected by pyroute2."""

    try:
        return BOND_MODES[mode]
    except KeyError as exc:
        raise ConfigError(f"unsupported Linux bond mode {mode!r}") from exc


def apply_command(args: argparse.Namespace) -> int:
    """Handle the ``apply`` subcommand."""

    data = load_json(args.input_json)
    if not args.no_validate:
        validate_with_xyang(data, args.schema)
    operations = plan_operations(data)
    if args.dry_run:
        print_operations(operations)
        return 0

    backend = NetlinkBackend(args.ns)
    try:
        backend.apply(operations)
    finally:
        backend.close()
    if args.verbose:
        print_operations(operations)
    return 0


def read_command(args: argparse.Namespace) -> int:
    """Handle the ``read`` subcommand."""

    backend = NetlinkBackend(args.ns)
    try:
        data = backend.read_config()
    finally:
        backend.close()
    if not args.no_validate:
        validate_with_xyang(data, args.schema)
    write_json(args.output_json, data)
    if args.verbose:
        print(f"wrote {args.output_json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the example."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser(
        "apply",
        help="configure Linux links from OpenConfig-shaped JSON",
    )
    apply_parser.add_argument("input_json", type=Path)
    apply_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip xYang validation before planning or applying",
    )
    apply_parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="YANG schema used for default validation",
    )
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned operations without sending Netlink messages",
    )
    apply_parser.add_argument(
        "--ns",
        help="operate in this network namespace, creating it if it does not exist",
    )
    apply_parser.add_argument("--verbose", action="store_true", help="print applied operations")
    apply_parser.set_defaults(func=apply_command)

    read_parser = subparsers.add_parser(
        "read",
        help="write current Linux link state as OpenConfig-shaped JSON",
    )
    read_parser.add_argument("output_json", type=Path)
    read_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip xYang validation before writing generated JSON",
    )
    read_parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="YANG schema used for default validation",
    )
    read_parser.add_argument(
        "--ns",
        help="operate in this network namespace, creating it if it does not exist",
    )
    read_parser.add_argument("--verbose", action="store_true", help="print the output path")
    read_parser.set_defaults(func=read_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line program and convert config errors to exit status."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
