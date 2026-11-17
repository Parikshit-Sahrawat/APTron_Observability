# Sprint 03 — transactional ingestion implementation brief

Prepared 17 November 2026. This is the next bounded increment after the reviewed #111 → #112 → #113 stack, not implemented ingestion or an approval to merge it. Existing production image/licensing and HA gates remain unchanged.

## Three separate reviewable changes

| Increment | Proposed branch | Deliverable | Explicit activation boundary |
|---|---|---|---|
| S03-TXN | `feat/s03-transactional-ingestion` | Internal PostgreSQL ingestion service, trusted registry adapter, concurrency/rollback tests and disposable probe | No public ingestion route, positive durability response, signer, receipt or external worker |
| S03-RECEIPT | `feat/s03-authenticated-receipts` | Reviewed IR-004 authenticated envelope, canonical signing input and verifier/signer interfaces | Issuance stays closed until the selected storage guarantee has independently demonstrated evidence; no production keys |
| S03-RECON | `feat/s03-critical-reconciliation` | Unknown-commit reconciliation, synchronous reaffirmation, CL-2 finalization and claim barriers | No external side effect without the demonstrated claim barrier and authenticated recovery authority |

Do not open empty placeholder PRs. Each draft must contain its implementation, negative tests, exact source/base and evidence. Owner review and manual merge remain required.

## S03-TXN contract and transaction

Input is a trusted transport principal plus a bounded, versioned event and canonical bytes. Payload tenant/source/Collector fields assert identity; they never confer authority. Wire Collector identity is ManagedAgent installation ID, not Collector configuration ID. Reject unsupported schema/canonicalization versions before any event write. Compute SHA-256 from the actual accepted canonical bytes and compare it with the envelope; never trust a supplied digest alone.

1. Enter a caller-owned, single PostgreSQL transaction on the intended writable primary. Require explicit environment/policy configuration; a staging transaction is not an HA guarantee. No implicit commit in an inner helper.
2. Take the same authority lock used by the relevant registry mutations, in a documented global lock order, then reload and lock the principal, installation, Collector configuration and DataSource owner. Reuse S02 authorization only after constructing its binding from these real rows. Recheck enabled/current-generation/capability/environment and authenticated principal equality. Missing generation or mTLS evidence fails closed; existing bearer enrollment does not imply the new transport contract.
3. Mutation endpoints must participate in the same locking protocol. Enumerate disable/delete/reassignment/credential-rotation paths and test each race. Row locks alone do not establish serialization against an uncoordinated external revocation service. If the shared protocol is unavailable, the adapter remains disabled rather than accepting a fabricated binding.
4. Insert registry identity with `ON CONFLICT (tenant_id, source_id, event_id) DO NOTHING`. PostgreSQL uniqueness arbitrates concurrent attempts. Read the winning row inside the transaction and compare tenant/source/event, digest, schema and canonicalization version exactly. Identical retry reuses its event key; any difference is a conflict, never an overwrite. Preserve conflict audit in an explicit denied-attempt transaction after rollback, with validated owner binding; never accidentally roll it back with a rejected payload or commit another caller's work.
5. Atomically insert the matching canonical inbox payload and finalization obligation, preserving unique identity and immutable payload. An existing inbox must match the original identity and installation/recovery contract; do not silently substitute a new installation on retry. Normal authorized transfer/recovery is a separate explicit procedure. No ledger, receipt claim or processing side effect is invented to suggest a stronger state.
6. A successful commit proves only the configured transaction completed. The initial internal service produces no transport acceptance or durability acknowledgment. Connection loss, cancellation or uncertain commit requires rollback/connection disposal and an indeterminate internal outcome. Finding an existing row with SELECT does not establish a durable receipt. Do not delete original evidence to retry.

The nine schema tables are SQLAlchemy Core tables: legacy ORM tenant criteria do not automatically protect their statements. Every service read/write must derive its tenant/source predicates from the trusted binding, and tests must attempt raw subject substitution. The database guards add relationship integrity; they do not replace per-request authorization, authentication, revocation checks or a least-privilege database role.

## Required tests before S03-TXN review

| Proof | Required negative / result |
|---|---|
| Atomicity | Inject failure after registry, inbox and outbox writes; no partial event state after rollback |
| Concurrent same retry | Two real PostgreSQL connections; one natural identity, one inbox, one obligation; identical stable event key |
| Concurrent conflict | Same natural identity with different bytes or versions; original immutable, denied attempt audited without payload/secret leakage |
| Ownership | Wrong tenant, source, installation, configuration or principal rejected; same-tenant wrong-source installation rejected too |
| Authority races | Disable, revoke, rotate, delete and reassign while ingestion is paused; either valid serialized commit or denial, never stale authorization |
| Caller ownership | A helper cannot commit unrelated pending work; SAVEPOINT failure does not certify the outer transaction |
| Unknown commit | Drop/cancel connection at commit boundary; no positive ACK or external side effect; replay cannot treat SELECT as a barrier |
| Legacy preservation | Fresh upgrade and populated legacy migration fixture; prior evidence and revision chain unchanged |
| Safety | No route registration, receipt issuance, signing keys, scheduler worker or outbox consumer activated |

Use real disposable PostgreSQL for concurrency/commit behavior; mocks cannot certify it. Extend the mandatory scope manifest for new test identities with RUN disposition and keep all 13 enforced contexts. No thresholds or protected assertions are removed.

## Later receipts and reconciliation

Authenticated receipts must bind issuer, algorithm/key purpose, customer/source/installation, event natural identity, digest, versions, policy, environment, receipt class and expiry as specified by the reviewed wire profile. A valid signature is not replication evidence. CL-2/HOST_PROTECTED and CL-3/CENTRAL_DURABLE issuance remain disabled until their respective synchronous storage, quorum/fencing and one-host-loss guarantees have demonstrated evidence. SQLite local acceptance is a separate guarantee and cannot be promoted by a central SELECT.

Reconciliation must require fresh authorized recovery identity, preserve contiguous checkpoints and original failures, and append gap/conflict evidence. An uncertain commit requires a fresh synchronous reaffirmation write and committed barrier before a claim can authorize work. Storage promotion, lost ACK, stale/revoked identity, duplicate replay and canceled synchronous commit need explicit failure tests. Single-runner disposable staging does not satisfy physical HA certification.
