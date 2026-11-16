"""Patched UAT is a digest-bound disposable test, not automatic pin promotion."""
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
DOCKERFILE=ROOT/"backend/Dockerfile.alpine-r03-candidate"

class PatchedUATBoundaryTests(TestCase):
    def test_legacy_uat_target_retains_old_collector_for_comparison(self):
        data=DOCKERFILE.read_text()
        legacy=data.split("FROM runtime_base AS uat\n",1)[1].split("FROM runtime_base AS uat_patched",1)[0]
        self.assertIn("COPY --from=legacy_telemetry /otelcol-contrib", legacy)
        self.assertIn("USER 10001:10001", legacy)

    def test_patched_uat_requires_external_named_build_context(self):
        data=DOCKERFILE.read_text()
        patched=data.split("FROM runtime_base AS uat_patched\n",1)[1]
        self.assertIn("COPY --from=patched_telemetry /otelcol-contrib", patched)
        self.assertNotIn("legacy_telemetry", patched)
        self.assertIn("ARG PATCHED_COLLECTOR_SHA256", patched)
        self.assertIn("sha256sum -c -", patched)
        self.assertIn("grep -F '0.165.0'", patched)
        self.assertIn("USER 10001:10001", patched)

    def test_patched_uat_retains_real_api_and_schema_migration_workload(self):
        s=DOCKERFILE.read_text().split("FROM runtime_base AS uat_patched\n",1)[1]
        for required in ["COPY migrations/ /app/migrations/","COPY alembic.ini /app/alembic.ini",
                         "ENV OPSCONTROL_OTEL_BINARY=/usr/local/bin/otelcol-contrib",
                         'CMD ["python", "-m", "scripts.run_api"]']:
            self.assertIn(required,s)
