"""Temporary staging exceptions never authorize production or changed findings."""

import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import staging_image_gate as gate
spec = importlib.util.spec_from_file_location("staging_run", ROOT / "scripts/staging/run_disposable.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class StagingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / ".ci/staging-exceptions.json").read_text())
        self.now = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
        record = next(x for x in self.policy["exceptions"] if x["kind"] == "vulnerability")
        self.role = record["roles"][0]
        self.finding = record["findings"][0]
        f = self.finding
        self.scan = {"matches": [{"vulnerability": {k: f[k] for k in ("id", "namespace", "severity")},
                                 "artifact": {"name": f["package"], "version": f["version"], "type": f["type"]}}]}

    def test_known_findings_are_retained_and_deferred_never_passed(self):
        snapshot = copy.deepcopy(self.scan)
        result = gate.assess(self.policy, self.role, self.scan, self.now)
        self.assertEqual(result["status"], "STAGING_ELIGIBLE_WITH_EXCEPTIONS")
        self.assertEqual(result["severe_matches_unresolved"], 1)
        self.assertEqual(result["legal_status"], "DEFERRED_NOT_PASSED")
        self.assertFalse(result["production_eligible"])
        self.assertEqual(self.scan, snapshot)

    def test_expiry_missing_owner_and_production_scope_stop_staging(self):
        for change in ("expired", "missing-owner", "production"):
            with self.subTest(change=change):
                policy = copy.deepcopy(self.policy)
                if change == "expired":
                    policy["expires_at"] = "2026-11-15T00:00:00Z"
                elif change == "missing-owner":
                    next(x for x in policy["exceptions"] if x["kind"] == "legal")["owner"] = ""
                else:
                    policy["scope"] = "production"
                with self.assertRaises(ValueError):
                    gate.assess(policy, self.role, self.scan, self.now)

    def test_new_advisory_version_or_severity_is_not_a_blanket_exception(self):
        for path, value in (("id", "CVE-NEW"), ("severity", "Critical"), ("version", "unreviewed-version")):
            scan = copy.deepcopy(self.scan)
            if path == "severity" and self.finding["severity"] == "Critical":
                value = "Unknown"
            scan["matches"][0]["artifact" if path == "version" else "vulnerability"][path] = value
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "New or changed"):
                gate.assess(self.policy, self.role, scan, self.now)

    def test_missing_evidence_and_production_profile_fail_before_deployment(self):
        with self.assertRaises(ValueError):
            gate.evaluate(ROOT / "missing-staging-evidence", "a" * 40, self.policy, profile="production")
        with self.assertRaises(OSError):
            gate.evaluate(ROOT / "missing-staging-evidence", "a" * 40, self.policy)

    def test_isolation_rejects_public_ports_host_mounts_and_mutable_images(self):
        images = {n: "sha256:" + "a" * 64 for n in ("postgres", "migration", "api", "worker", "frontend")}
        base = {"services": {n: {"image": i, "networks": {"staging": {}}} for n, i in images.items()},
                "networks": {"staging": {"internal": True}}, "volumes": {}}
        runner.isolation(base, images)
        for patch in ({"ports": [{"host_ip": "0.0.0.0"}]},
                      {"volumes": [{"type": "bind", "source": "/var/run/docker.sock"}]},
                      {"privileged": True}, {"image": "aptron:latest"},
                      {"network_mode": "host"}):
            config = copy.deepcopy(base)
            config["services"]["api"].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                runner.isolation(config, images)
