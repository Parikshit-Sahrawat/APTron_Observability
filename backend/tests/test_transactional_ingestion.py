"""Independent real connections to the runner-owned PG17 and ephemeral test PKI."""

import json
import os
import ssl
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

from sqlalchemy import create_engine, event as hooks, func, select, text, update
from app.critical_events.identity import (
    EventIdentity,
    IdentityConflict,
    UnauthorizedSource,
)
from app.critical_events.ingestion import (
    Submission,
    IngestionService,
    CommitIndeterminate,
    ProtectionPolicy,
)
from app.critical_events.models import (
    registry,
    inbox,
    finalization,
    conflicts,
    claims,
    ledger,
)
from app.critical_events.registration import register_certificate, revoke_certificate
from app.models import Collector, Organization
from scripts.collector_certificate_probe import fixture, issue, connection


@unittest.skipUnless(
    os.environ.get("APTRON_TXN_LAB") == "1", "Owned transactional PG17 fixture required"
)
class TransactionalIngestionTests(unittest.TestCase):
    def setUp(self):
        self.lab = ExitStack()
        self.addCleanup(self.lab.close)
        self.db = create_engine(os.environ["DATABASE_URL"])
        self.lab.callback(self.db.dispose)
        with self.db.connect() as db:
            self.assertEqual(
                db.scalar(text("select current_database()")), "s03_auth_lab"
            )
            self.assertEqual(
                db.scalar(text("show synchronous_standby_names")), "s03_test_standby"
            )
        self.scope, self.other_source = fixture(self.db)
        self.directory = Path(self.lab.enter_context(tempfile.TemporaryDirectory()))
        for name in ("ca", "localhost", "client", "new"):
            issue(self.directory, name)
        self.enroll("client", 0)
        self.policy = ProtectionPolicy(
            "disposable-local",
            "lab",
            "s03_auth_lab",
            int(os.environ["APTRON_LAB_SYSTEM_ID"]),
            os.environ["APTRON_LAB_PRIMARY_ADDRESS"],
            5432,
        )
        self.service = self.build_service(self.db, self.policy)
        self.submit = self.peer()
        self.event = self.make_event()

    def build_service(self, engine, policy):
        return IngestionService(
            engine,
            policy=policy,
            server_certificate=self.directory / "localhost.pem",
            server_key=self.directory / "localhost.key",
            client_ca=self.directory / "ca.pem",
        )

    def peer(self, name="client"):
        return self.lab.enter_context(connection(self.service, self.directory, name))

    def enroll(self, name, generation, db=None):
        def register(conn):
            register_certificate(
                conn,
                **self.scope,
                certificate_pem=(self.directory / (name + ".pem")).read_text(),
                expected_generation=generation,
            )

        if db is None:
            with self.db.begin() as conn:
                register(conn)
        else:
            register(db)

    def make_event(self):
        data = b'{"state":"failed"}'
        return Submission(
            EventIdentity(
                self.scope["tenant_id"],
                self.scope["source_id"],
                uuid4().hex,
                sha256(data).digest(),
                "1.0",
                "1.0",
            ),
            self.scope["installation_id"],
            "lab",
            data,
        )

    def count(self, table):
        with self.db.connect() as db:
            return db.scalar(select(func.count()).select_from(table))

    @contextmanager
    def listen(self, callback, name="after_cursor_execute"):
        hooks.listen(self.db, name, callback)
        try:
            yield
        finally:
            hooks.remove(self.db, name, callback)

    def test_validate_authority_digest_and_versions(self):
        identity = self.event.identity
        for attr, value in (("tenant_id", uuid4()), ("source_id", self.other_source)):
            with self.assertRaises(UnauthorizedSource):
                self.submit(
                    replace(self.event, identity=replace(identity, **{attr: value}))
                )
        for changes in (dict(collector_id=uuid4()), dict(environment="prod")):
            with self.assertRaises(UnauthorizedSource):
                self.submit(replace(self.event, **changes))
        for changes in (
            dict(schema_version="2.0"),
            dict(canonicalization_version="2.0"),
            dict(payload_sha256=b"x" * 32),
        ):
            with self.assertRaises(ValueError):
                self.submit(replace(self.event, identity=replace(identity, **changes)))
        # Existing historical identity of a different version is never updated.
        with self.db.begin() as db:
            key = uuid4()
            db.execute(
                registry.insert().values(
                    event_key=key,
                    tenant_id=identity.tenant_id,
                    source_id=identity.source_id,
                    event_id=identity.event_id,
                    payload_sha256=identity.payload_sha256,
                    schema_version="legacy",
                    canonicalization_version="1.0",
                    first_seen_at=func.now(),
                )
            )
            db.execute(
                inbox.insert().values(
                    event_key=key,
                    canonical_payload=self.event.canonical_payload,
                    collector_id=self.event.collector_id,
                    protected_received_at=func.now(),
                    protection_state="PENDING",
                    protection_policy_id="local",
                )
            )
            db.execute(finalization.insert().values(event_key=key, state="PENDING"))
        with self.assertRaises(IdentityConflict):
            self.submit(self.event)
        with self.db.connect() as db:
            self.assertEqual(
                db.scalar(
                    select(registry.c.schema_version).where(registry.c.event_key == key)
                ),
                "legacy",
            )

    def test_conflict_audit_owns_only_denied_attempt(self):
        key = self.submit(self.event)
        rejected = replace(
            self.event,
            canonical_payload=b"denied",
            identity=replace(
                self.event.identity, payload_sha256=sha256(b"denied").digest()
            ),
        )
        marker = uuid4()
        table = Organization.__table__
        with self.db.connect() as caller:
            tx = caller.begin()
            caller.execute(
                table.insert().values(id=marker, name=marker.hex, code=marker.hex)
            )
            with self.assertRaises(IdentityConflict):
                self.submit(rejected)
            with self.db.connect() as independent:
                self.assertIsNone(
                    independent.scalar(select(table.c.id).where(table.c.id == marker))
                )
                self.assertEqual(
                    independent.scalar(
                        select(conflicts.c.received_hash).where(
                            conflicts.c.evidence_reference == str(key)
                        )
                    ),
                    rejected.identity.payload_sha256,
                )
            tx.rollback()

    def test_submission_bounds_and_connection_lifetime(self):
        for payload in (b"", b"x" * (1024 * 1024 + 1)):
            with self.assertRaises(ValueError):
                self.submit(
                    replace(
                        self.event,
                        canonical_payload=payload,
                        identity=replace(
                            self.event.identity, payload_sha256=sha256(payload).digest()
                        ),
                    )
                )
        with connection(self.service, self.directory, "client") as submit:
            with self.assertRaises(ValueError):
                submit(self.scope)
        with self.assertRaises(UnauthorizedSource):
            submit(self.event)

    def test_rollback_after_each_write(self):
        tables = (registry, inbox, finalization, claims, ledger)
        before = [self.count(t) for t in tables]
        for table in tables[:3]:

            def fail(conn, cursor, sql, *args):
                if sql.startswith("INSERT INTO " + table.name + " "):
                    raise RuntimeError("Injected write failure")

            with self.listen(fail), self.assertRaisesRegex(RuntimeError, "Injected"):
                self.submit(self.event)
            self.assertEqual([self.count(t) for t in tables], before)

    def while_locked(self, contender):
        # Pause after all three writes, while registration locks are still held.
        pause, release = Event(), Event()
        holder = []

        def suspend(conn, cursor, sql, *args):
            if (
                sql.startswith("INSERT INTO protected_finalization_outbox ")
                and not holder
            ):
                holder.append(conn.connection.driver_connection.info.backend_pid)
                pause.set()
                if not release.wait(12):
                    raise TimeoutError("Commit not released")

        with self.listen(suspend), ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.submit, self.event)
            try:
                self.assertTrue(pause.wait(5))
                second = pool.submit(contender)
                self.wait_db(
                    "select exists(select from pg_stat_activity where :pid=any(pg_blocking_pids(pid)))",
                    holder[0],
                )
            finally:
                release.set()
            return first.result(timeout=6), second

    def wait_db(self, sql, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.db.connect() as db:
                if db.scalar(text(sql), {"pid": pid}):
                    return
            time.sleep(0.02)
        self.fail("Expected PostgreSQL wait was never observed")

    def test_concurrent_retry_and_conflict(self):
        second = self.peer()
        counts = [self.count(t) for t in (registry, inbox, finalization)]
        key, retry = self.while_locked(lambda: second(self.event))
        self.assertEqual(key, retry.result())
        self.event = self.make_event()
        different = replace(
            self.event,
            canonical_payload=b"other",
            identity=replace(
                self.event.identity, payload_sha256=sha256(b"other").digest()
            ),
        )
        key, denied = self.while_locked(lambda: second(different))
        with self.assertRaises(IdentityConflict):
            denied.result()
        with self.db.connect() as db:
            evidence = (
                db.execute(
                    select(conflicts).where(conflicts.c.evidence_reference == str(key))
                )
                .mappings()
                .one()
            )
            self.assertEqual(evidence.received_hash, different.identity.payload_sha256)
            self.assertEqual(evidence.existing_hash, self.event.identity.payload_sha256)
            self.assertEqual(
                db.scalar(
                    select(inbox.c.canonical_payload).where(inbox.c.event_key == key)
                ),
                self.event.canonical_payload,
            )
        self.assertEqual(
            [self.count(t) for t in (registry, inbox, finalization)],
            [n + 2 for n in counts],
        )

    def test_registration_mutation_races(self):
        cert = self.directory / "client.pem"

        fingerprint = sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).digest()
        config = update(Collector.__table__).where(
            Collector.id == self.scope["configuration_id"]
        )
        for action in ("rotate", "disable", "reassign", "revoke"):
            with self.subTest(action=action):

                def change():
                    with self.db.begin() as db:
                        if action == "rotate":
                            self.enroll("new", self.generation, db)
                        elif action == "revoke":
                            revoke_certificate(db, self.fingerprint)
                        else:
                            values = (
                                dict(enabled=False)
                                if action == "disable"
                                else dict(data_source_id=self.other_source)
                            )
                            db.execute(config.values(**values))

                if action == "rotate":
                    self.generation = 1
                    self.fingerprint = fingerprint
                self.event = self.make_event()
                _, changed = self.while_locked(change)
                changed.result()
                with self.assertRaises(UnauthorizedSource):
                    self.submit(self.event)
                if action == "rotate":
                    self.submit = self.peer("new")
                elif action != "revoke":
                    with self.db.begin() as db:
                        db.execute(
                            config.values(
                                enabled=True, data_source_id=self.scope["source_id"]
                            )
                        )
                    name = uuid4().hex
                    issue(self.directory, name)
                    self.enroll(name, self.generation)
                    self.fingerprint = sha256(
                        ssl.PEM_cert_to_DER_cert(
                            (self.directory / (name + ".pem")).read_text()
                        )
                    ).digest()
                    self.submit = self.peer(name)
                self.generation += 1

    def test_commit_wait_cancellation_disconnect_and_replay(self):
        from queue import Queue

        for terminate in (False, True):
            self.event = self.make_event()
            pid = Queue()

            def synchronous(db):
                db.exec_driver_sql("SET LOCAL synchronous_commit = remote_apply")
                pid.put(db.connection.driver_connection.info.backend_pid)

            # A separate engine observes and interrupts only our fixture session.
            observer = create_engine(
                os.environ["DATABASE_URL"], isolation_level="AUTOCOMMIT"
            )
            try:
                with self.listen(synchronous, "begin"), ThreadPoolExecutor(1) as pool:
                    future = pool.submit(self.submit, self.event)
                    worker = pid.get(timeout=5)
                    with observer.connect() as db:
                        deadline = time.monotonic() + 5
                        while (
                            db.scalar(
                                text(
                                    "select wait_event from pg_stat_activity where pid=:p"
                                ),
                                dict(p=worker),
                            )
                            != "SyncRep"
                        ):
                            if time.monotonic() > deadline:
                                db.execute(
                                    text("select pg_terminate_backend(:p)"),
                                    dict(p=worker),
                                )
                                self.fail(
                                    "COMMIT did not reach synchronous replication wait"
                                )
                            time.sleep(0.02)
                        command = (
                            "pg_terminate_backend" if terminate else "pg_cancel_backend"
                        )
                        self.assertTrue(
                            db.scalar(text(f"select {command}(:p)"), dict(p=worker))
                        )
                    with self.assertRaises(CommitIndeterminate):
                        future.result(timeout=6)
            finally:
                observer.dispose()
            key = self.submit(self.event)
            self.assertEqual(key, self.submit(self.event))
            with self.db.connect() as db:
                self.assertIsNone(
                    db.scalar(
                        select(claims.c.receipt_id).where(claims.c.event_key == key)
                    )
                )

    def scoped_peer(self, engine, policy):
        service = self.build_service(engine, policy)
        return self.lab.enter_context(connection(service, self.directory, "client"))

    def test_protection_policy_and_primary(self):
        with self.assertRaises(ValueError):
            replace(self.policy, policy_id="CENTRAL_DURABLE")
        for policy in (
            replace(self.policy, system_identifier=self.policy.system_identifier + 1),
            replace(self.policy, database="another"),
            replace(self.policy, server_address="192.0.2.1"),
            replace(self.policy, server_port=5433),
        ):
            with self.assertRaisesRegex(RuntimeError, "violate protection policy"):
                self.scoped_peer(self.db, policy)(self.event)
        with self.assertRaises(UnauthorizedSource):
            self.scoped_peer(self.db, replace(self.policy, environment="other"))(
                self.event
            )
        standby = create_engine(
            self.db.url.set(port=int(os.environ["APTRON_LAB_STANDBY_PORT"]))
        )
        self.lab.callback(standby.dispose)
        with standby.connect() as db:
            self.assertTrue(db.scalar(text("select pg_is_in_recovery()")))
        with self.assertRaisesRegex(RuntimeError, "Writable PostgreSQL primary"):
            self.scoped_peer(standby, self.policy)(self.event)
        for setting, reason in (
            ("transaction_read_only = on", "Writable PostgreSQL primary"),
            ("default_transaction_read_only = on", "Writable PostgreSQL primary"),
            ("synchronous_commit = off", "violate protection policy"),
            ("session_replication_role = replica", "violate protection policy"),
            ("search_path = pg_catalog", "violate protection policy"),
        ):

            def configure(db):
                db.exec_driver_sql("SET LOCAL " + setting)

            with self.listen(configure, "begin"), self.assertRaisesRegex(
                RuntimeError, reason
            ):
                self.submit(self.event)
        self.assertEqual(self.submit(self.event), self.submit(self.event))

    def test_conflict_audit_rechecks_protection_policy(self):
        key = self.submit(self.event)
        conflict = replace(
            self.event,
            canonical_payload=b"changed",
            identity=replace(
                self.event.identity, payload_sha256=sha256(b"changed").digest()
            ),
        )
        transactions = 0

        def read_only_during_audit(db):
            nonlocal transactions
            transactions += 1
            if transactions == 2:
                db.exec_driver_sql("SET TRANSACTION READ ONLY")

        with self.listen(read_only_during_audit, "begin"), self.assertRaisesRegex(
            RuntimeError, "Writable PostgreSQL primary"
        ):
            self.submit(conflict)
        self.assertEqual(transactions, 2)
        with self.db.connect() as db:
            self.assertIsNone(
                db.scalar(
                    select(conflicts.c.conflict_id).where(
                        conflicts.c.evidence_reference == str(key)
                    )
                )
            )
        self.assertEqual(self.submit(self.event), key)

    def test_unsupported_transaction_modes(self):
        for level in (
            "READ UNCOMMITTED",
            "REPEATABLE READ",
            "SERIALIZABLE",
            "AUTOCOMMIT",
        ):
            with self.subTest(level=level), self.assertRaises(RuntimeError):
                self.scoped_peer(
                    self.db.execution_options(isolation_level=level), self.policy
                )(self.event)
        other = create_engine("sqlite://")
        self.lab.callback(other.dispose)
        with self.assertRaisesRegex(RuntimeError, "PostgreSQL psycopg"):
            self.scoped_peer(other, self.policy)(self.event)

    def test_serialization_abort_and_clean_retry(self):
        from sqlalchemy.exc import DBAPIError

        tables = (registry, inbox, finalization, conflicts)
        before = [self.count(t) for t in tables]
        # Forced server-side 40001, once during the final write and once at COMMIT.
        for timing in ("INITIALLY IMMEDIATE", "INITIALLY DEFERRED"):
            with self.db.begin() as db:
                db.exec_driver_sql(
                    """CREATE FUNCTION txn_abort_fixture() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN RAISE EXCEPTION 'fixture serialization failure' USING ERRCODE='40001'; END $$"""
                )
                db.exec_driver_sql(
                    f"""CREATE CONSTRAINT TRIGGER txn_abort_fixture AFTER INSERT ON
                    protected_finalization_outbox DEFERRABLE {timing} FOR EACH ROW EXECUTE FUNCTION txn_abort_fixture()"""
                )
            try:
                with self.assertRaises(DBAPIError) as failed:
                    self.submit(self.event)
                self.assertEqual(failed.exception.orig.sqlstate, "40001")
                self.assertEqual([self.count(t) for t in tables], before)
            finally:
                with self.db.begin() as db:
                    db.exec_driver_sql(
                        "DROP TRIGGER txn_abort_fixture ON protected_finalization_outbox"
                    )
                    db.exec_driver_sql("DROP FUNCTION txn_abort_fixture()")
        self.assertEqual(self.submit(self.event), self.submit(self.event))

    def test_delete_waits_and_preserves_legacy_owner(self):
        from sqlalchemy.exc import IntegrityError
        from app.telemetry.models import ManagedAgent

        from app.models import DataSource

        for table, parent_id in (
            (ManagedAgent.__table__, self.scope["installation_id"]),
            (DataSource.__table__, self.scope["source_id"]),
        ):
            with self.subTest(table=table.name):
                selector = table.c.id == parent_id
                with self.db.connect() as db:
                    original = db.execute(select(table).where(selector)).one()

                def remove():
                    with self.db.begin() as db:
                        db.execute(table.delete().where(selector))

                self.event = self.make_event()
                key, deletion = self.while_locked(remove)
                with self.assertRaises(IntegrityError) as denied:
                    deletion.result()
                self.assertEqual(denied.exception.orig.sqlstate, "23503")
                with self.db.connect() as db:
                    self.assertEqual(
                        db.execute(select(table).where(selector)).one(), original
                    )
                    self.assertEqual(
                        db.scalar(
                            select(inbox.c.collector_id).where(inbox.c.event_key == key)
                        ),
                        self.scope["installation_id"],
                    )

    def test_legacy_upgrade_and_restrictive_foreign_keys(self):
        original = json.loads(os.environ["APTRON_LAB_LEGACY_ROW"])
        with self.db.begin() as db:
            self.assertEqual(
                db.scalar(
                    text("SELECT to_jsonb(a) FROM managed_agents a WHERE id=:id"),
                    {"id": original["id"]},
                ),
                original,
            )
            self.assertFalse(
                db.scalar(
                    text(
                        "SELECT EXISTS (SELECT FROM collector_certificates WHERE installation_id=:id)"
                    ),
                    {"id": original["id"]},
                )
            )
            parents = dict(db.exec_driver_sql("""
                SELECT confrelid::regclass::text, confdeltype::text FROM pg_constraint
                 WHERE conrelid='collector_certificates'::regclass AND contype='f'
            """).all())
            self.assertEqual(
                parents,
                {
                    name: "r"
                    for name in (
                        "organizations",
                        "data_sources",
                        "collectors",
                        "managed_agents",
                        "worker_identities",
                    )
                },
            )

    def test_prior_mutations_deny_new_event(self):
        from app.models import DataSource

        src = DataSource.__table__
        for change in ("disable", "reassign", "rotate", "revoke"):
            with self.subTest(change=change):
                submitted = self.peer()
                with self.db.begin() as db:
                    if change == "disable":
                        db.execute(
                            update(src)
                            .where(src.c.id == self.scope["source_id"])
                            .values(enabled=False)
                        )
                    elif change == "reassign":
                        db.execute(
                            update(Collector.__table__)
                            .where(Collector.id == self.scope["configuration_id"])
                            .values(data_source_id=self.other_source)
                        )
                    elif change == "rotate":
                        self.enroll("new", 1, db)
                    else:
                        revoke_certificate(
                            db,
                            sha256(
                                ssl.PEM_cert_to_DER_cert(
                                    (self.directory / "client.pem").read_text()
                                )
                            ).digest(),
                        )
                before = self.count(registry)
                with self.assertRaises(UnauthorizedSource):
                    submitted(self.make_event())
                self.assertEqual(before, self.count(registry))
                if change != "revoke":
                    # Each case starts from a distinct legitimately enrolled installation.
                    self.scope, self.other_source = fixture(self.db)
                    issue(self.directory, "client")
                    self.enroll("client", 0)

    def test_independent_same_tenant_contention(self):
        from statistics import median, quantiles

        second, _ = fixture(self.db, organization_id=self.scope["tenant_id"])
        with self.db.begin() as db:
            register_certificate(
                db,
                **second,
                certificate_pem=(self.directory / "new.pem").read_text(),
                expected_generation=0,
            )
        peer = self.peer("new")

        def independent():
            e = self.make_event()
            return peer(
                replace(
                    e,
                    collector_id=second["installation_id"],
                    identity=replace(e.identity, source_id=second["source_id"]),
                )
            )

        # Observe a real blocked backend even though event, source and installation differ.
        first, result = self.while_locked(independent)
        self.assertNotEqual(first, result.result())

        def batch(submit):
            durations = []
            for _ in range(24):
                start = time.perf_counter()
                submit()
                durations.append((time.perf_counter() - start) * 1000)
            return durations

        def one():
            return self.submit(self.make_event())

        for concurrent in (False, True):
            start = time.perf_counter()
            if concurrent:
                with ThreadPoolExecutor(2) as pool:
                    runs = [pool.submit(batch, fn) for fn in (one, independent)]
                    times = runs[0].result() + runs[1].result()
            else:
                times = batch(one) + batch(independent)
            elapsed = time.perf_counter() - start
            print(
                f"Same tenant clients={2 if concurrent else 1} events={len(times)} "
                f"events/s={len(times)/elapsed:.1f} median_ms={median(times):.2f} "
                f"p95_ms={quantiles(times,n=20)[18]:.2f}",
                flush=True,
            )
