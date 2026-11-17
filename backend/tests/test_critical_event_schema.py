"""Frozen PostgreSQL DDL contracts; actual engine checks run in disposable staging."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects.postgresql import dialect
from app.critical_events.models import TABLES

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "critical_migration",
    ROOT / "backend/migrations/versions/0039_critical_event_storage.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class CriticalEventSchemaTests(unittest.TestCase):
    def test_frozen_migration_matches_nine_models_without_mutating_legacy_tables(self):
        self.assertEqual(len(TABLES), 9)
        for table in TABLES:
            self.assertIn(
                str(CreateTable(table).compile(dialect=dialect())).strip(),
                migration.DDL,
            )
        self.assertEqual(migration.down_revision, "0038_k8s_cluster_associations")
        self.assertTrue(
            all(s.startswith(("CREATE TABLE ", "CREATE INDEX ")) for s in migration.DDL)
        )
        self.assertTrue(all("CASCADE" not in s for s in migration.DDL))

    def test_identity_hash_receipt_and_side_effect_uniqueness_are_database_constraints(
        self,
    ):
        ddl = "\n".join(migration.DDL)
        for required in [
            "UNIQUE (tenant_id, source_id, event_id)",
            "octet_length(payload_sha256) = 32",
            "UNIQUE (event_key, receipt_class)",
            "UNIQUE (external_idempotency_key)",
            "generation > 0",
            "receipt_class IN ('HOST_PROTECTED','CENTRAL_DURABLE')",
        ]:
            self.assertIn(required, ddl)
        self.assertNotIn("LOCAL_ACCEPTED", ddl)

    def test_historical_evidence_is_immutable_and_destructive_downgrade_is_refused(
        self,
    ):
        guards = "\n".join(migration.GUARDS)
        self.assertIn("BEFORE UPDATE OR DELETE ON event_identity_registry", guards)
        self.assertIn("BEFORE UPDATE OR DELETE ON critical_event_ledger", guards)
        self.assertIn("source owner mismatch", guards)
        self.assertIn("recovery source mismatch", guards)
        self.assertIn("Collector source owner mismatch", guards)
        self.assertIn("FOR SHARE OF m,c,w,s", guards)
        for table in ("identity_conflict_audit", "delivery_gap_audit"):
            self.assertIn(table + "_source_owner BEFORE INSERT ON " + table, guards)
        self.assertIn("m.organization_id=r.tenant_id", guards)
        self.assertIn("c.data_source_id=r.source_id", guards)
        self.assertIn("w.organization_id=r.tenant_id", guards)
        connection = Mock()
        connection.exec_driver_sql.return_value.scalar.return_value = True
        with patch.object(
            migration.op, "get_context", return_value=SimpleNamespace(as_sql=False)
        ), patch.object(
            migration.op, "get_bind", return_value=connection
        ), patch.object(
            migration.op, "drop_table"
        ) as drop:
            with self.assertRaisesRegex(RuntimeError, "evidence is retained"):
                migration.downgrade()
            drop.assert_not_called()
        connection.exec_driver_sql.return_value.scalar.return_value = False
        with patch.object(
            migration.op, "get_context", return_value=SimpleNamespace(as_sql=False)
        ), patch.object(
            migration.op, "get_bind", return_value=connection
        ), patch.object(
            migration.op, "drop_table"
        ) as drop, patch.object(
            migration.op, "execute"
        ):
            migration.downgrade()
            self.assertEqual(drop.call_count, 9)
            connection.exec_driver_sql.assert_any_call(
                "LOCK TABLE event_identity_registry, protected_event_inbox, protected_finalization_outbox, critical_event_ledger, durable_receipt_claim, receipt_reaffirmation, processing_outbox, identity_conflict_audit, delivery_gap_audit IN ACCESS EXCLUSIVE MODE"
            )
