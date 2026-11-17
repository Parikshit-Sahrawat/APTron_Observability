"""Additive critical-event storage; does not expose ingestion or acknowledgments."""

from alembic import op

revision = "0039_critical_event_storage"
down_revision = "0038_k8s_cluster_associations"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE event_identity_registry (
	event_key UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	event_id TEXT NOT NULL, 
	schema_version TEXT NOT NULL, 
	canonicalization_version TEXT NOT NULL, 
	payload_sha256 BYTEA NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (event_key), 
	CONSTRAINT uq_critical_event_identity UNIQUE (tenant_id, source_id, event_id), 
	CONSTRAINT ck_critical_event_id CHECK (length(event_id) BETWEEN 1 AND 512), 
	CONSTRAINT ck_critical_identity_hash CHECK (octet_length(payload_sha256) = 32), 
	CONSTRAINT ck_critical_identity_versions CHECK (length(schema_version) > 0 AND length(canonicalization_version) > 0), 
	FOREIGN KEY(tenant_id) REFERENCES organizations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_id) REFERENCES data_sources (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE protected_event_inbox (
	event_key UUID NOT NULL, 
	canonical_payload BYTEA NOT NULL, 
	collector_id UUID NOT NULL, 
	protected_received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	protection_state TEXT NOT NULL, 
	protection_policy_id TEXT NOT NULL, 
	PRIMARY KEY (event_key), 
	FOREIGN KEY(event_key) REFERENCES event_identity_registry (event_key) ON DELETE RESTRICT, 
	FOREIGN KEY(collector_id) REFERENCES managed_agents (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE protected_finalization_outbox (
	event_key UUID NOT NULL, 
	state TEXT NOT NULL, 
	claim_generation BIGINT DEFAULT 0 NOT NULL, 
	claim_owner TEXT, 
	claim_expires_at TIMESTAMP WITH TIME ZONE, 
	next_attempt_at TIMESTAMP WITH TIME ZONE, 
	last_error_category TEXT, 
	PRIMARY KEY (event_key), 
	CONSTRAINT ck_critical_finalization_generation CHECK (claim_generation >= 0), 
	FOREIGN KEY(event_key) REFERENCES protected_event_inbox (event_key) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_critical_finalization_due ON protected_finalization_outbox (state, next_attempt_at)""",
    """CREATE TABLE critical_event_ledger (
	event_key UUID NOT NULL, 
	connector_type TEXT NOT NULL, 
	scheduler_version TEXT, 
	execution_id TEXT NOT NULL, 
	attempt_id TEXT, 
	event_type TEXT NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	normalized_event BYTEA NOT NULL, 
	original_failure_event_key UUID, 
	PRIMARY KEY (event_key), 
	FOREIGN KEY(event_key) REFERENCES event_identity_registry (event_key) ON DELETE RESTRICT, 
	FOREIGN KEY(original_failure_event_key) REFERENCES event_identity_registry (event_key) ON DELETE RESTRICT
)""",
    """CREATE TABLE durable_receipt_claim (
	receipt_id UUID NOT NULL, 
	event_key UUID NOT NULL, 
	receipt_class TEXT NOT NULL, 
	receipt_version TEXT NOT NULL, 
	durability_policy_id TEXT NOT NULL, 
	claim_created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	current_reaffirmation_generation BIGINT DEFAULT 0 NOT NULL, 
	PRIMARY KEY (receipt_id), 
	CONSTRAINT uq_critical_receipt_class UNIQUE (event_key, receipt_class), 
	CONSTRAINT ck_critical_receipt_class CHECK (receipt_class IN ('HOST_PROTECTED','CENTRAL_DURABLE')), 
	CONSTRAINT ck_critical_receipt_generation CHECK (current_reaffirmation_generation >= 0), 
	FOREIGN KEY(event_key) REFERENCES event_identity_registry (event_key) ON DELETE RESTRICT
)""",
    """CREATE TABLE receipt_reaffirmation (
	receipt_id UUID NOT NULL, 
	generation BIGINT NOT NULL, 
	barrier_token UUID NOT NULL, 
	barrier_committed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (receipt_id, generation), 
	CONSTRAINT uq_critical_barrier UNIQUE (barrier_token), 
	CONSTRAINT ck_critical_reaffirmation_generation CHECK (generation > 0), 
	FOREIGN KEY(receipt_id) REFERENCES durable_receipt_claim (receipt_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE processing_outbox (
	outbox_id UUID NOT NULL, 
	event_key UUID NOT NULL, 
	obligation_type TEXT NOT NULL, 
	state TEXT NOT NULL, 
	claim_generation BIGINT DEFAULT 0 NOT NULL, 
	claim_owner TEXT, 
	claim_expires_at TIMESTAMP WITH TIME ZONE, 
	external_idempotency_key TEXT NOT NULL, 
	last_error_category TEXT, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (outbox_id), 
	CONSTRAINT uq_critical_processing_obligation UNIQUE (event_key, obligation_type), 
	CONSTRAINT uq_critical_external_idempotency UNIQUE (external_idempotency_key), 
	CONSTRAINT ck_critical_processing_generation CHECK (claim_generation >= 0), 
	FOREIGN KEY(event_key) REFERENCES critical_event_ledger (event_key) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_critical_processing_due ON processing_outbox (state, claim_expires_at)""",
    """CREATE TABLE identity_conflict_audit (
	conflict_id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	event_id TEXT NOT NULL, 
	existing_hash BYTEA NOT NULL, 
	received_hash BYTEA NOT NULL, 
	actor_id TEXT, 
	detected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	evidence_reference TEXT NOT NULL, 
	PRIMARY KEY (conflict_id), 
	CONSTRAINT ck_critical_conflict_hashes CHECK (octet_length(existing_hash) = 32 AND octet_length(received_hash) = 32), 
	FOREIGN KEY(tenant_id) REFERENCES organizations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_id) REFERENCES data_sources (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE delivery_gap_audit (
	gap_id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	detected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	start_at TIMESTAMP WITH TIME ZONE, 
	end_at TIMESTAMP WITH TIME ZONE, 
	reason_code TEXT NOT NULL, 
	known_missing_count BIGINT, 
	estimated_missing_count BIGINT, 
	confidence_note TEXT, 
	recovery_state TEXT NOT NULL, 
	PRIMARY KEY (gap_id), 
	CONSTRAINT ck_critical_gap_known_count CHECK (known_missing_count IS NULL OR known_missing_count >= 0), 
	CONSTRAINT ck_critical_gap_estimated_count CHECK (estimated_missing_count IS NULL OR estimated_missing_count >= 0), 
	CONSTRAINT ck_critical_gap_interval CHECK (start_at IS NULL OR end_at IS NULL OR start_at <= end_at), 
	FOREIGN KEY(tenant_id) REFERENCES organizations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_id) REFERENCES data_sources (id) ON DELETE RESTRICT
)""",
)


def upgrade():
    for statement in DDL:
        op.execute(statement)
    for statement in GUARDS:
        op.execute(statement)


def downgrade():
    # Historical rollback harnesses may remove an empty additive schema only.
    # Lock all new tables before checking: no concurrent ingest can invalidate
    # the proof. Never drop populated evidence or weaken older retention guards.
    if op.get_context().as_sql:
        raise RuntimeError("Live emptiness proof required for critical-event downgrade")
    bind = op.get_bind()
    names = (
        "event_identity_registry",
        "protected_event_inbox",
        "protected_finalization_outbox",
        "critical_event_ledger",
        "durable_receipt_claim",
        "receipt_reaffirmation",
        "processing_outbox",
        "identity_conflict_audit",
        "delivery_gap_audit",
    )
    bind.exec_driver_sql("LOCK TABLE " + ", ".join(names) + " IN ACCESS EXCLUSIVE MODE")
    if any(
        bind.exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM " + name + " LIMIT 1)"
        ).scalar()
        for name in names
    ):
        raise RuntimeError(
            "Critical-event evidence is retained: roll back the application, not these tables"
        )
    for name in reversed(names):
        op.drop_table(name)
    for function in (
        "aptron_critical_mutable_state_only",
        "aptron_critical_failure_owner",
        "aptron_critical_collector_owner",
        "aptron_critical_source_owner",
        "aptron_critical_append_only",
    ):
        op.execute("DROP FUNCTION " + function + "()")


GUARDS = (
    """CREATE FUNCTION aptron_critical_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'critical-event evidence is immutable' USING ERRCODE='23514'; END $$""",
    *tuple(
        "CREATE TRIGGER "
        + name
        + "_immutable BEFORE UPDATE OR DELETE ON "
        + name
        + " FOR EACH ROW EXECUTE FUNCTION aptron_critical_append_only()"
        for name in (
            "event_identity_registry",
            "critical_event_ledger",
            "receipt_reaffirmation",
            "identity_conflict_audit",
            "delivery_gap_audit",
        )
    ),
    """CREATE FUNCTION aptron_critical_source_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE owner_id uuid; BEGIN
      SELECT organization_id INTO owner_id FROM data_sources WHERE id=NEW.source_id FOR SHARE;
      IF owner_id IS DISTINCT FROM NEW.tenant_id THEN
        RAISE EXCEPTION 'critical-event source owner mismatch' USING ERRCODE='23514';
      END IF; RETURN NEW; END $$""",
    """CREATE TRIGGER critical_source_owner BEFORE INSERT ON event_identity_registry
       FOR EACH ROW EXECUTE FUNCTION aptron_critical_source_owner()""",
    *tuple(
        "CREATE TRIGGER "
        + name
        + "_source_owner BEFORE INSERT ON "
        + name
        + " FOR EACH ROW EXECUTE FUNCTION aptron_critical_source_owner()"
        for name in ("identity_conflict_audit", "delivery_gap_audit")
    ),
    """CREATE FUNCTION aptron_critical_collector_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM 1 FROM event_identity_registry r
        JOIN managed_agents m ON m.id=NEW.collector_id AND m.organization_id=r.tenant_id
        JOIN collectors c ON c.id=m.collector_id AND c.data_source_id=r.source_id
        JOIN worker_identities w ON w.id=m.worker_id AND w.organization_id=r.tenant_id
        JOIN data_sources s ON s.id=c.data_source_id AND s.organization_id=r.tenant_id
        WHERE r.event_key=NEW.event_key FOR SHARE OF m,c,w,s;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'critical-event Collector source owner mismatch' USING ERRCODE='23514';
      END IF; RETURN NEW; END $$""",
    """CREATE TRIGGER critical_collector_owner BEFORE INSERT ON protected_event_inbox
       FOR EACH ROW EXECUTE FUNCTION aptron_critical_collector_owner()""",
    """CREATE FUNCTION aptron_critical_failure_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.original_failure_event_key IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM event_identity_registry a JOIN event_identity_registry b
        ON a.tenant_id=b.tenant_id AND a.source_id=b.source_id
        WHERE a.event_key=NEW.event_key AND b.event_key=NEW.original_failure_event_key
      ) THEN RAISE EXCEPTION 'critical-event recovery source mismatch' USING ERRCODE='23514';
      END IF; RETURN NEW; END $$""",
    """CREATE TRIGGER critical_failure_owner BEFORE INSERT ON critical_event_ledger
       FOR EACH ROW EXECUTE FUNCTION aptron_critical_failure_owner()""",
)

GUARDS += (
    """CREATE FUNCTION aptron_critical_mutable_state_only() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed text[]; BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'critical-event evidence is retained' USING ERRCODE='23514'; END IF;
      CASE TG_TABLE_NAME
        WHEN 'protected_event_inbox' THEN allowed=ARRAY['protection_state'];
        WHEN 'durable_receipt_claim' THEN
          allowed=ARRAY['current_reaffirmation_generation'];
          IF NEW.current_reaffirmation_generation < OLD.current_reaffirmation_generation THEN
            RAISE EXCEPTION 'receipt generation cannot regress' USING ERRCODE='23514'; END IF;
        WHEN 'protected_finalization_outbox' THEN
          allowed=ARRAY['state','claim_generation','claim_owner','claim_expires_at','next_attempt_at','last_error_category'];
          IF NEW.claim_generation < OLD.claim_generation THEN
            RAISE EXCEPTION 'claim generation cannot regress' USING ERRCODE='23514'; END IF;
        WHEN 'processing_outbox' THEN
          allowed=ARRAY['state','claim_generation','claim_owner','claim_expires_at','last_error_category','completed_at'];
          IF NEW.claim_generation < OLD.claim_generation THEN
            RAISE EXCEPTION 'claim generation cannot regress' USING ERRCODE='23514'; END IF;
      END CASE;
      IF (to_jsonb(NEW)-allowed) IS DISTINCT FROM (to_jsonb(OLD)-allowed) THEN
        RAISE EXCEPTION 'critical-event immutable fields changed' USING ERRCODE='23514'; END IF;
      RETURN NEW; END $$""",
    *tuple(
        "CREATE TRIGGER "
        + name
        + "_state_only BEFORE UPDATE OR DELETE ON "
        + name
        + " FOR EACH ROW EXECUTE FUNCTION aptron_critical_mutable_state_only()"
        for name in (
            "protected_event_inbox",
            "durable_receipt_claim",
            "protected_finalization_outbox",
            "processing_outbox",
        )
    ),
)
