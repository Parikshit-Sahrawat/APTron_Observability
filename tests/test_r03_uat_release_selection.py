"""Draft UAT image stays source-equivalent to the tested legacy pin candidate."""
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"backend/Dockerfile.alpine-r03-candidate"
RELEASE=ROOT/"backend/Dockerfile.uat"

class UATReleaseSelectionTests(TestCase):
    @staticmethod
    def commands(s):
        return [r.strip() for r in s.splitlines() if r.strip() and not r.lstrip().startswith("#")]

    def test_build_source_matches_previously_qualified_legacy_compat_uat(self):
        source=SOURCE.read_text()
        source=source.split("# SEC001-R03D: isolated UAT with a rebuilt",1)[0]
        self.assertEqual(self.commands(RELEASE.read_text()),self.commands(source))

    def test_legacy_otel_pin_not_silently_upgraded(self):
        s=RELEASE.read_text()
        self.assertIn("otel/opentelemetry-collector-contrib:0.123.0@sha256:e39311df1f3d941923c00da79ac7ba6269124a870ee87e3c3ad24d60f8aee4d2",s)
        self.assertIn("COPY --from=legacy_telemetry /otelcol-contrib /usr/local/bin/otelcol-contrib",s)
        self.assertNotIn("COPY --from=patched_telemetry",s)
        self.assertEqual([x for x in s.splitlines() if x.startswith("FROM ")][-1],"FROM runtime_base AS uat")

    def test_migration_and_runtime_remain_nonroot_and_installer_free(self):
        s=RELEASE.read_text()
        self.assertIn("USER 10001:10001",s)
        self.assertIn("COPY alembic.ini /app/alembic.ini",s)
        self.assertIn("COPY migrations/ /app/migrations/",s)
        self.assertIn("rm -rf /usr/local/lib/python3.12/site-packages/pip",s)
        self.assertIn('CMD ["python", "-m", "scripts.run_api"]',s)
        self.assertIn("DO NOT fix inherited Collector CVEs",s)
