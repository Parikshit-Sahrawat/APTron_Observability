"""Internal, connection-bound ingestion. Event keys are local references only."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from ipaddress import ip_address
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from .identity import EventIdentity, IdentityConflict, UnauthorizedSource, same_retry
from .models import conflicts, finalization, inbox, registry
from .registration import CollectorTransport


@dataclass(frozen=True)
class Submission:
    identity: EventIdentity
    collector_id: UUID
    environment: str
    canonical_payload: bytes

    def validate(self):
        key = self.identity
        if (
            type(key) is not EventIdentity
            or key.schema_version != "1.0"
            or key.canonicalization_version != "1.0"
            or "\x00" in key.event_id
            or not isinstance(self.collector_id, UUID)
            or not isinstance(self.environment, str)
            or not 0 < len(self.environment) <= 256
            or type(self.canonical_payload) is not bytes
            or not 0 < len(self.canonical_payload) <= 1024 * 1024
        ):
            raise ValueError("Unsupported or unbounded critical event")
        if not compare_digest(
            sha256(self.canonical_payload).digest(), key.payload_sha256
        ):
            raise ValueError("Canonical payload digest mismatch")


@dataclass(frozen=True)
class ProtectionPolicy:
    """Deployment-owned pins supplied independently of requests and pool discovery."""

    policy_id: str
    environment: str
    database: str
    system_identifier: int
    server_address: str
    server_port: int

    def __post_init__(self):
        if self.policy_id != "disposable-local":
            raise ValueError("Unsupported ingestion protection policy")
        if not all(
            isinstance(s, str) and s.strip() for s in (self.environment, self.database)
        ):
            raise ValueError("Explicit environment and database pins required")
        if type(self.system_identifier) is not int or self.system_identifier <= 0:
            raise ValueError("Explicit PostgreSQL system identifier required")

        ip_address(self.server_address)
        if type(self.server_port) is not int or not 0 < self.server_port < 65536:
            raise ValueError("Explicit PostgreSQL port required")

    def check_transaction(self, db):
        if (
            (db.dialect.name, db.dialect.driver) != ("postgresql", "psycopg")
            or not db.in_transaction()
            or db.connection.driver_connection.autocommit
        ):
            raise RuntimeError("Transactional PostgreSQL psycopg connection required")
        state = db.exec_driver_sql("""
            SELECT pg_catalog.pg_is_in_recovery() AS recovering,
                   pg_catalog.current_setting('transaction_read_only') AS read_only,
                   pg_catalog.current_setting('transaction_isolation') AS isolation,
                   pg_catalog.current_database() AS database,
                   system_identifier,
                   pg_catalog.host(pg_catalog.inet_server_addr()) AS server_address,
                   pg_catalog.inet_server_port() AS server_port,
                   pg_catalog.current_setting('server_version_num')::int AS version,
                   pg_catalog.current_setting('default_transaction_read_only') AS default_read_only,
                   pg_catalog.current_schemas(true) AS schemas,
                   pg_catalog.current_setting('session_replication_role') AS replication_role,
                   pg_catalog.current_setting('full_page_writes') AS full_page_writes,
                   pg_catalog.current_setting('fsync') AS fsync,
                   pg_catalog.current_setting('synchronous_commit') AS sync_commit
              FROM pg_catalog.pg_control_system()
        """).mappings().one()
        if (
            state.recovering
            or state.read_only != "off"
            or state.default_read_only != "off"
        ):
            raise RuntimeError("Writable PostgreSQL primary required")
        if state.isolation != "read committed":
            raise RuntimeError("READ COMMITTED isolation required")
        if (
            state.database != self.database
            or state.system_identifier != self.system_identifier
            or state.server_address != self.server_address
            or state.server_port != self.server_port
            or not 170000 <= state.version < 180000
            or state.schemas != ["pg_catalog", "public"]
            or state.replication_role != "origin"
            or state.full_page_writes != "on"
            or state.fsync != "on"
            or state.sync_commit not in {"local", "on", "remote_write", "remote_apply"}
        ):
            raise RuntimeError(
                "PostgreSQL target or settings violate protection policy"
            )


class CommitIndeterminate(RuntimeError):
    """Local COMMIT outcome or synchronous wait was ambiguous. No receipt."""


def _commit(db, transaction):
    # PostgreSQL can return command success with WARNING when SyncRep is canceled.
    db.exec_driver_sql("SET LOCAL client_min_messages = warning")
    raw = db.connection.driver_connection
    warnings = []

    def notice(diag):
        if diag.severity_nonlocalized in {"WARNING", "ERROR", "FATAL", "PANIC"}:
            warnings.append(diag.sqlstate)

    raw.add_notice_handler(notice)
    try:
        try:
            transaction.commit()
        finally:
            raw.remove_notice_handler(notice)
        if warnings:
            raise RuntimeError("PostgreSQL commit warning")
    except Exception as exc:
        db.invalidate()
        # A server-reported serialization rollback is a known rejection even
        # when a deferred operation reports it at COMMIT.
        if (
            isinstance(exc, DBAPIError)
            and getattr(exc.orig, "sqlstate", None) == "40001"
        ):
            raise
        raise CommitIndeterminate("Commit requires independent reconciliation") from exc


def _natural(subject, event):
    return and_(
        registry.c.tenant_id == subject.tenant_id,
        registry.c.source_id == subject.source_id,
        registry.c.event_id == event.identity.event_id,
    )


def _existing(db, subject, event):
    return (
        db.execute(
            select(
                registry,
                inbox.c.collector_id,
                inbox.c.canonical_payload,
                finalization.c.event_key.label("obligation"),
            )
            .outerjoin(inbox, inbox.c.event_key == registry.c.event_key)
            .outerjoin(finalization, finalization.c.event_key == registry.c.event_key)
            .where(_natural(subject, event))
        )
        .mappings()
        .one()
    )


def _compare(row, subject, event):
    if row.collector_id != subject.installation_id or row.obligation is None:
        raise UnauthorizedSource("Incomplete or differently owned event")
    same_retry(
        EventIdentity(
            row.tenant_id,
            row.source_id,
            row.event_id,
            row.payload_sha256,
            row.schema_version,
            row.canonicalization_version,
        ),
        event.identity,
    )
    if row.canonical_payload != event.canonical_payload:
        raise IdentityConflict("Canonical payload conflict")


def _persist(db, subject, event, policy):
    identity = event.identity
    key = db.scalar(
        insert(registry)
        .values(
            tenant_id=subject.tenant_id,
            source_id=subject.source_id,
            event_id=identity.event_id,
            event_key=uuid4(),
            schema_version=identity.schema_version,
            canonicalization_version=identity.canonicalization_version,
            payload_sha256=identity.payload_sha256,
            first_seen_at=func.clock_timestamp(),
        )
        .on_conflict_do_nothing(constraint="uq_critical_event_identity")
        .returning(registry.c.event_key)
    )
    if key is None:
        existing = _existing(db, subject, event)
        _compare(existing, subject, event)
        return existing.event_key
    db.execute(
        inbox.insert().values(
            event_key=key,
            canonical_payload=event.canonical_payload,
            collector_id=subject.installation_id,
            protected_received_at=func.clock_timestamp(),
            protection_state="PENDING",
            protection_policy_id=policy,
        )
    )
    db.execute(finalization.insert().values(event_key=key, state="PENDING"))
    return key


class IngestionService:
    def __init__(self, engine, *, policy, server_certificate, server_key, client_ca):
        if type(policy) is not ProtectionPolicy:
            raise ValueError("Trusted ingestion protection policy required")
        self._engine = engine
        self._policy = policy
        self._transport = CollectorTransport(
            server_certificate=server_certificate,
            server_key=server_key,
            client_ca=client_ca,
        )

    @contextmanager
    def accept(self, raw_socket):
        """Yield a local submit operation scoped to the lifetime of this mTLS stream."""
        with self._transport.accept(raw_socket) as (stream, authenticate):

            def authority(db, event):
                self._policy.check_transaction(db)
                if event.environment != self._policy.environment:
                    raise UnauthorizedSource(
                        "Environment outside configured ingestion policy"
                    )
                return authenticate(
                    db,
                    tenant_id=event.identity.tenant_id,
                    source_id=event.identity.source_id,
                    collector_id=event.collector_id,
                    environment=event.environment,
                    capability="critical-event:submit",
                )

            def submit(event):
                if type(event) is not Submission:
                    raise ValueError("Critical-event submission required")
                event.validate()
                try:
                    with self._engine.connect() as db, db.begin() as tx:
                        subject = authority(db, event)
                        key = _persist(db, subject, event, self._policy.policy_id)
                        _commit(db, tx)
                        return key
                except IdentityConflict:
                    # Fully roll back before acquiring new authority locks. Recheck
                    # original ownership and conflict under the independent audit tx.
                    with self._engine.connect() as db, db.begin() as tx:
                        subject = authority(db, event)
                        row = _existing(db, subject, event)
                        try:
                            _compare(row, subject, event)
                        except IdentityConflict:
                            db.execute(
                                conflicts.insert().values(
                                    conflict_id=uuid4(),
                                    tenant_id=subject.tenant_id,
                                    source_id=subject.source_id,
                                    event_id=row.event_id,
                                    existing_hash=row.payload_sha256,
                                    received_hash=event.identity.payload_sha256,
                                    actor_id=subject.principal_id,
                                    detected_at=func.clock_timestamp(),
                                    evidence_reference=str(row.event_key),
                                )
                            )
                            _commit(db, tx)
                    raise

            yield stream, submit
