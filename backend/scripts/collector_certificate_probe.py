"""Run only in a freshly migrated disposable s03_auth_lab database."""

import os
import socket
import ssl
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from unittest import TestCase
from uuid import uuid4

from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from app.main import app  # noqa: F401 -- register the full mapper graph
from app.critical_events.registration import (
    CollectorTransport,
    UnauthorizedSource,
    register_certificate,
    revoke_certificate,
)
from app.models import Organization, DataSource, Collector
from app.security.models import WorkerIdentity
from app.telemetry.models import ManagedAgent


def issue(directory, name, *, expired=False):
    def openssl(*args):
        subprocess.run(
            ["openssl", *args], cwd=directory, check=True, capture_output=True
        )

    openssl(
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=" + name,
        "-keyout",
        name + ".key",
        "-out",
        name + ".csr",
    )
    signer = (
        ["-signkey", name + ".key"]
        if name == "ca"
        else ["-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial"]
    )
    extensions = directory / (name + ".ext")
    extensions.write_text(
        "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
        if name == "ca"
        else "basicConstraints=critical,CA:FALSE\nextendedKeyUsage="
        + ("serverAuth" if name == "localhost" else "clientAuth")
        + "\n"
    )
    openssl(
        "x509",
        "-req",
        "-in",
        name + ".csr",
        *signer,
        "-extfile",
        extensions.name,
        "-days",
        "0" if expired else "2",
        "-out",
        name + ".pem"
    )


@contextmanager
def connection(transport, directory, name):
    client = ssl.create_default_context(cafile=str(directory / "ca.pem"))
    if name:
        client.load_cert_chain(directory / (name + ".pem"), directory / (name + ".key"))
    left, right = socket.socketpair()
    left.settimeout(5)
    right.settimeout(5)
    with left, right, ThreadPoolExecutor(1) as pool:
        handshake = pool.submit(client.wrap_socket, right, server_hostname="localhost")
        try:
            with transport.accept(left) as (_, authenticate):
                yield authenticate
        finally:
            try:
                handshake.result().close()
            except ssl.SSLError:
                pass


def fixture(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name=uuid4().hex, code=uuid4().hex)
        session.add(org)
        session.flush()
        sources = [
            DataSource(
                organization_id=org.id,
                name=name,
                source_type="LINUX",
                connection_config={"opscontrol": {"environment": "lab"}},
            )
            for name in ("one", "two")
        ]
        worker = WorkerIdentity(
            organization_id=org.id,
            name="lab",
            token_hash=uuid4().hex * 2,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        session.add_all([*sources, worker])
        session.flush()
        config = Collector(
            data_source_id=sources[0].id,
            remote_worker_id=worker.id,
            name="lab",
            collector_type="LINUX",
        )
        session.add(config)
        session.flush()
        agent = ManagedAgent(
            organization_id=org.id,
            collector_id=config.id,
            worker_id=worker.id,
            hostname="lab",
            version="test",
            runtime_version="test",
        )
        session.add(agent)
        session.flush()
        return (
            dict(
                tenant_id=org.id,
                source_id=sources[0].id,
                installation_id=agent.id,
                configuration_id=config.id,
            ),
            sources[1].id,
        )


def race(engine, authenticate, scope, mutation):
    # Hold admission open, verify the other live backend is actually waiting on
    # our transaction, then release and observe its committed change.
    pids = Queue()

    def mutate():
        with engine.begin() as other:
            pids.put(other.scalar(text("SELECT pg_backend_pid()")))
            other.execute(text("SET LOCAL lock_timeout = '8s'"))
            mutation(other)

    with ThreadPoolExecutor(1) as pool:
        with engine.begin() as first:
            authenticate(first, **scope)
            holder = first.scalar(text("SELECT pg_backend_pid()"))
            future = pool.submit(mutate)
            waiter = pids.get(timeout=5)
            deadline = time.monotonic() + 5
            while not first.scalar(
                text("SELECT :holder = ANY(pg_blocking_pids(:waiter))"),
                dict(holder=holder, waiter=waiter),
            ):
                if future.done():
                    future.result()
                    raise AssertionError("Mutation escaped admission lock")
                if time.monotonic() > deadline:
                    raise AssertionError("Mutation never blocked on admission")
                time.sleep(0.02)
        future.result(timeout=10)


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as db:
        if (
            os.environ.get("APTRON_DISPOSABLE_STAGING") != "1"
            or db.scalar(text("SELECT current_database()")) != "s03_auth_lab"
        ):
            raise RuntimeError("Owned isolated fixture required")
    registration, other_source = fixture(engine)
    foreign, _ = fixture(engine)
    scope = dict(
        tenant_id=registration["tenant_id"],
        source_id=registration["source_id"],
        collector_id=registration["installation_id"],
        capability="critical-event:submit",
        environment="lab",
    )
    check = TestCase()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name in ("ca", "localhost", "old", "new", "unknown", "expired"):
            issue(directory, name, expired=name == "expired")
        transport = CollectorTransport(
            server_certificate=directory / "localhost.pem",
            server_key=directory / "localhost.key",
            client_ca=directory / "ca.pem",
        )

        def enroll(db, name, expected):
            return register_certificate(
                db,
                **registration,
                certificate_pem=(directory / (name + ".pem")).read_text(),
                expected_generation=expected
            )

        with engine.begin() as db:
            enroll(db, "old", 0)
        with check.assertRaises(UnauthorizedSource), transport.accept(
            {"X-Client-Cert": "old"}
        ):
            pass
        for name in (None, "expired"):
            with check.assertRaises(ssl.SSLError), connection(
                transport, directory, name
            ):
                pass
        with connection(
            transport, directory, "unknown"
        ) as auth, engine.begin() as db, check.assertRaises(UnauthorizedSource):
            auth(db, **scope)
        with connection(transport, directory, "old") as auth:
            with engine.begin() as db:
                check.assertEqual(auth(db, **scope).generation, 1)
                for substitution in (
                    dict(source_id=other_source),
                    dict(tenant_id=foreign["tenant_id"]),
                    dict(collector_id=foreign["installation_id"]),
                    dict(environment="prod"),
                    dict(capability="recover:source-events"),
                ):
                    with check.assertRaises(UnauthorizedSource):
                        auth(db, **(scope | substitution))
            with engine.begin() as db:
                with check.assertRaises(IntegrityError):
                    enroll(db, "old", 1)
                check.assertEqual(auth(db, **scope).generation, 1)
            race(engine, auth, scope, lambda db: enroll(db, "new", 1))
            with engine.begin() as db, check.assertRaises(UnauthorizedSource):
                auth(db, **scope)
        with connection(transport, directory, "new") as auth:
            with engine.begin() as db:
                check.assertEqual(auth(db, **scope).generation, 2)
                with check.assertRaises(UnauthorizedSource):
                    enroll(db, "unknown", 1)
            reassign = update(Collector.__table__).where(
                Collector.id == registration["configuration_id"]
            )
            race(
                engine,
                auth,
                scope,
                lambda db: db.execute(reassign.values(data_source_id=other_source)),
            )
            with engine.begin() as db:
                db.execute(reassign.values(data_source_id=registration["source_id"]))
                with check.assertRaises(UnauthorizedSource):
                    auth(db, **scope)
                enroll(db, "unknown", 2)
        with connection(transport, directory, "unknown") as auth:
            with engine.begin() as db:
                binding = auth(db, **scope)
                revoke_certificate(db, bytes.fromhex(binding.principal_id))
            with engine.begin() as db, check.assertRaises(UnauthorizedSource):
                auth(db, **scope)
        for statement in (
            "DELETE FROM collector_certificates",
            "TRUNCATE collector_certificates",
            "UPDATE collector_certificates SET revoked=false",
        ):
            with check.assertRaises(DBAPIError), engine.begin() as db:
                db.execute(text(statement))
    print(
        "PASS: direct mTLS, missing/expired/unknown certificate, header denial, tenant/source/installation scope, recovery grant denial, locked rotation and reassignment, stale generation and revocation"
    )


if __name__ == "__main__":
    main()
