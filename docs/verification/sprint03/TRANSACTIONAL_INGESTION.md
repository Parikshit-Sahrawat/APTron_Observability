# Internal critical-event ingestion

S03-TXN-01 builds on the certificate registry and the existing IR-002 tables. A trusted host configures IngestionService with a PostgreSQL engine, an explicit ProtectionPolicy, server identity and client CA. Its accept context performs the S03-AUTH-01 handshake on an accepted socket. The yielded submit function is scoped to that live server connection. Each call acquires its own database connection and transaction. No application route or automatic reader invokes it.

## Input and authority

The internal Submission carries the S02 natural identity, claimed installation and environment, and already-canonical source bytes. This increment accepts the schema and canonicalization labels 1.0 used by the schema fixture. It accepts opaque nonempty payloads up to 1 MiB and verifies SHA-256 over those exact bytes before writing. Wire parsing and generating canonical bytes from structured events are outside this interface. Event IDs retain S02's 512-character limit. The internal result is a UUID suitable for looking up local state.

The existing TLS adapter freshly locks Organization, DataSource, Collector, ManagedAgent, WorkerIdentity and certificate generation, in that order, within the write transaction. Only the live submission capability admits a new event or ordinary retry. Per-request fields supply comparisons. The registry uses the authenticated tenant and source, and the inbox records the wire installation. A replacement installation cannot take over an ordinary retry.

## Atomic writes and conflict evidence

PostgreSQL arbitrates the immutable tenant/source/event key with INSERT ON CONFLICT DO NOTHING. The insertion winner writes the canonical inbox and a pending finalization obligation in the same transaction. A retry must find both rows and match the original installation, versions, digest and canonical bytes. An incomplete pre-existing chain fails closed.

An identity conflict rolls back the event transaction. On a new transaction, the service authenticates again, reloads the winning immutable row and verifies the conflict before committing an audit record. That record contains the natural key, digest pair, certificate fingerprint, detection time and original event key. An intervening revocation or database failure can prevent the audit commit and surfaces as an error. The caller's unrelated database work has its own transaction. No receipt, ledger entry, processing claim, external action or delivery acknowledgment follows from this operation.

## Commit boundaries

The commit wrapper listens for PostgreSQL warnings with the session's local message threshold set to warning. PostgreSQL can complete a local commit while canceling a synchronous replication wait. A COMMIT warning or an error with an uncertain outcome invalidates the connection and raises CommitIndeterminate. A PostgreSQL serialization rejection (SQLSTATE 40001) aborts the transaction. At COMMIT the service discards that connection and propagates the definite rejection. A retry reauthenticates and can find or insert the event locally. It supplies no proof of replication or durability. Receipt issuance and synchronous reaffirmation require separately reviewed work.

## Reproduction

From the repository root with Python dependencies installed, run:

```bash
OPSCONTROL_TEST_PYTHON=.venv/bin/python bash scripts/test-collector-certificates.sh
```

The existing CI entry point owns its PostgreSQL 17 container and temporary TLS material. Normal fixture commits use local synchronous commit. A physical standby exercises the recovery-mode guard. A deliberately unmatched synchronous standby name allows the two commit-boundary tests to observe a real SyncRep wait, cancel or terminate the waiting backend, and replay. The other independent-session tests observe actual lock waiters before releasing admission. Test-only SQLAlchemy hooks inject exceptions immediately after each successful INSERT. The runner also checks migration metadata, downgrade/re-upgrade and certificate-registry behavior.

## Writable primary and isolation (TXN-R01 and TXN-R03)

The only supported policy is `disposable-local`. The trusted host supplies its environment, database name, cluster system identifier, and the intended primary's server-side TCP address and port. Provision these values through a trusted channel independent of the engine being checked. The fixture obtains the cluster identifier through a local administrative connection inside its own container and the address from Docker. A client has no field for selecting a policy. The connection role must be able to read `pg_catalog.pg_control_system()`. An unreadable setting or missing privilege aborts admission.

On the same connection as each event write or conflict audit, the service checks the pins, PostgreSQL major version 17, psycopg transaction mode, recovery state, and session and transaction writability. It requires `fsync=on`, `full_page_writes=on`, origin-mode triggers, and effective schemas `pg_catalog, public`. The allowed synchronous commit modes are local, on, remote_write and remote_apply. These checks assume a trusted, access-controlled database endpoint, schema and administrator. A restored or promoted physical copy can share a system identifier, and an address can be reused. Physical fencing, storage behavior and exclusive cluster leadership require independent operational evidence.

Admission uses READ COMMITTED. Each statement takes a fresh snapshot, so a uniqueness conflict can be followed by a read of the committed winner. The authority locks span validation, writes and commit. Autocommit and other isolation levels fail before admission. A serialization failure during a statement rolls back all writes. A consuming host can explicitly resubmit the original event through a live authenticated connection. Each attempt checks authority again. The fixture forces SQLSTATE 40001 on the final insert and on deferred COMMIT, checks the row counts through an independent connection, and verifies a clean retry. It also switches the second transaction of a conflict to read-only to verify that the audit repeats the primary check.

## Contention and authority (TXN-R02 and TXN-R04)

Two independent installations use distinct sources, configuration rows, workers, certificates and event IDs under one organization. With the first submission paused before commit, the fixture observes its PostgreSQL backend blocking the second. Both complete once the lock is released. For a timing sample, each installation submits 24 fresh events. The fixture measures sequential batches and two concurrent batches using the same live TLS connections. A local sample appears below. Results include PostgreSQL round trips and are sensitive to machine load.

| Active clients | Total events | Events/s | Median (ms) | p95 (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 48 | 105.6 | 8.57 | 16.03 |
| 2 | 48 | 144.1 | 13.16 | 20.89 |

For a future optimization, measure lock wait duration with representative tenant load. A reader-side `FOR SHARE` on the organization row could allow independent readers while conflicting with updates and deletes. Before adoption, prove that every authority writer conflicts in the same lock order, check any read-to-write lock upgrades for deadlocks, and repeat the mutation and deletion races in both orders. A key-share lock alone permits non-key updates such as tenant disablement.

The mandatory fixture exercises source and installation DELETE while a submission holds the parent locks. After admission commits, the attempted delete fails with SQLSTATE 23503 and the parent and inbox provenance survive. The migration fixture seeds an unenrolled installation at revision 0039, compares its full row after 0040, checks that it acquired no certificate, and verifies RESTRICT on all five certificate foreign keys. With a TLS session already open, source disablement, configuration reassignment, rotation and revocation committed before admission each deny a fresh event.

## Conflict evidence and canonicalization (TXN-R05)

Equal hashes are possible in an audited conflict when only a version differs. The immutable winner records both of its versions. The audit stores the winning event reference and two hashes. It omits the attempted versions and the reason for the mismatch. The historical winner and the audit alone cannot establish which version field the attempt carried. Incoming versions outside the supported 1.0 pair fail input validation before conflict comparison. A historical winner can still carry another version.

This interface checks exact bytes, length, accepted version labels and SHA-256. It treats the bytes as opaque. Semantically equivalent JSON with different whitespace or key order can conflict. The caller owns canonicalization. The service does not parse, normalize or attest to the supplied encoding. Before admitting another version, consider an additive migration with nullable bounded attempted schema and canonicalization version columns and a constrained mismatch reason (or reason flags for combined differences). Populate them only from a newly observed, revalidated attempt in the conflict transaction. Preserve historical unknowns. This proposal requires owner review and has no wire-format changes.

## Review evidence

The review base is PR #116 at `d440fd3d5a7c5d826e6563aee175c25b823dbfd3` on top of PR #114 at `fc16b7653851a984249ef6acf18dc29945f599ba`. The following hosted results belong to the review base.

| Hosted job | Result and evidence |
| --- | --- |
| [Frontend dependency audit](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/44208290251/job/134479827689) | Failed. Artifact `14385380761` matches GitHub’s SHA-256 `71a2d44872b7319f893c20fdebc7df54ce33b27469609c4f236063e4ef131d5d`. Runtime audit has zero findings. Full audit has four High package entries for one Picomatch advisory, GHSA-fc5q-39xc-vjpf, affecting Picomatch, fdir, Tinyglobby and Vite. Both results match the PR #114 audit. |
| [Image security policy](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/44208290391/job/134480732613) | Failed. Artifact `14384757005` matches SHA-256 `a04379e0d3bfaa2bb86721d6de9efea0e059314ad6f2428d01b8c50d4e1a0c84`. Coverage passed. Severe or unknown matches blocked backend runtime (4), backend migration (4), UAT backend (111), and OTel (107). License/NOTICE review blocked frontend, PostgreSQL, ingestion gateway and production frontend. The recorded policy step exited 1. |
| [Disposable staging](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/44208290570/job/134479828689) | Passed, including the isolated deployment, functionality and cleanup step. |
| [Verification](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/44208290922/job/134479829979) | In progress at inspection. The supplied archive contained no verification-step log. The local security command independently reproduced the npm failure. |

Correction validation used the following repository entry points.

| Command | Local outcome |
| --- | --- |
| `OPSCONTROL_TEST_PYTHON=.venv/bin/python bash scripts/test-collector-certificates.sh` | Fresh PG17 migration, Alembic metadata check, downgrade/re-upgrade, certificate registration probe and all 15 ingestion tests passed. The fixture ran all seven original and eight additional cases. |
| `cd backend && ENV=test .venv/bin/python -m unittest discover -s tests -v` | 574 discovered, 339 passed, 235 skipped under ordinary discovery. The dedicated PG17 command above runs the ingestion tests with the database fixture enabled. |
| `backend/.venv/bin/python -m unittest discover -s tests -v` and `backend/.venv/bin/python scripts/ci/policy.py` | 158 repository tests passed. Policy verified 752 inventoried tests and all 13 required CI contexts. |
| `cd frontend && npm ci --no-audit --no-fund && npm test && npm run lint && npm run build` | Passed on Vite 7.3.7 using a writable npm cache. |
| `npm audit --omit=dev --audit-level=moderate` and `npm audit --audit-level=moderate` in frontend | Runtime passed. Full audit failed with four High entries from the inherited Picomatch advisory. |
| `make test-security` | Authorization and other security tests passed. Dependency audit reported `pip=0 npm=1`. |
| `V16_BROWSER_ACCEPTANCE=1 V16_API_ACCEPTANCE=1 V16_STAGING_PRESERVATION=1 backend/.venv/bin/python scripts/v16-acceptance.py` | Local disposable database, migration preservation, HTTP and browser acceptance passed using the installed Playwright module. The image-gated staging entry point requires a GitHub-hosted runner. |

A separate fresh local PostgreSQL 17 database and loopback API also passed the three staging probes (`scripts.auth_tenant_probe`, `scripts.deep_tenant_security_probe` and `scripts.critical_event_schema_probe`). The schema probe passed all 35 checks, including empty and populated downgrade behavior.

For owner review, confirm the new commit's backend-validation fixture and disposable-staging evidence, the disposition of every required context, and the independent image-security result. Review the disposable-only policy pins and the organization lock cost. Decide on additive audit evidence before supporting additional version pairs. Physical fencing and positive durability acknowledgments remain outside this verification.
