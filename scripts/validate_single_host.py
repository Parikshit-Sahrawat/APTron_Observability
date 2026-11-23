"""Validate resolved Compose JSON from stdin without printing secrets.

Usage: docker compose ... config --format json | python scripts/validate_single_host.py
This is structural validation, not image approval or a deployment authorization.
"""

import ipaddress
import json
from pathlib import PurePosixPath
import re
import sys


def validate(config):
    services = config["services"]
    if set(services) != {"gateway", "engine", "postgres"}:
        raise ValueError("Exactly three central services required")
    for name, service in services.items():
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", service["image"]):
            raise ValueError("Immutable image reference required")
        if service.get("privileged") or service.get("network_mode") == "host":
            raise ValueError("Privileged or host networking forbidden")
        if name != "gateway" and service.get("ports"):
            raise ValueError("Only HTTPS gateway may publish a port")
    ports = services["gateway"].get("ports", [])
    if len(ports) != 1 or ports[0]["target"] != 8443:
        raise ValueError("One TLS gateway port required")
    pgdata = services["postgres"]["volumes"]
    if len(pgdata) != 1 or (
        pgdata[0]["type"] != "bind"
        or not PurePosixPath(pgdata[0]["source"]).is_absolute()
        or pgdata[0]["target"] != "/var/lib/postgresql/data"
        or pgdata[0].get("bind", {}).get("create_host_path", False)
    ):
        raise ValueError("Pre-created persistent PostgreSQL bind mount required")
    engine = services["engine"]
    if engine["command"] != ["python", "-m", "scripts.run_single_host"]:
        raise ValueError("Supervised engine command required")
    if engine["environment"]["ENVIRONMENT"] != "production":
        raise ValueError("Production security checks must remain enabled")
    proxy = ipaddress.ip_address(engine["environment"]["TRUSTED_PROXY_IPS"])
    address = services["gateway"]["networks"]["ingress"]["ipv4_address"]
    subnet = config["networks"]["ingress"]["ipam"]["config"][0]["subnet"]
    if proxy != ipaddress.ip_address(address) or proxy not in ipaddress.ip_network(
        subnet
    ):
        raise ValueError("Exact gateway proxy trust and subnet must agree")
    if not config["networks"]["database"]["internal"]:
        raise ValueError("Database network must be internal")


def main():
    try:
        validate(json.load(sys.stdin))
    except (KeyError, IndexError, TypeError, ValueError):
        print(
            "Single-host configuration rejected; review deployment contract",
            file=sys.stderr,
        )
        return 1
    print(
        "Single-host structure validated; image and runtime acceptance still required"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
