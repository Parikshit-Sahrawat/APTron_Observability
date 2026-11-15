"""SEC001-R03 Root.io supply-chain intake — no vendor download or installation.

This is a fail-closed evidence *preflight* for security and legal reviewers.
A JSON claim cannot prove an APK signature, cryptographic trust or entitlement.
Only an independently completed supplier review may authorize ingestion.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

DIGEST = re.compile(r"^[0-9a-f]{64}$")
CVES = {
    "CVE-2026-119373",
    "CVE-2026-119374",
    "CVE-2026-119379",
    "CVE-2026-119586",
}
EXPECTED = "3.53.4-r00073"


def assess(evidence, package_path=None):
    if not isinstance(evidence, dict):
        evidence = {}
    blockers = []
    if evidence.get("supplier") != "Root.io":
        blockers.append("supplier identity has not been independently verified")
    if evidence.get("distribution") != "alpine-3.23":
        blockers.append("Alpine 3.23 distribution not verified")
    if evidence.get("architecture") != "x86_64":
        blockers.append("supported x86_64 architecture not verified")
    if evidence.get("sqlite_package_version") != EXPECTED:
        blockers.append("pinned vendor-patched SQLite version not verified")
    try:
        listed = set(evidence.get("cve_patch_claims", []))
    except TypeError:
        listed = set()
    if listed != CVES:
        blockers.append("complete four-advisory patch statement missing")
    key_digest = evidence.get("trusted_signing_key_sha256")
    if not isinstance(key_digest, str) or not DIGEST.fullmatch(key_digest):
        blockers.append("vendor repository signing-key fingerprint absent")
    expected_sha = evidence.get("apk_sha256")
    if not isinstance(expected_sha, str) or not DIGEST.fullmatch(expected_sha):
        blockers.append("exact patched APK SHA-256 absent")
    path = Path(package_path) if package_path is not None else None
    actual_sha = None
    if path is None or not path.is_file() or not path.name.endswith(".apk"):
        blockers.append("offline exact APK bytes were not provided")
    else:
        actual_sha = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if actual_sha != expected_sha:
            blockers.append("offline APK bytes do not match supplied SHA-256")
    # Statements in a submitted JSON file do NOT authenticate signer authority.
    blockers.extend([
        "vendor repository APK signature and trust anchor require independent verification",
        "supplier entitlement / patch provenance requires Security and Platform signoff",
        "redistribution/source-offer/NOTICE needs accountable legal review",
    ])
    return {
        "schema": 1,
        "status": "BLOCKED_INDEPENDENT_REVIEW_REQUIRED",
        "supplier": "Root.io",
        "target": "Alpine 3.23 x86_64 SQLite 3.53.4-r00073",
        "expected_cves": sorted(CVES),
        "apk_present": path is not None and path.is_file(),
        "observed_apk_sha256": actual_sha,
        "blockers": blockers,
        "supplier_approved": False,
        "apk_install_authorized": False,
        "patch_qualification_passed": False,
        "license_notice_approved": False,
        "release_eligible": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--metadata", type=Path)
    p.add_argument("--offline-apk", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    manifest = {}
    if args.metadata:
        manifest = json.loads(args.metadata.read_text())
    result = assess(manifest, args.offline_apk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
