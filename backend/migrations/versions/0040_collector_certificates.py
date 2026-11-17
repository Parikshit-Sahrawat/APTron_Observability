"""Register installation certificate generations without enrolling legacy agents."""

from alembic import op, context

revision = "0040_collector_certificates"
down_revision = "0039_critical_event_storage"
branch_labels = depends_on = None


# Parent row updates already own the row lock. Invalidate at the same commit,
# including an away-and-back reassignment or disable/enable cycle.
PARENTS = {
    "organizations": ("tenant_id", "NOT NEW.active"),
    "data_sources": (
        "source_id",
        """NOT NEW.enabled OR NEW.organization_id <> OLD.organization_id
        OR (NEW.connection_config::jsonb #>> '{opscontrol,environment}') IS DISTINCT FROM
           (OLD.connection_config::jsonb #>> '{opscontrol,environment}')""",
    ),
    "collectors": (
        "configuration_id",
        """NOT NEW.enabled OR NEW.data_source_id <> OLD.data_source_id
        OR NEW.remote_worker_id IS DISTINCT FROM OLD.remote_worker_id""",
    ),
    "managed_agents": (
        "installation_id",
        """NOT NEW.enabled OR NEW.organization_id <> OLD.organization_id
        OR NEW.collector_id <> OLD.collector_id OR NEW.worker_id <> OLD.worker_id""",
    ),
    "worker_identities": (
        "worker_id",
        "NOT NEW.enabled OR NEW.organization_id <> OLD.organization_id",
    ),
}


def upgrade():
    op.execute("""
        CREATE TABLE collector_certificates (
            fingerprint bytea PRIMARY KEY CHECK (octet_length(fingerprint) = 32),
            installation_id uuid NOT NULL REFERENCES managed_agents ON DELETE RESTRICT,
            generation bigint NOT NULL CHECK (generation > 0),
            tenant_id uuid NOT NULL REFERENCES organizations ON DELETE RESTRICT,
            source_id uuid NOT NULL REFERENCES data_sources ON DELETE RESTRICT,
            configuration_id uuid NOT NULL REFERENCES collectors ON DELETE RESTRICT,
            worker_id uuid NOT NULL REFERENCES worker_identities ON DELETE RESTRICT,
            environment text NOT NULL CHECK (btrim(environment) <> ''),
            recovery boolean NOT NULL DEFAULT false,
            revoked boolean NOT NULL DEFAULT false,
            UNIQUE (installation_id, generation)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_collector_current_certificate ON collector_certificates (installation_id) WHERE NOT revoked"
    )
    op.execute("""
        CREATE FUNCTION guard_collector_certificate() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND NOT OLD.revoked AND NEW.revoked
             AND (to_jsonb(NEW) - 'revoked') = (to_jsonb(OLD) - 'revoked') THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Certificate generations are retained and immutable';
        END $$;
    """)
    op.execute(
        "CREATE TRIGGER guard_collector_certificate BEFORE UPDATE OR DELETE ON collector_certificates FOR EACH ROW EXECUTE FUNCTION guard_collector_certificate()"
    )

    op.execute(
        "CREATE TRIGGER retain_certificate_history BEFORE TRUNCATE ON collector_certificates FOR EACH STATEMENT EXECUTE FUNCTION guard_collector_certificate()"
    )

    for parent, (column, changed) in PARENTS.items():
        op.execute(f"""
            CREATE FUNCTION revoke_certificate_for_{parent}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                UPDATE collector_certificates SET revoked = true WHERE {column} = NEW.id AND NOT revoked;
                RETURN NEW;
            END $$;
        """)
        op.execute(
            f"""CREATE TRIGGER revoke_certificate AFTER UPDATE ON {parent}
            FOR EACH ROW WHEN ({changed}) EXECUTE FUNCTION revoke_certificate_for_{parent}()"""
        )


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Online certificate registry check required")
    op.execute("LOCK TABLE collector_certificates IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .exec_driver_sql("SELECT EXISTS(SELECT FROM collector_certificates)")
        .scalar_one()
    ):
        raise RuntimeError("Certificate evidence is retained")
    for parent in PARENTS:
        op.execute(f"DROP TRIGGER revoke_certificate ON {parent}")
        op.execute(f"DROP FUNCTION revoke_certificate_for_{parent}()")
    op.drop_table("collector_certificates")
    op.execute("DROP FUNCTION guard_collector_certificate()")
