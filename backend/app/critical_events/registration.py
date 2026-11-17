"""Internal certificate provisioning and per-request PostgreSQL authority checks."""

import hashlib
import socket
import ssl
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select, func
from app.critical_events.identity import (
    AuthenticatedCollector,
    RegistryBinding,
    UnauthorizedSource,
    authorize_source,
)
from app.critical_events.models import certificates
from app.models import Organization, DataSource, Collector
from app.telemetry.models import ManagedAgent
from app.security.models import WorkerIdentity


def _deny():
    raise UnauthorizedSource("Current registered installation required")


def _transaction(db):
    if (
        db.dialect.name != "postgresql"
        or not db.in_transaction()
        or db.connection.driver_connection.autocommit
    ):
        raise RuntimeError("Explicit PostgreSQL transaction required")


def _lock(db, table, key):
    row = (
        db.execute(select(table).where(table.c.id == key).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        _deny()
    return row


def _authority(db, tenant_id, source_id, configuration_id, installation_id):
    # Legacy UPDATE/DELETE necessarily conflicts with these same row locks.
    org = _lock(db, Organization.__table__, tenant_id)
    source = _lock(db, DataSource.__table__, source_id)
    collector = _lock(db, Collector.__table__, configuration_id)
    agent = _lock(db, ManagedAgent.__table__, installation_id)
    worker = _lock(db, WorkerIdentity.__table__, agent.worker_id)
    if not (
        org.active
        and source.enabled
        and collector.enabled
        and agent.enabled
        and worker.enabled
        and org.id
        == source.organization_id
        == agent.organization_id
        == worker.organization_id
        and collector.data_source_id == source.id
        and agent.collector_id == collector.id
        and collector.remote_worker_id == worker.id
    ):
        _deny()
    config = source.connection_config
    scope = config.get("opscontrol") if isinstance(config, dict) else None
    env = scope.get("environment") if isinstance(scope, dict) else None
    if not isinstance(env, str) or not env.strip():
        _deny()
    return worker, env


def register_certificate(
    db,
    *,
    tenant_id,
    source_id,
    configuration_id,
    installation_id,
    certificate_pem,
    expected_generation,
    recovery=False
):
    """Trusted provisioning only. Require the operator's observed latest generation."""
    _transaction(db)
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate_pem)).digest()
    with db.begin_nested():
        worker, env = _authority(
            db, tenant_id, source_id, configuration_id, installation_id
        )
        prior = (
            db.execute(
                select(certificates)
                .where(certificates.c.installation_id == installation_id)
                .order_by(certificates.c.generation.desc())
                .limit(1)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        generation = prior.generation if prior else 0
        if generation != expected_generation:
            _deny()
        if prior and not prior.revoked:
            revoke_certificate(db, prior.fingerprint)
        db.execute(
            certificates.insert().values(
                fingerprint=fingerprint,
                installation_id=installation_id,
                generation=generation + 1,
                tenant_id=tenant_id,
                source_id=source_id,
                configuration_id=configuration_id,
                worker_id=worker.id,
                environment=env,
                recovery=recovery,
            )
        )
    return generation + 1


def revoke_certificate(db, fingerprint):
    """Revoke this exact leaf, including after the legacy installation is disabled."""
    _transaction(db)
    result = db.execute(
        certificates.update()
        .where(certificates.c.fingerprint == fingerprint, ~certificates.c.revoked)
        .values(revoked=True)
    )
    if result.rowcount != 1:
        _deny()


class CollectorTransport:
    """Dedicated direct TLS terminator. No HTTP or ingestion handler is installed."""

    def __init__(self, *, server_certificate, server_key, client_ca):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.num_tickets = 0
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=client_ca)
        ctx.load_cert_chain(server_certificate, server_key)
        self._context = ctx

    @contextmanager
    def accept(self, raw_socket):
        if type(raw_socket) is not socket.socket:
            _deny()
        with self._context.wrap_socket(raw_socket, server_side=True) as stream:
            peer = stream.getpeercert()
            fingerprint = hashlib.sha256(stream.getpeercert(binary_form=True)).digest()
            expires = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(peer["notAfter"]), timezone.utc
            )
            issued = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(peer["notBefore"]), timezone.utc
            )

            def authenticate(
                db, *, tenant_id, source_id, collector_id, environment, capability
            ):
                _transaction(db)
                if stream.fileno() < 0:
                    _deny()
                lookup = select(certificates).where(
                    certificates.c.fingerprint == fingerprint
                )
                hint = db.execute(lookup).mappings().one_or_none()
                if hint is None:
                    _deny()
                worker, env = _authority(
                    db,
                    hint.tenant_id,
                    hint.source_id,
                    hint.configuration_id,
                    hint.installation_id,
                )
                row = db.execute(lookup.with_for_update()).mappings().one()
                now = db.scalar(select(func.clock_timestamp()))
                if (
                    row.revoked
                    or row.worker_id != worker.id
                    or env != row.environment
                    or not issued <= now < expires
                    or worker.expires_at <= now
                ):
                    _deny()
                capabilities = {"critical-event:submit"}
                if row.recovery:
                    capabilities.add("recover:source-events")
                principal = AuthenticatedCollector(
                    fingerprint.hex(), row.installation_id, row.generation, True
                )
                binding = RegistryBinding(
                    tenant_id=row.tenant_id,
                    source_id=row.source_id,
                    installation_id=row.installation_id,
                    configuration_collector_id=row.configuration_id,
                    principal_id=row.fingerprint.hex(),
                    generation=row.generation,
                    source_owner_id=row.tenant_id,
                    collector_source_id=row.source_id,
                    installation_collector_id=row.configuration_id,
                    environment=env,
                    capabilities=frozenset(capabilities),
                )
                return authorize_source(
                    principal,
                    binding,
                    tenant_id=tenant_id,
                    source_id=source_id,
                    collector_id=collector_id,
                    environment=environment,
                    capability=capability,
                )

            yield stream, authenticate
