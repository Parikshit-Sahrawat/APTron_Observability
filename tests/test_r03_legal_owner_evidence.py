"""Signed final OCI image approvals cannot be inferred from owner workbook review."""
import json
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"docs/verification/sec001-r03/LEGAL_EVIDENCE_OWNER_TRIAGE_2026-11-16.json"


class LegalOwnerEvidenceTests(TestCase):
    def test_all_historic_roles_present(self):
        d=json.loads(PATH.read_text())
        self.assertEqual(len(d["images"]),8)
        self.assertEqual(len({i["role"] for i in d["images"]}),8)
        self.assertEqual(sum(i["components"] for i in d["images"]),2506)
        self.assertEqual(d["reported_components"],2506)

    def test_source_and_hash_binding_are_present(self):
        d=json.loads(PATH.read_text())
        for row in d["images"]:
            self.assertEqual(row["source_sha"],d["source_sha"])
            self.assertEqual(len(row["evidence_zip_sha256"]),64)
            self.assertTrue(row["image_config_id"].startswith("sha256:"))

    def test_owner_approval_never_claims_independent_legal_signoff(self):
        d=json.loads(PATH.read_text())
        self.assertEqual(d["approved_owner_workbook_scope"],"TECHNICAL_TRIAGE_BASELINE_ONLY")
        self.assertFalse(d["legal_signoff_complete"])
        self.assertFalse(d["release_eligible"])
        for row in d["images"]:
            self.assertEqual(row["license_notice_status"],"PENDING_ACCOUNTABLE_REVIEW")
            self.assertIsNone(row["signature_reference"])
            self.assertIsNone(row["final_published_oci_manifest_digest"])
