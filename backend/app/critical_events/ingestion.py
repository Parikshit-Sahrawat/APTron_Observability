"""Internal, connection-bound ingestion. Event keys are local references only."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert

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
    def __init__(self, engine, *, policy_id, server_certificate, server_key, client_ca):
        if (
            not isinstance(policy_id, str)
            or not policy_id.strip()
            or len(policy_id) > 256
        ):
            raise ValueError("Explicit protection policy required")
        self._engine = engine
        self._policy = policy_id
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
                        key = _persist(db, subject, event, self._policy)
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
