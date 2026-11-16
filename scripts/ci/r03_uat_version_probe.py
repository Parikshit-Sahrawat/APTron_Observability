"""Measure the existing application pin against patched UAT; no pin changes."""

import hashlib
import json
from pathlib import Path
import re
import subprocess


def measure(binary, runtime_version, validator):
    version = subprocess.run([str(binary), "--version"], check=True,
                             capture_output=True, text=True, timeout=15)
    if not re.search(r"(?<![\d.])0\.165\.0(?![\d.])", version.stdout):
        raise ValueError("Expected rebuilt 0.165.0 candidate")
    if runtime_version != "0.123.0":
        raise ValueError("Active pin changed; re-review this qualification")
    try:
        validator("service: {}\n", binary=str(binary))
    except ValueError as error:
        if str(error) != "Selected Collector binary version does not match " + runtime_version:
            raise
    else:
        raise ValueError("Unexpected version acceptance; investigate before promotion")
    with binary.open("rb") as stream:
        binary_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "schema": 1, "status": "BLOCKED_APPLICATION_VERSION_NEGOTIATION",
        "candidate_version": "0.165.0", "required_application_version": runtime_version,
        "binary_sha256": binary_hash,
        "application_accepts_candidate": False,
        "observed_rejection": "Selected Collector binary version does not match " + runtime_version,
        "next_requirement": "Separately reviewed version negotiation, generated configurations and Agent compatibility before runtime replacement",
        "release_eligible": False,
    }


if __name__ == "__main__":
    from app.telemetry.configuration import RUNTIME_VERSION, validate_binary
    print(json.dumps(measure(Path("/usr/local/bin/otelcol-contrib"),
                             RUNTIME_VERSION, validate_binary), indent=2))
