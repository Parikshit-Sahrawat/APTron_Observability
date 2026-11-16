"""Candidate measurement must not report compatibility through a rejected pin."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("uat_probe", Path(__file__).resolve().parents[1] / "scripts/ci/r03_uat_version_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class UATVersionProbeTests(unittest.TestCase):
    def test_actual_version_command_and_expected_rejection_report_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "candidate"
            binary.write_text("#!/bin/sh\necho 'otelcol-contrib version 0.165.0'\n")
            binary.chmod(0o700)
            def reject(text, binary):
                raise ValueError("Selected Collector binary version does not match 0.123.0")
            report = probe.measure(binary, "0.123.0", reject)
            self.assertEqual(report["status"], "BLOCKED_APPLICATION_VERSION_NEGOTIATION")
            self.assertFalse(report["application_accepts_candidate"])
            self.assertFalse(report["release_eligible"])
            with self.assertRaisesRegex(ValueError, "Unexpected version acceptance"):
                probe.measure(binary, "0.123.0", lambda *a, **kw: True)
            with self.assertRaisesRegex(ValueError, "Active pin changed"):
                probe.measure(binary, "0.165.0", reject)
