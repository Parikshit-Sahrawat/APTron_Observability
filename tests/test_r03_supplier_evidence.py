"""SEC001-R03 supplier preflight negative tests: never authorizes unreviewed APKs."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import r03_supplier_evidence as supplier  # noqa: E402


class SupplierEvidenceTests(unittest.TestCase):
    def good_claims(self):
        return {
            "supplier": "Root.io",
            "distribution": "alpine-3.23",
            "architecture": "x86_64",
            "sqlite_package_version": supplier.EXPECTED,
            "cve_patch_claims": sorted(supplier.CVES),
            "trusted_signing_key_sha256": "a" * 64,
            "apk_sha256": hashlib.sha256(b"synthetic-not-real-apk").hexdigest(),
        }

    def test_missing_supplier_evidence_blocks_without_installing(self):
        result = supplier.assess({})
        self.assertFalse(result["apk_install_authorized"])
        self.assertEqual(result["status"], "BLOCKED_INDEPENDENT_REVIEW_REQUIRED")

    def test_missing_apk_and_signer_blocks(self):
        result = supplier.assess(self.good_claims())
        self.assertIn("offline exact APK bytes were not provided", result["blockers"])
        self.assertFalse(result["release_eligible"])

    def test_mismatched_apk_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            apk = Path(root) / "synthetic.sqlite-libs.apk"
            apk.write_bytes(b"digest-does-not-match")
            verdict = supplier.assess(self.good_claims(), apk)
            self.assertIn("offline APK bytes do not match supplied SHA-256", verdict["blockers"])

    def test_all_four_cves_and_architecture_are_mandatory(self):
        for field, wrong in [
            ("architecture", "aarch64"),
            ("sqlite_package_version", "3.53.4-r0"),
            ("cve_patch_claims", ["CVE-2026-119373"]),
            ("trusted_signing_key_sha256", "not-a-key-digest"),
        ]:
            claims = copy.deepcopy(self.good_claims())
            claims[field] = wrong
            verdict = supplier.assess(claims)
            self.assertGreater(len(verdict["blockers"]), 3)
            self.assertFalse(verdict["patch_qualification_passed"])

    def test_even_matching_synthetic_bytes_never_sign_off_a_vendor(self):
        with tempfile.TemporaryDirectory() as root:
            apk = Path(root) / "synthetic.sqlite-libs.apk"
            apk.write_bytes(b"synthetic-not-real-apk")
            verdict = supplier.assess(self.good_claims(), apk)
            self.assertEqual(verdict["observed_apk_sha256"], self.good_claims()["apk_sha256"])
            self.assertFalse(verdict["supplier_approved"])
            self.assertFalse(verdict["apk_install_authorized"])
            self.assertFalse(verdict["license_notice_approved"])
            self.assertFalse(verdict["release_eligible"])


if __name__ == "__main__":
    unittest.main()
