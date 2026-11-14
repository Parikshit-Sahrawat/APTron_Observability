"""Negative contract tests, synthetic fixtures are never certification evidence."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import r03_ha_evidence_contract as gate  # noqa: E402

D = "sha256:" + "1" * 64


def illustrative_fixture():
    return {
        "lab_type": "INDEPENDENT_MULTI_HOST",
        "pg_image_id": D,
        "patroni_image_id": D,
        "etcd_image_id": D,
        "physical_hosts": [
            {
                "host_id": f"synthetic-{i}",
                "failure_domain": f"synthetic-az-{i}",
                "host_attestation_sha256": D,
            }
            for i in range(3)
        ],
        "scenarios": [
            {"name": name, "result": "PASS", "artifact_sha256": D}
            for name in gate.REQUIRED
        ],
        "durability": {
            "acknowledged_critical_events": 100,
            "acknowledged_event_loss": 0,
            "critical_identity_duplicates": 0,
        },
    }


class HAEvidenceGuardTests(unittest.TestCase):
    def test_no_evidence_is_blocked_and_never_certified(self):
        result = gate.assess({})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["independent_dba_approval"], "NOT_VERIFIED")

    def test_independent_test_records_only_ready_for_human_review(self):
        result = gate.assess(illustrative_fixture())
        self.assertEqual(result["status"], "READY_FOR_INDEPENDENT_DBA_REVIEW")
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["license_notice_approval"], "NOT_VERIFIED")

    def test_single_host_docker_containers_are_not_three_failure_domains(self):
        payload = illustrative_fixture()
        for node in payload["physical_hosts"]:
            node["host_id"] = "one-github-runner"
            node["failure_domain"] = "one-github-runner"
        payload["lab_type"] = "SINGLE_HOST_DOCKER"
        self.assertEqual(gate.assess(payload)["status"], "BLOCKED")

    def test_no_duplicate_or_lost_acknowledged_critical_events(self):
        for key, value in [
            ("acknowledged_critical_events", 0),
            ("acknowledged_event_loss", 1),
            ("critical_identity_duplicates", 1),
        ]:
            payload = illustrative_fixture()
            payload["durability"][key] = value
            self.assertEqual(gate.assess(payload)["status"], "BLOCKED")

    def test_all_scenarios_are_mandatory_with_real_evidence_hash(self):
        for name in gate.REQUIRED:
            payload = illustrative_fixture()
            payload["scenarios"] = [
                row for row in payload["scenarios"] if row["name"] != name
            ]
            self.assertEqual(gate.assess(payload)["status"], "BLOCKED")
        payload = illustrative_fixture()
        payload["scenarios"][0]["artifact_sha256"] = "sha256:unverified"
        self.assertEqual(gate.assess(payload)["status"], "BLOCKED")

    def test_missing_immutable_image_identity_fails_closed(self):
        payload = illustrative_fixture()
        payload["pg_image_id"] = "postgres:17-alpine"
        self.assertEqual(gate.assess(payload)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
