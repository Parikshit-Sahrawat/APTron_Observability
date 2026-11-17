"""Dormant IR-002 central storage. No admission, ACK or signer is enabled."""

from sqlalchemy import (
    Table,
    Column,
    Text,
    BigInteger,
    DateTime,
    LargeBinary,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from app.db.session import Base
from app.telemetry.models import ManagedAgent
from app.models import Organization, DataSource


def uid(name, target=None, *, primary=False, nullable=False):
    return Column(
        name,
        UUID(as_uuid=True),
        *([ForeignKey(target, ondelete="RESTRICT")] if target else []),
        primary_key=primary,
        nullable=nullable
    )


def value(name, *, nullable=False):
    return Column(name, Text, nullable=nullable)


def timestamp(name, *, nullable=False):
    return Column(name, DateTime(timezone=True), nullable=nullable)


def generation(name="claim_generation"):
    return Column(name, BigInteger, nullable=False, server_default=text("0"))


registry = Table(
    "event_identity_registry",
    Base.metadata,
    uid("event_key", primary=True),
    uid("tenant_id", Organization.__tablename__ + ".id"),
    uid("source_id", DataSource.__tablename__ + ".id"),
    value("event_id"),
    value("schema_version"),
    value("canonicalization_version"),
    Column("payload_sha256", LargeBinary, nullable=False),
    timestamp("first_seen_at"),
    UniqueConstraint(
        "tenant_id", "source_id", "event_id", name="uq_critical_event_identity"
    ),
    CheckConstraint("length(event_id) BETWEEN 1 AND 512", name="ck_critical_event_id"),
    CheckConstraint(
        "octet_length(payload_sha256) = 32", name="ck_critical_identity_hash"
    ),
    CheckConstraint(
        "length(schema_version) > 0 AND length(canonicalization_version) > 0",
        name="ck_critical_identity_versions",
    ),
)

inbox = Table(
    "protected_event_inbox",
    Base.metadata,
    uid("event_key", "event_identity_registry.event_key", primary=True),
    Column("canonical_payload", LargeBinary, nullable=False),
    uid("collector_id", ManagedAgent.__tablename__ + ".id"),
    timestamp("protected_received_at"),
    value("protection_state"),
    value("protection_policy_id"),
)

finalization = Table(
    "protected_finalization_outbox",
    Base.metadata,
    uid("event_key", "protected_event_inbox.event_key", primary=True),
    value("state"),
    generation(),
    value("claim_owner", nullable=True),
    timestamp("claim_expires_at", nullable=True),
    timestamp("next_attempt_at", nullable=True),
    value("last_error_category", nullable=True),
    CheckConstraint(
        "claim_generation >= 0", name="ck_critical_finalization_generation"
    ),
)

ledger = Table(
    "critical_event_ledger",
    Base.metadata,
    uid("event_key", "event_identity_registry.event_key", primary=True),
    value("connector_type"),
    value("scheduler_version", nullable=True),
    value("execution_id"),
    value("attempt_id", nullable=True),
    value("event_type"),
    timestamp("occurred_at"),
    timestamp("observed_at"),
    Column("normalized_event", LargeBinary, nullable=False),
    uid(
        "original_failure_event_key", "event_identity_registry.event_key", nullable=True
    ),
)

claims = Table(
    "durable_receipt_claim",
    Base.metadata,
    uid("receipt_id", primary=True),
    uid("event_key", "event_identity_registry.event_key"),
    value("receipt_class"),
    value("receipt_version"),
    value("durability_policy_id"),
    timestamp("claim_created_at"),
    generation("current_reaffirmation_generation"),
    UniqueConstraint("event_key", "receipt_class", name="uq_critical_receipt_class"),
    CheckConstraint(
        "receipt_class IN ('HOST_PROTECTED','CENTRAL_DURABLE')",
        name="ck_critical_receipt_class",
    ),
    CheckConstraint(
        "current_reaffirmation_generation >= 0", name="ck_critical_receipt_generation"
    ),
)

reaffirmation = Table(
    "receipt_reaffirmation",
    Base.metadata,
    uid("receipt_id", "durable_receipt_claim.receipt_id", primary=True),
    Column("generation", BigInteger, primary_key=True, nullable=False),
    uid("barrier_token"),
    timestamp("barrier_committed_at"),
    UniqueConstraint("barrier_token", name="uq_critical_barrier"),
    CheckConstraint("generation > 0", name="ck_critical_reaffirmation_generation"),
)

processing = Table(
    "processing_outbox",
    Base.metadata,
    uid("outbox_id", primary=True),
    uid("event_key", "critical_event_ledger.event_key"),
    value("obligation_type"),
    value("state"),
    generation(),
    value("claim_owner", nullable=True),
    timestamp("claim_expires_at", nullable=True),
    value("external_idempotency_key"),
    value("last_error_category", nullable=True),
    timestamp("completed_at", nullable=True),
    UniqueConstraint(
        "event_key", "obligation_type", name="uq_critical_processing_obligation"
    ),
    UniqueConstraint(
        "external_idempotency_key", name="uq_critical_external_idempotency"
    ),
    CheckConstraint("claim_generation >= 0", name="ck_critical_processing_generation"),
)

conflicts = Table(
    "identity_conflict_audit",
    Base.metadata,
    uid("conflict_id", primary=True),
    uid("tenant_id", Organization.__tablename__ + ".id"),
    uid("source_id", DataSource.__tablename__ + ".id"),
    value("event_id"),
    Column("existing_hash", LargeBinary, nullable=False),
    Column("received_hash", LargeBinary, nullable=False),
    value("actor_id", nullable=True),
    timestamp("detected_at"),
    value("evidence_reference"),
    CheckConstraint(
        "octet_length(existing_hash) = 32 AND octet_length(received_hash) = 32",
        name="ck_critical_conflict_hashes",
    ),
)

gaps = Table(
    "delivery_gap_audit",
    Base.metadata,
    uid("gap_id", primary=True),
    uid("tenant_id", Organization.__tablename__ + ".id"),
    uid("source_id", DataSource.__tablename__ + ".id"),
    timestamp("detected_at"),
    timestamp("start_at", nullable=True),
    timestamp("end_at", nullable=True),
    value("reason_code"),
    Column("known_missing_count", BigInteger),
    Column("estimated_missing_count", BigInteger),
    value("confidence_note", nullable=True),
    value("recovery_state"),
    CheckConstraint(
        "known_missing_count IS NULL OR known_missing_count >= 0",
        name="ck_critical_gap_known_count",
    ),
    CheckConstraint(
        "estimated_missing_count IS NULL OR estimated_missing_count >= 0",
        name="ck_critical_gap_estimated_count",
    ),
    CheckConstraint(
        "start_at IS NULL OR end_at IS NULL OR start_at <= end_at",
        name="ck_critical_gap_interval",
    ),
)

Index(
    "ix_critical_finalization_due", finalization.c.state, finalization.c.next_attempt_at
)
Index("ix_critical_processing_due", processing.c.state, processing.c.claim_expires_at)
TABLES = (
    registry,
    inbox,
    finalization,
    ledger,
    claims,
    reaffirmation,
    processing,
    conflicts,
    gaps,
)
