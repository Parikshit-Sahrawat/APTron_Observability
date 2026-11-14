"""SEC001-R03 HA evidence contract. Never substitutes for a DBA's signed decision.

A single GitHub-hosted Docker runner cannot certify loss of a physical host,
power/VM fencing, or an independently hosted etcd quorum. Fail closed until
at least three real failure domains are evidenced by authorized testing.
"""
import argparse
import json
import re
from pathlib import Path

HEX = re.compile(r"sha256:[0-9a-f]{64}\Z")
REQUIRED = (
    "etcd_three_voters_and_quorum",
    "synchronous_pg_replication",
    "primary_host_loss",
    "standby_host_loss",
    "partition_and_fencing",
    "stale_leader_rejoin",
    "acknowledged_events_preserved",
    "populated_backup_restore",
    "post_failover_recovery_and_rejoin",
)


def assess(evidence):
    blockers = []
    if not isinstance(evidence, dict):
        evidence = {}
    for field in ("pg_image_id", "patroni_image_id", "etcd_image_id"):
        if not HEX.fullmatch(str(evidence.get(field, ""))):
            blockers.append(f"{field}: missing exact SHA-256 image identity")
    nodes = evidence.get("physical_hosts", [])
    if not isinstance(nodes, list):
        nodes = []
    hosts = [n.get("host_id") for n in nodes if isinstance(n, dict)]
    domains = [n.get("failure_domain") for n in nodes if isinstance(n, dict)]
    attestations = [
        n.get("host_attestation_sha256") for n in nodes if isinstance(n, dict)
    ]
    if (
        len(nodes) < 3
        or len(set(hosts)) < 3
        or len(set(domains)) < 3
        or any(not isinstance(x, str) or not x.strip() for x in hosts + domains)
        or len(attestations) != len(nodes)
        or any(not HEX.fullmatch(str(x)) for x in attestations)
    ):
        blockers.append("three independently attested physical failure domains missing")
    observations = evidence.get("scenarios", [])
    if not isinstance(observations, list):
        observations = []
    lookup = {
        x.get("name"): x
        for x in observations
        if isinstance(x, dict) and isinstance(x.get("name"), str)
    }
    for scenario in REQUIRED:
        item = lookup.get(scenario, {})
        if item.get("result") != "PASS" or not HEX.fullmatch(
            str(item.get("artifact_sha256", ""))
        ):
            blockers.append(f"{scenario}: passing immutable test artifact missing")
    counts = evidence.get("durability", {})
    if not isinstance(counts, dict):
        counts = {}
    accepted = counts.get("acknowledged_critical_events")
    loss = counts.get("acknowledged_event_loss")
    duplicates = counts.get("critical_identity_duplicates")
    if (
        type(accepted) is not int
        or accepted <= 0
        or type(loss) is not int
        or loss != 0
        or type(duplicates) is not int
        or duplicates != 0
    ):
        blockers.append("durability: nonzero acknowledged sample, zero loss and zero duplicates not evidenced")
    if evidence.get("lab_type") != "INDEPENDENT_MULTI_HOST":
        blockers.append("lab_type: Docker-on-one-host cannot prove host-failure durability")
    return {
        "schema": 1,
        "status": "READY_FOR_INDEPENDENT_DBA_REVIEW" if not blockers else "BLOCKED",
        "blocking_reasons": blockers,
        "required_scenarios": list(REQUIRED),
        "independent_dba_approval": "NOT_VERIFIED",
        "fencing_approval": "NOT_VERIFIED",
        "license_notice_approval": "NOT_VERIFIED",
        "release_eligible": False,
        "automatic_merge_allowed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-qualification", action="store_true")
    args = p.parse_args()
    payload = {}
    if args.evidence and args.evidence.is_file():
        payload = json.loads(args.evidence.read_text())
    verdict = assess(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    if args.require_qualification and verdict["status"] != "READY_FOR_INDEPENDENT_DBA_REVIEW":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
