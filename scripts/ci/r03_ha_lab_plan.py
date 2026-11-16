"""SEC001-R03 read-only preparation of owner-authorized THREE-host HA qualification.

NEVER calls SSH, Docker, Patroni, etcd, a VM API, power/fencing, or a network.
A plan is not physical-failure certification or signed DBA/Platform approval.
"""
import argparse
import json
from pathlib import Path

from r03_ha_evidence_contract import HEX, REQUIRED


def prepare(inventory):
    blockers = []
    if not isinstance(inventory, dict):
        inventory = {}
    nodes = inventory.get("hosts", [])
    if not isinstance(nodes, list):
        nodes = []
    if inventory.get("environment") != "ISOLATED_EXISTING_HOSTS":
        blockers.append("isolated existing-host lab authority not documented")
    if inventory.get("owner_authorized") is not True:
        blockers.append("owner authorization of specific existing hosts absent")
    if inventory.get("synthetic_data_only") is not True:
        blockers.append("synthetic-only data boundary absent")
    if inventory.get("production_network_connected") is not False:
        blockers.append("non-production network isolation unverified")
    ids, domains = [], []
    for node in nodes:
        if not isinstance(node, dict):
            blockers.append("invalid host inventory entry")
            continue
        ids.append(node.get("host_id"))
        domains.append(node.get("failure_domain"))
        if node.get("owner_authorized") is not True:
            blockers.append("host-specific owner authorization missing")
        if node.get("physical_host") is not True:
            blockers.append("host is not attested as physically independent")
        if not HEX.fullmatch(str(node.get("host_attestation_sha256", ""))):
            blockers.append("host attestation hash missing")
    if (
        len(nodes) != 3 or len(ids) != 3 or len(set(ids)) != 3
        or len(set(domains)) != 3 or any(not isinstance(s,str) or not s for s in ids+domains)
    ):
        blockers.append("exactly three independent host IDs/failure domains needed")
    images=inventory.get("images", {})
    if not isinstance(images, dict):
        images={}
    for role in ("postgres", "patroni", "etcd"):
        if not HEX.fullmatch(str(images.get(role,""))):
            blockers.append(f"{role} exact candidate image SHA-256 missing")
    return {
        "schema": 1,
        "status": "PREPARED_NOT_EXECUTED" if not blockers else "BLOCKED",
        "blockers": blockers,
        "approved_hosts": ids if not blockers else [],
        "scenario_plan": [
            {
                "id": f"HA-{i+1:02d}",
                "scenario": scenario,
                "execution": "MANUAL_IN_AUTHORIZED_ISOLATED_LAB_ONLY",
                "status": "NOT_EXECUTED",
                "evidence_artifact_sha256": None,
            }
            for i,scenario in enumerate(REQUIRED)
        ],
        "contains_host_commands": False,
        "physical_fencing_executed": False,
        "independent_dba_certification": "NOT_RECEIVED",
        "security_platform_certification": "NOT_RECEIVED",
        "release_eligible": False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--inventory",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    inventory={}
    if args.inventory:
        inventory=json.loads(args.inventory.read_text())
    result=prepare(inventory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
