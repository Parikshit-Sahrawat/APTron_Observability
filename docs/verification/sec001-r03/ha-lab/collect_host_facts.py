"""Operator-run read-only physical host sizing observations, NOT attestation."""
import argparse
import json
import os
import platform
import shutil
from pathlib import Path


def assess(release, meminfo, logical_cpus, filesystem_bytes):
    os_values = {}
    for line in release.splitlines():
        if "=" in line and not line.startswith("#"):
            k,v = line.split("=",1)
            os_values[k] = v.strip('"')
    memory_kib = next((int(line.split()[1]) for line in meminfo.splitlines()
                       if line.startswith("MemTotal:")), 0)
    mem_gib = round(memory_kib / 1024**2, 2)
    disk_gib = round(filesystem_bytes / 1024**3, 2)
    warnings = []
    if os_values.get("ID") != "ubuntu" or os_values.get("VERSION_ID") != "24.04":
        warnings.append("Ubuntu 24.04 not confirmed")
    if logical_cpus < 8:
        warnings.append("8 logical CPU functional baseline not met")
    if mem_gib < 30:
        warnings.append("nominal 32 GiB memory not confirmed")
    if disk_gib < 180:
        warnings.append("nominal 200 GiB data SSD not confirmed")
    if platform.machine() not in ("x86_64", "amd64"):
        warnings.append("linux/amd64 architecture not confirmed")
    return {"schema":1,"status":"UNATTESTED_HOST_FACTS_REVIEW_REQUIRED",
            "logical_cpus":logical_cpus,"memory_gib_observed":mem_gib,
            "data_filesystem_gib_observed":disk_gib,"os_id":os_values.get("ID"),
            "os_version":os_values.get("VERSION_ID"),"warnings":warnings,
            "physical_failure_domain_verified":False,
            "individual_host_authorization_verified":False,
            "independent_certificate_or_fencing_approval":False,
            "release_eligible":False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--existing-data-mount",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if not args.existing_data_mount.is_dir():
        parser.error("existing data mount required; no filesystem creation")
    report=assess(Path("/etc/os-release").read_text(),
                  Path("/proc/meminfo").read_text(),os.cpu_count() or 0,
                  shutil.disk_usage(args.existing_data_mount).total)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"warnings":report["warnings"],
                      "physical_hosts_certified":False}))


if __name__=="__main__":
    main()
