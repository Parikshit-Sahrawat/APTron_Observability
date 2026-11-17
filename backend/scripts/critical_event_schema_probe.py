"""Real constraints in the owner-authorized disposable staging database only."""

import json
import os
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models import Organization, DataSource, Collector
from app.security.models import WorkerIdentity
from app.telemetry.models import ManagedAgent
from app.critical_events.models import TABLES, registry


def migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0039_critical_event_storage.py"
    )
    spec = importlib.util.spec_from_file_location("critical_storage_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exercise_downgrade(db, *, populated):
    # PostgreSQL DDL is transactional: restore even the empty schema by rolling
    # back this SAVEPOINT. Never touch alembic_version or legacy migrations.
    migration = migration_module()
    legacy = db.execute(
        text("SELECT id, code, active FROM organizations ORDER BY id")
    ).all()
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    savepoint = db.begin_nested()
    try:
        with Operations.context(MigrationContext.configure(db.connection())):
            if populated:
                try:
                    migration.downgrade()
                except RuntimeError as error:
                    assert "evidence is retained" in str(error)
                else:
                    raise AssertionError("Populated evidence downgrade allowed")
            else:
                migration.downgrade()
                assert (
                    db.scalar(text("SELECT to_regclass('event_identity_registry')"))
                    is None
                )
    finally:
        savepoint.rollback()
    for table in TABLES:
        assert db.scalar(text("SELECT to_regclass(:name)"), {"name": table.name})
    assert (
        db.execute(text("SELECT id, code, active FROM organizations ORDER BY id")).all()
        == legacy
    )
    assert db.scalar(text("SELECT version_num FROM alembic_version")) == revision


def main():
    if (
        os.environ.get("APTRON_DISPOSABLE_STAGING") != "1"
        or os.environ.get("ENVIRONMENT") != "test"
    ):
        raise RuntimeError("Disposable synthetic staging required")
    checks = []
    with SessionLocal() as db:
        if db.scalar(text("SELECT current_database()")) != "aptron_staging":
            raise RuntimeError("Wrong database for disposable constraint probe")
        orgs = db.scalars(
            select(Organization)
            .where(Organization.code.in_(["LAB-N", "LAB-S"]))
            .order_by(Organization.code)
        ).all()
        if len(orgs) != 2:
            raise RuntimeError("Synthetic tenant fixture absent")
        exercise_downgrade(db, populated=False)
        checks.append("empty-downgrade-restores-schema-and-legacy-data")
        source = DataSource(
            id=uuid4(),
            organization_id=orgs[0].id,
            name="Critical schema fixture",
            source_type="LINUX",
        )
        db.add(source)
        db.flush()
        event = dict(
            event_key=uuid4(),
            tenant_id=orgs[0].id,
            source_id=source.id,
            event_id="schema-event",
            schema_version="1.0",
            canonicalization_version="1.0",
            payload_sha256=b"a" * 32,
            first_seen_at=datetime.now(timezone.utc),
        )
        db.execute(registry.insert().values(**event))
        checks.append("insert-exact-identity")
        cases = [
            (
                "duplicate-natural-key",
                registry.insert().values(**{**event, "event_key": uuid4()}),
            ),
            (
                "short-hash",
                registry.insert().values(
                    **{
                        **event,
                        "event_key": uuid4(),
                        "event_id": "short",
                        "payload_sha256": b"bad",
                    }
                ),
            ),
            (
                "cross-customer-source",
                registry.insert().values(
                    **{
                        **event,
                        "event_key": uuid4(),
                        "tenant_id": orgs[1].id,
                        "event_id": "forged",
                    }
                ),
            ),
            (
                "immutable-hash",
                registry.update()
                .where(registry.c.event_key == event["event_key"])
                .values(payload_sha256=b"b" * 32),
            ),
            (
                "retained-identity",
                registry.delete().where(registry.c.event_key == event["event_key"]),
            ),
        ]
        now = datetime.now(timezone.utc)
        tables = {table.name: table for table in TABLES}
        # Real installation identities for two different sources of the same
        # customer, and one foreign-customer installation. No credentials issued.
        installations = []
        for index, org in enumerate([orgs[0], orgs[0], orgs[1]]):
            bound_source = source
            if index:
                bound_source = DataSource(
                    id=uuid4(),
                    organization_id=org.id,
                    name="Critical schema source " + str(index),
                    source_type="LINUX",
                )
                db.add(bound_source)
                db.flush()
            worker = WorkerIdentity(
                id=uuid4(),
                organization_id=org.id,
                name="Critical schema worker " + str(index),
                token_hash=uuid4().hex * 2,
                expires_at=now + timedelta(hours=1),
            )
            db.add(worker)
            db.flush()
            collector = Collector(
                id=uuid4(),
                data_source_id=bound_source.id,
                remote_worker_id=worker.id,
                name="Critical schema collector",
                collector_type="LINUX",
            )
            db.add(collector)
            db.flush()
            installation = ManagedAgent(
                id=uuid4(),
                organization_id=org.id,
                collector_id=collector.id,
                worker_id=worker.id,
                hostname="synthetic-invalid-host",
                version="schema-only",
                runtime_version="none",
            )
            db.add(installation)
            db.flush()
            installations.append(installation)
        inbox = tables["protected_event_inbox"]
        inbox_values = dict(
            event_key=event["event_key"],
            canonical_payload=b"synthetic",
            collector_id=installations[0].id,
            protected_received_at=now,
            protection_state="UNVERIFIED",
            protection_policy_id="test-no-ack",
        )
        for index in (1, 2):
            cases.append(
                (
                    "collector-source-owner-" + str(index),
                    inbox.insert().values(
                        **{**inbox_values, "collector_id": installations[index].id}
                    ),
                )
            )
        # Insert the matching installation only after the negative INSERTs below.
        conflict = tables["identity_conflict_audit"]
        gap = tables["delivery_gap_audit"]
        conflict_values = dict(
            conflict_id=uuid4(),
            tenant_id=orgs[0].id,
            source_id=source.id,
            event_id="schema-event",
            existing_hash=b"a" * 32,
            received_hash=b"b" * 32,
            detected_at=now,
            evidence_reference="synthetic-only",
        )
        gap_values = dict(
            gap_id=uuid4(),
            tenant_id=orgs[0].id,
            source_id=source.id,
            detected_at=now,
            reason_code="SYNTHETIC",
            recovery_state="UNVERIFIED",
        )
        for table, values in ((conflict, conflict_values), (gap, gap_values)):
            cases.append(
                (
                    table.name + "-source-owner",
                    table.insert().values(**{**values, "tenant_id": orgs[1].id}),
                )
            )
        for name, statement in cases:
            try:
                with db.begin_nested():
                    db.execute(statement)
            except IntegrityError:
                checks.append(name)
            else:
                raise AssertionError(
                    "Database accepted invalid critical event: " + name
                )
        db.execute(inbox.insert().values(**inbox_values))
        checks.append("matching-installation-inbox")
        ledger = tables["critical_event_ledger"]
        db.execute(
            ledger.insert().values(
                event_key=event["event_key"],
                connector_type="SYNTHETIC",
                execution_id="schema-only",
                event_type="FAILURE",
                occurred_at=now,
                observed_at=now,
                normalized_event=b"synthetic",
            )
        )
        claim = tables["durable_receipt_claim"]
        receipt_id = uuid4()
        db.execute(
            claim.insert().values(
                receipt_id=receipt_id,
                event_key=event["event_key"],
                receipt_class="HOST_PROTECTED",
                receipt_version="1.0",
                durability_policy_id="test-no-ack",
                claim_created_at=now,
                current_reaffirmation_generation=1,
            )
        )
        reaffirmation = tables["receipt_reaffirmation"]
        db.execute(
            reaffirmation.insert().values(
                receipt_id=receipt_id,
                generation=1,
                barrier_token=uuid4(),
                barrier_committed_at=now,
            )
        )
        finalization = tables["protected_finalization_outbox"]
        db.execute(
            finalization.insert().values(
                event_key=event["event_key"], state="UNVERIFIED", claim_generation=1
            )
        )
        processing = tables["processing_outbox"]
        db.execute(
            processing.insert().values(
                outbox_id=uuid4(),
                event_key=event["event_key"],
                obligation_type="synthetic",
                state="UNVERIFIED",
                claim_generation=1,
                external_idempotency_key="synthetic-no-side-effect",
            )
        )
        db.execute(conflict.insert().values(**conflict_values))
        db.execute(gap.insert().values(**gap_values))
        # These uncommitted fixture claims are not signed or returned. This probe
        # proves constraints only, never replication, durability or issuance.
        immutable = []
        for table in TABLES:
            immutable.append((table.name + "-delete-denied", table.delete()))
        for table, values in (
            (inbox, {"canonical_payload": b"changed"}),
            (ledger, {"normalized_event": b"changed"}),
            (claim, {"durability_policy_id": "forged"}),
            (reaffirmation, {"barrier_token": uuid4()}),
            (conflict, {"evidence_reference": "changed"}),
            (gap, {"reason_code": "changed"}),
            (finalization, {"event_key": uuid4()}),
            (processing, {"external_idempotency_key": "changed"}),
            (claim, {"current_reaffirmation_generation": 0}),
            (finalization, {"claim_generation": 0}),
            (processing, {"claim_generation": 0}),
        ):
            immutable.append(
                (
                    table.name + "-immutable-or-regression",
                    table.update().values(**values),
                )
            )
        for name, statement in immutable:
            try:
                with db.begin_nested():
                    db.execute(statement)
            except IntegrityError:
                checks.append(name)
            else:
                raise AssertionError("Database allowed evidence mutation: " + name)
        # Permitted operational fields remain writable without changing evidence.
        for table, values in (
            (inbox, {"protection_state": "STILL_UNVERIFIED"}),
            (finalization, {"state": "RETRY", "claim_generation": 2}),
            (processing, {"state": "RETRY", "claim_generation": 2}),
        ):
            db.execute(table.update().values(**values))
        checks.append("operational-state-only-updates")
        exercise_downgrade(db, populated=True)
        checks.append("populated-evidence-downgrade-refused-legacy-preserved")
        assert (
            db.scalar(
                select(registry.c.payload_sha256).where(
                    registry.c.event_key == event["event_key"]
                )
            )
            == b"a" * 32
        )
        db.rollback()  # All fixture writes are disposable and uncommitted.
    print(
        json.dumps(
            {
                "status": "PASS",
                "checks": checks,
                "production_eligible": False,
                "ha_certified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
