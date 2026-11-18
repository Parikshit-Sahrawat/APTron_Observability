# Internal critical-event ingestion

S03-TXN-01 builds on the certificate registry and the existing IR-002 tables. A trusted host configures IngestionService with a PostgreSQL engine, protection policy label, server identity and client CA. Its accept context performs the S03-AUTH-01 handshake on an accepted socket. The yielded submit function is scoped to that live server connection. Each call acquires its own database connection and transaction. No application route or automatic reader invokes it.

## Input and authority

The internal Submission carries the S02 natural identity, claimed installation and environment, and already-canonical source bytes. This increment accepts the schema and canonicalization labels 1.0 used by the schema fixture. It accepts opaque nonempty payloads up to 1 MiB and verifies SHA-256 over those exact bytes before writing. Wire parsing and generating canonical bytes from structured events are outside this interface. Event IDs retain S02's 512-character limit. The internal result is a UUID suitable for looking up local state.

The existing TLS adapter freshly locks Organization, DataSource, Collector, ManagedAgent, WorkerIdentity and certificate generation, in that order, within the write transaction. Only the live submission capability admits a new event or ordinary retry. Per-request fields supply comparisons. The registry uses the authenticated tenant and source, and the inbox records the wire installation. A replacement installation cannot take over an ordinary retry.

## Atomic writes and conflict evidence

PostgreSQL arbitrates the immutable tenant/source/event key with INSERT ON CONFLICT DO NOTHING. The insertion winner writes the canonical inbox and a pending finalization obligation in the same transaction. A retry must find both rows and match the original installation, versions, digest and canonical bytes. An incomplete pre-existing chain fails closed.

An identity conflict rolls back the event transaction. On a new transaction, the service authenticates again, reloads the winning immutable row and verifies the conflict before committing an audit record. That record contains the natural key, digest pair, certificate fingerprint, detection time and original event key. An intervening revocation or database failure can prevent the audit commit and surfaces as an error. The caller's unrelated database work has its own transaction. No receipt, ledger entry, processing claim, external action or delivery acknowledgment follows from this operation.

## Commit boundaries

The commit wrapper listens for PostgreSQL warnings with the session's local message threshold set to warning. PostgreSQL can complete a local commit while canceling a synchronous replication wait. A commit exception or warning invalidates the connection and raises CommitIndeterminate. A retry reauthenticates and can find or insert the event locally. It supplies no proof of replication or durability. Receipt issuance and synchronous reaffirmation require separately reviewed work.

## Reproduction

From the repository root with Python dependencies installed, run:

```bash
OPSCONTROL_TEST_PYTHON=.venv/bin/python bash scripts/test-collector-certificates.sh
```

The existing CI entry point owns its PostgreSQL 17 container and temporary TLS material. Normal fixture commits use local synchronous commit. A deliberately absent standby allows the two commit-boundary tests to observe a real SyncRep wait, cancel or terminate the waiting backend, and replay. The other independent-session tests observe actual lock waiters before releasing admission. Test-only SQLAlchemy hooks inject exceptions immediately after each successful INSERT. The runner also checks migration metadata, downgrade/re-upgrade and certificate-registry behavior.
