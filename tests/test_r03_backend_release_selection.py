"""Selected draft backend runtime must exactly match already tested Alpine source."""
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"backend/Dockerfile.alpine-r03-candidate"
RELEASE=ROOT/"backend/Dockerfile.runtime"

class BackendReleaseSelectionTests(TestCase):
    @staticmethod
    def instructions(data):
        return [l.strip() for l in data.splitlines() if l.strip() and not l.lstrip().startswith("#")]

    def test_selected_runtime_migration_identical_to_bounded_candidate(self):
        src=SOURCE.read_text()
        expected=src.split("FROM python:3.12.16-alpine3.23@",1)[1].split("# Isolated hardened UAT parity target",1)[0]
        expected="FROM python:3.12.16-alpine3.23@"+expected
        self.assertEqual(self.instructions(RELEASE.read_text()),self.instructions(expected))

    def test_python_base_and_wheel_abi_pinning_are_present(self):
        source=RELEASE.read_text()
        self.assertIn("python:3.12.16-alpine3.23@sha256:fe32c943235f1c5748d1106dbdfa25d206355c1be1ae1e167444a7ff9dfa9422",source)
        self.assertIn("psutil==7.1.0",source)
        self.assertIn("--only-binary=:all:",source)
        self.assertNotIn("slim-trixie",source)

    def test_schema_and_api_targets_remain_nonroot(self):
        source=RELEASE.read_text()
        self.assertIn("FROM runtime_base AS migration",source)
        self.assertIn("FROM runtime_base AS runtime",source)
        self.assertIn("USER 10001:10001",source)
        self.assertIn('CMD ["python", "-m", "alembic", "upgrade", "head"]',source)
        self.assertIn('CMD ["python", "-m", "scripts.run_api"]',source)
        self.assertNotIn("COPY --from=legacy_telemetry",source)
        self.assertIn("DOES NOT patch sqlite-libs",source)
