# S03-AUTH-01 internal collector identity

The trusted operator enrolls the exact public leaf certificate against the installation and observed generation via `register_certificate`. The next generation is assigned under lock. Active registration grants submission and may explicitly grant source recovery. Rotating grants requires a fresh leaf. PostgreSQL retains old fingerprints and denies reuse. Certificate issuance, trust-store administration, operator authentication and production provisioning remain deployment responsibilities. Protect the registry writer as a security administrator.

The adapter owns the server-side TLS 1.3 handshake on an accepted socket using a dedicated client CA and required client certificates. It disables session tickets. For each request the caller uses the authenticator yielded by that connection in an explicit, non-autocommit PostgreSQL transaction. It resolves the SHA-256 fingerprint of the actual peer leaf and rechecks leaf validity against database time after locking. Forwarded certificate headers, bearer enrollment and request subject IDs cannot establish possession. The service has no listener or public route. Critical-event storage and acknowledgment issuance remain inactive.

An unlocked fingerprint lookup supplies routing hints. Authority reads then lock Organization, DataSource, Collector, ManagedAgent, WorkerIdentity and certificate generation in that order. They compare the full ownership chain, enabled flags, worker expiry, source configuration environment and requested capability. Locks remain held until the caller ends the transaction. The returned S02 binding is valid only in that transaction. Serialization or deadlock errors require rollback and a fresh authentication attempt. Use short transactions.

Revocation takes only the final certificate lock. A legacy disablement or ownership change takes its normal parent UPDATE lock and a database trigger revokes affected active leaves before commit. Re-enabling or moving back requires new enrollment. Legacy bearer clients use their existing authentication paths. Registration rejects incompatible or incomplete source configurations. It assumes trusted application code, the PostgreSQL authority and clock, protected CA/server keys and a correctly maintained dedicated trust store. This increment covers leaf revocation in PostgreSQL. It does not operate a CA or distribute CA revocation data.

## Reproduce the focused verification

From the repository root with Docker, OpenSSL, Python 3.12 and the backend requirements installed, run:

```bash
OPSCONTROL_TEST_PYTHON=.venv/bin/python bash scripts/test-collector-certificates.sh
```

The runner creates its own loopback-only PostgreSQL 17 instance and temporary PKI. It migrates forward, checks metadata drift, downgrades the empty registry and upgrades it again. The probe uses real TLS sockets and independent PostgreSQL sessions. It observes the blocked backend PID before releasing each race. It also checks stale or substituted subjects, insufficient grants, expired and missing client certificates, unknown or revoked leaves, rotation rollback, and retained certificate history. Tier A backend validation runs the same probe.
