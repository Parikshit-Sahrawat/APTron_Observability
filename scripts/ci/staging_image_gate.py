"""Staging-only exception decision. Production security gate is independent."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from image_coverage import ROOT, contract, verify
from security_manifest import verify_evidence


class UncoveredSevereFindings(ValueError):
    def __init__(self, match_count):
        super().__init__("New or changed severe finding requires owner review")
        self.match_count = match_count


def fingerprint(match):
    v, a = match["vulnerability"], match["artifact"]
    return {"id": v["id"], "namespace": v.get("namespace", ""),
            "package": a["name"], "version": a.get("version", ""),
            "type": a.get("type", ""), "severity": v.get("severity", "Unknown")}


def applicable(policy, kind, role, now):
    result = []
    for item in policy["exceptions"]:
        if item.get("kind") != kind or role not in item.get("roles", []):
            continue
        for key in ("id", "owner", "approval_reference", "scope", "risk", "exit_criteria"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError("Incomplete accountable exception: " + key)
        expiry = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        if (expiry.tzinfo is None or expiry <= now or
                item["status"] != "APPROVED_TEMPORARY_STAGING_EXCEPTION"):
            raise ValueError("Expired or unapproved staging exception")
        result.append(item)
    return result


def assess(policy, role, scan, now):
    if policy.get("scope") != "disposable-ci-staging" or policy.get("production_approved") is not False:
        raise ValueError("Policy cannot authorize production or another environment")
    if policy.get("schema") != 1 or policy.get("policy") != "APTRON_STAGING_FIRST_V1":
        raise ValueError("Unknown staging policy")
    expiry = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= now:
        raise ValueError("Staging policy expired")
    if role not in policy["inventory_roles"]:
        raise ValueError("Unapproved staging image role")
    legal = applicable(policy, "legal", role, now)
    ha = applicable(policy, "physical_ha", "deployment", now)
    if not legal or not ha:
        raise ValueError("Legal or physical HA deferral is missing")
    allowed = applicable(policy, "vulnerability", role, now)
    known = {json.dumps(f, sort_keys=True) for item in allowed for f in item["findings"]}
    severe = [fingerprint(m) for m in scan["matches"] if
              m["vulnerability"].get("severity", "Unknown").lower() in {"critical", "high", "unknown"}]
    uncovered_count = sum(json.dumps(f, sort_keys=True) not in known for f in severe)
    if uncovered_count:
        raise UncoveredSevereFindings(uncovered_count)
    return {"role": role, "status": "STAGING_ELIGIBLE_WITH_EXCEPTIONS",
            "severe_matches_unresolved": len(severe),
            "exception_ids": [x["id"] for x in legal + ha + (allowed if severe else [])],
            "legal_status": "DEFERRED_NOT_PASSED", "physical_ha_status": "DEFERRED_NOT_PASSED",
            "production_eligible": False}


def evaluate(directory, source, policy, profile="deployment", root=ROOT):
    if profile not in {"deployment", "inventory"}:
        raise ValueError("Only staging deployment or inventory profiles are allowed")
    roles = policy["staging_roles"] if profile == "deployment" else policy["inventory_roles"]
    expected = {"uat-backend", "frontend", "postgres"} if profile == "deployment" else {r["role"] for r in contract(root)}
    if set(roles) != expected or len(roles) != len(expected):
        raise ValueError("Staging evidence role coverage mismatch")
    rows = {r["role"]: r for r in contract(root)}
    results = []
    for role in roles:
        path = directory / ("image-evidence-" + role)
        binding = verify(path, rows[role], source, root)
        verify_evidence(path)  # Keep checksum, exact-image and fresh scanner DB safeguards.
        scan = json.loads((path / "grype.json").read_text())
        result = assess(policy, role, scan, datetime.now(timezone.utc))
        result["image_config_id"] = binding["image_id"]
        results.append(result)
    return {"schema": 1, "status": "STAGING_ELIGIBLE_WITH_EXCEPTIONS", "source_sha": source,
            "scope": "disposable-ci-staging", "profile": profile, "images": results,
            "deployment_completed": False, "production_eligible": False,
            "expires_at": policy["expires_at"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--policy", type=Path, default=ROOT / ".ci/staging-exceptions.json")
    parser.add_argument("--profile", choices=["deployment", "inventory"], default="deployment")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate(args.directory, args.source, json.loads(args.policy.read_text()), args.profile)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {"status": "STAGING_BLOCKED", "error": str(error), "production_eligible": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "STAGING_ELIGIBLE_WITH_EXCEPTIONS":
        raise SystemExit(1)
