"""SEC001-R03: offline, non-installing Alpine APK signature verification.

Only invoke after Security provides an independently authenticated public key,
its out-of-band SHA-256 and actual vendor-supplied APK bytes. No network, no
supplier account, no package installation and NO legal/release approval.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{64}$")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_offline(apk, key, apk_sha256, trusted_key_sha256, trust_reference, apk_executable="apk"):
    verdict = {
        "schema": 1,
        "supplier": "Root.io (claimed, not independently approved)",
        "status": "BLOCKED",
        "signature_verified": False,
        "vendor_identity_approved": False,
        "apk_install_authorized": False,
        "license_notice_approved": False,
        "release_eligible": False,
        "signing_key_trust_reference": trust_reference,
        "blockers": [],
    }
    reasons = verdict["blockers"]
    apk = Path(apk)
    key = Path(key)
    if not isinstance(apk_sha256, str) or not SHA.fullmatch(apk_sha256):
        reasons.append("expected APK SHA-256 is missing or malformed")
    if not isinstance(trusted_key_sha256, str) or not SHA.fullmatch(trusted_key_sha256):
        reasons.append("out-of-band key SHA-256 is missing or malformed")
    if not isinstance(trust_reference, str) or not trust_reference.strip():
        reasons.append("independent supplier trust-source reference is missing")
    if not apk.is_file() or not apk.name.endswith(".apk") or apk.is_symlink():
        reasons.append("offline regular APK file missing")
    if not key.is_file() or not key.name.endswith(".pub") or key.is_symlink():
        reasons.append("offline regular vendor public-key file missing")
    if reasons:
        return verdict
    observed_apk = digest(apk)
    observed_key = digest(key)
    verdict["observed_apk_sha256"] = observed_apk
    verdict["observed_key_sha256"] = observed_key
    if observed_apk != apk_sha256:
        reasons.append("APK bytes do not match independently provided digest")
    if observed_key != trusted_key_sha256:
        reasons.append("vendor signing key differs from out-of-band fingerprint")
    if reasons:
        return verdict
    executable = shutil.which(apk_executable)
    if not executable:
        reasons.append("trusted Alpine apk-tools verifier unavailable; no fallback")
        return verdict
    with tempfile.TemporaryDirectory(prefix="sec001-r03-apk-keys-") as directory:
        keys = Path(directory)
        shutil.copyfile(key, keys / key.name)
        # apk verify is strictly read-only. No --allow-untrusted, add, upgrade,
        # execution of supplied APK scripts, repository access or network.
        result = subprocess.run(
            [executable, "--network=no", "--keys-dir", str(keys), "verify", str(apk.resolve())],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    if result.returncode != 0:
        reasons.append("Alpine apk verify rejected package integrity/signature")
        return verdict
    verdict["signature_verified"] = True
    verdict["status"] = "SIGNATURE_VERIFIED_REVIEW_REQUIRED"
    reasons.extend([
        "Security/Platform must attest independent Root.io key identity and patch/source provenance",
        "Legal must approve patched APK redistribution, NOTICE and source obligations",
        "Exact final image still needs Syft/CycloneDX/Grype and compatibility qualification",
    ])
    return verdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--offline-apk", type=Path, required=True)
    p.add_argument("--trusted-public-key", type=Path, required=True)
    p.add_argument("--apk-sha256", required=True)
    p.add_argument("--trusted-key-sha256", required=True)
    p.add_argument("--independent-trust-reference", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    outcome = verify_offline(
        args.offline_apk,
        args.trusted_public_key,
        args.apk_sha256,
        args.trusted_key_sha256,
        args.independent_trust_reference,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome, indent=2) + "\n")
    print(json.dumps(outcome, indent=2))
    if not outcome["signature_verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
