"""Independent real connections to the runner-owned PG17 and ephemeral test PKI."""

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
        self.service = IngestionService(
            self.db,
            policy_id="disposable-local",
            server_certificate=self.directory / "localhost.pem",
            server_key=self.directory / "localhost.key",
            client_ca=self.directory / "ca.pem",
        )
        self.submit = self.peer()
        self.event = self.make_event()

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
