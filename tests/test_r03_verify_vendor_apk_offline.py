"""Negative and mocked-only unit tests: NO real Root.io APK or key is used."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import r03_verify_vendor_apk_offline as v  # noqa: E402


class OfflineAPKVerificationTests(unittest.TestCase):
    def test_absent_package_and_key_never_authorize_install(self):
        result = v.verify_offline(
            "/missing/rootio-patched.apk", "/missing/vendor.rsa.pub", "0" * 64, "1" * 64, "independent-ticket"
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["apk_install_authorized"])
        self.assertFalse(result["signature_verified"])

    def test_untrusted_fingerprint_blocks_before_invoking_apk_tools(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            apk = root / "sqlite-libs.apk"
            key = root / "trusted.rsa.pub"
            apk.write_bytes(b"synthetic test, NOT A REAL APK")
            key.write_bytes(b"synthetic test, NOT A REAL PUBLIC KEY")
            with patch.object(v.subprocess, "run", side_effect=AssertionError("never execute")):
                result = v.verify_offline(
                    apk, key, hashlib.sha256(apk.read_bytes()).hexdigest(),
                    "e" * 64, "independent-ticket"
                )
            self.assertIn("vendor signing key differs", result["blockers"][0])
            self.assertFalse(result["signature_verified"])

    def test_untrusted_self_declared_key_without_independent_reference_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            apk = root / "sqlite-libs.apk"
            key = root / "trusted.rsa.pub"
            apk.write_bytes(b"not an apk")
            key.write_bytes(b"not a key")
            result = v.verify_offline(
                apk, key, hashlib.sha256(apk.read_bytes()).hexdigest(),
                hashlib.sha256(key.read_bytes()).hexdigest(), ""
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["vendor_identity_approved"])

    def test_even_mocked_success_never_grants_supplier_license_or_release(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            apk = root / "sqlite-libs.apk"
            key = root / "vendor.rsa.pub"
            apk.write_bytes(b"unit-test-only-not-a-signed-apk")
            key.write_bytes(b"unit-test-only-not-trusted")
            with patch.object(v.shutil, "which", return_value="/usr/bin/apk"):
                with patch.object(v.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as cmd:
                    outcome = v.verify_offline(
                        apk, key, hashlib.sha256(apk.read_bytes()).hexdigest(),
                        hashlib.sha256(key.read_bytes()).hexdigest(), "out-of-band-review-placeholder"
                    )
            args = cmd.call_args.args[0]
            self.assertIn("verify", args)
            self.assertIn("--network=no", args)
            self.assertNotIn("add", args)
            self.assertNotIn("--allow-untrusted", args)
            self.assertFalse(outcome["apk_install_authorized"])
            self.assertFalse(outcome["license_notice_approved"])
            self.assertFalse(outcome["release_eligible"])


if __name__ == "__main__":
    unittest.main()
