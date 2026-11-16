"""SEC001-R03: LOCAL read-only validation and proposed config render; no host contact."""
import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path

DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]+@sha256:[a-f0-9]{64}$")
NODE = re.compile(r"^[a-z][a-z0-9-]{2,45}$")


def blockers(inv):
    if not isinstance(inv, dict):
        return ["inventory must be a JSON object"]
    issues = []
    for k, expected in (("schema", 1), ("environment", "ISOLATED_EXISTING_HOSTS"),
                        ("owner_authorized", True), ("synthetic_data_only", True),
                        ("production_network_connected", False)):
        if inv.get(k) != expected:
            issues.append(f"{k}: missing required owner-authorized value")
    if not NODE.fullmatch(str(inv.get("cluster_name", ""))):
        issues.append("safe cluster name missing")
    try:
        net = ipaddress.ip_network(inv.get("network_cidr", "invalid"), strict=True)
        if net.version != 4 or not net.is_private or not any(net.subnet_of(ipaddress.ip_network(c))
               for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            issues.append("real isolated RFC1918 subnet missing")
    except ValueError:
        net = None
        issues.append("invalid subnet")
    hosts = inv.get("hosts", [])
    if not isinstance(hosts, list) or len(hosts) != 3 or not all(isinstance(h, dict) for h in hosts):
        return issues + ["exactly three host records required"]
    for k in ("node_name", "host_id", "failure_domain", "address"):
        values = [h.get(k) for h in hosts]
        if any(not isinstance(v, str) or not v for v in values) or len(set(values)) != 3:
            issues.append(f"three distinct {k} required")
    for h in hosts:
        name = str(h.get("node_name", "<unidentified>"))
        if not NODE.fullmatch(name):
            issues.append(f"{name}: unsafe name")
        if h.get("owner_authorized") is not True or h.get("physical_host") is not True:
            issues.append(f"{name}: physical host not individually authorized")
        if h.get("os") != "Ubuntu 24.04 LTS":
            issues.append(f"{name}: OS not verified")
        if not DIGEST.fullmatch(str(h.get("host_attestation_sha256", ""))):
            issues.append(f"{name}: signed attestation evidence missing")
        for k, minimum in (("vcpus", 8), ("memory_gib", 32), ("data_disk_gib", 200)):
            v = h.get(k)
            if type(v) is not int or v < minimum:
                issues.append(f"{name}: {k} below owner-approved minimum")
        try:
            addr = ipaddress.ip_address(h.get("address", "invalid"))
            if net is None or addr not in net or not addr.is_private or addr.is_multicast:
                issues.append(f"{name}: IP outside approved lab subnet")
        except ValueError:
            issues.append(f"{name}: invalid host IP")
    images = inv.get("images", {})
    if not isinstance(images, dict):
        images = {}
    for r in ("postgres", "patroni", "etcd"):
        if not DIGEST.fullmatch(str(images.get(r, ""))):
            issues.append(f"{r}: immutable image config SHA absent")
    for r in ("patroni_image_ref", "etcd_image_ref"):
        if not PIN.fullmatch(str(images.get(r, ""))):
            issues.append(f"{r}: immutable OCI manifest lock absent")
    tls = inv.get("tls", {})
    if not isinstance(tls, dict) or not DIGEST.fullmatch(str(tls.get("independent_ca_fingerprint_sha256", ""))) or tls.get("san_and_client_auth_verified") is not True:
        issues.append("independently validated TLS CA and peer SAN proof missing")
    return issues


def render(inv, node, output_dir):
    issues = blockers(inv)
    if issues:
        raise ValueError("Blocked before configuration render: " + "; ".join(issues))
    host = next((h for h in inv["hosts"] if h["node_name"] == node), None)
    if host is None:
        raise ValueError("node not present in authorized inventory")
    out = Path(output_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError("refusing overwrite of existing operator files")
    out.mkdir(parents=True, exist_ok=True)
    ip = host["address"]
    etcd_hosts = ",".join(f"{h['address']}:2379" for h in inv["hosts"])
    cfg = {
        "scope": inv["cluster_name"], "namespace": "/aptron-lab/", "name": node,
        "restapi": {"listen": f"{ip}:8008", "connect_address": f"{ip}:8008",
                    "certfile": "/run/lab-patroni-tls/server.crt", "keyfile": "/run/lab-patroni-tls/server.key",
                    "cafile": "/run/lab-patroni-tls/ca.crt",
                    # Patroni REST mutating AND safe GET endpoints require mTLS.
                    # Ctl client certs are mandatory when verify_client=required.
                    "verify_client": "required",
                    "allowlist_include_members": True,
                    "authentication": {"username": "lab-patroni-api"}},
        "ctl": {"cacert": "/run/lab-patroni-tls/ca.crt",
                "certfile": "/run/lab-patroni-tls/client.crt",
                "keyfile": "/run/lab-patroni-tls/client.key"},
        "etcd3": {"hosts": etcd_hosts, "protocol": "https",
                  "cacert": "/run/lab-patroni-tls/ca.crt",
                  "cert": "/run/lab-patroni-tls/client.crt", "key": "/run/lab-patroni-tls/client.key"},
        "bootstrap": {"dcs": {"ttl": 30, "loop_wait": 10, "retry_timeout": 10,
                               "synchronous_mode": True, "synchronous_mode_strict": True,
                               "synchronous_node_count": 1, "check_timeline": True,
                               "postgresql": {"use_pg_rewind": True, "use_slots": True,
                                              "parameters": {"wal_level": "replica", "hot_standby": "on",
                                                             "synchronous_commit": "on", "wal_log_hints": "on",
                                                             "max_wal_senders": 10, "max_replication_slots": 10,
                                                             "ssl": "on", "ssl_min_protocol_version": "TLSv1.2",
                                                             "ssl_cert_file": "/run/lab-patroni-tls/server.crt",
                                                             "ssl_key_file": "/run/lab-patroni-tls/server.key",
                                                             "ssl_ca_file": "/run/lab-patroni-tls/ca.crt"}}},
                       "initdb": [{"encoding": "UTF8"}, "data-checksums"],
                       "pg_hba": [f"hostssl replication replicator {inv['network_cidr']} scram-sha-256",
                                  f"hostssl all all {inv['network_cidr']} scram-sha-256"]},
        "postgresql": {"listen": f"{ip}:5432", "connect_address": f"{ip}:5432",
                       "data_dir": "/var/lib/postgresql/data", "bin_dir": "/usr/local/bin",
                       "authentication": {"superuser": {"username": "postgres"},
                                          "replication": {"username": "replicator"}}},
        "watchdog": {"mode": "required", "device": "/dev/watchdog", "safety_margin": 5}
    }
    cluster = ",".join(f"{h['node_name']}=https://{h['address']}:2380" for h in inv["hosts"])
    env = "\n".join((f"NODE_NAME={node}", f"NODE_IP={ip}", f"CLUSTER_NAME={inv['cluster_name']}",
                      f"INITIAL_CLUSTER={cluster}",
                      f"PATRONI_IMAGE={inv['images']['patroni_image_ref']}",
                      f"ETCD_IMAGE={inv['images']['etcd_image_ref']}")) + "\n"
    config_file = out / "patroni.yaml"
    config_file.write_text(json.dumps(cfg, indent=2) + "\n")
    config_file.chmod(0o600)
    env_file = out / "node.env"
    env_file.write_text(env)
    env_file.chmod(0o600)
    report = {"status": "CONFIG_RENDERED_NOT_DEPLOYED",
              "config_sha256": "sha256:" + hashlib.sha256(config_file.read_bytes()).hexdigest(),
              "node": node, "fencing_approval": "NOT_VERIFIED",
              "independent_host_attestation_verified": False, "release_eligible": False}
    (out / "render-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--node")
    p.add_argument("--output-dir", type=Path)
    args = p.parse_args()
    inventory = json.loads(args.inventory.read_text())
    if args.node is None:
        issues = blockers(inventory)
        print(json.dumps({"status": "BLOCKED" if issues else "READY_FOR_CONFIG_RENDER_ONLY",
                          "blockers": issues, "physical_ha_certified": False,
                          "deployment_authorized": False}, indent=2))
    else:
        if args.output_dir is None:
            p.error("--output-dir required when --node given")
        print(json.dumps(render(inventory, args.node, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
