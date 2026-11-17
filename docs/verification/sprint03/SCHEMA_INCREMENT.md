# Sprint 03 — first bounded schema increment

Owner authorization: 16 November 2026, following S02-ID-01 contract approval. Stack: reviewed #110 harness/foundation content → #111 Organizations stabilization → S02 authority contract → this schema-only draft. No merge or retarget is authorized by implementation.

## Implemented scope

Nine IR-002 central tables: event_identity_registry, protected_event_inbox, protected_finalization_outbox, critical_event_ledger, durable_receipt_claim, receipt_reaffirmation, processing_outbox, identity_conflict_audit and delivery_gap_audit. `tenant_id` and `source_id` use the existing Organization/DataSource UUID identities; wire event_id remains opaque text. Inbox collector_id references ManagedAgent installation identity, not configuration Collector.id.

Frozen migration `0039_critical_event_storage` follows `0038_k8s_cluster_associations`; the historical revision name does not reintroduce excluded Kubernetes functionality. Upgrade adds tables, indexes, constraints and functions/triggers on new tables only. No legacy row is backfilled or modified. Application metadata registers the dormant tables so drift checks see them; no ingestion, enrollment, signer, receipt route or worker is enabled.

Constraints enforce unique natural event identity, 32-byte hashes, per-event receipt class uniqueness, positive reaffirmation generations and external side-effect idempotency. All foreign-key deletion is RESTRICT. Identity/ledger/audit/reaffirmation evidence is append-only; protected payload/receipt subjects/outbox identities are immutable while permitted operational states may advance and claim generations may not regress. Registry insertion checks the current DataSource tenant under a row lock. Recovery/failure links cannot cross tenant/source identity.

Application rollback may keep additive tables. Database downgrade acquires ACCESS EXCLUSIVE locks on all nine new tables, proves every one empty, and only then removes the empty schema. Any critical evidence blocks downgrade before a table is dropped; offline downgrade cannot bypass the live proof. Historical retention guards remain unchanged. No retention period or exception is invented.

## Evidence and remaining acceptance

Local: seven new identity/schema contract tests, frozen-model/DDL agreement, PostgreSQL offline Alembic 0038→0039 rendering, formatting, policy and root controller checks. First local DDL compilation exposed a missing registration of ManagedAgent metadata; explicit metadata imports corrected it. Real DB/browser results are pending CI, not local passes.

The existing disposable staging migration applies 0039 to a fresh private PostgreSQL database. A new guarded `critical_event_schema_probe` requires APTRON_DISPOSABLE_STAGING=1, ENVIRONMENT=test and database aptron_staging. It executes real insertion, natural-key duplication, malformed digest, cross-customer source rejection, immutable hash and deletion negatives, checks the original digest and rolls its synthetic transaction back. Existing migration, tenant/browser/restart/cleanup checks stay enabled.

Before merge: exact-head PostgreSQL migration/model drift, populated old-data preservation, empty downgrade compatibility, populated critical-evidence downgrade refusal, DB concurrency/revocation negatives and all relevant CI need review. Schema tests alone are not HA/durability or security certification. Production image/license findings, independent legal decisions and physical HA/fencing remain release gates; staging exceptions are unchanged.

## Separate subsequent reviewable PRs

| Increment | Dependency | Bounded work | Acceptance required |
|---|---|---|---|
| S03-TXN | Reviewed S02 + schema | Per-request authenticated registry binding under consistent locks; conflict-safe registry insertion; transactional inbox/ledger/claim/outbox; no premature response | Concurrent duplicate/conflict, revocation/reassignment races, rollback and unknown commit, synchronous policy/fenced-primary denial; no receipt based on SELECT |
| S03-RECEIPT | Reviewed transaction proof + IR-004/005 profile | JCS canonical claims and vetted ES256 JWS; issuer/algorithm/key-purpose/policy/environment/event/digest binding; signer interface | Wrong issuer/alg/key/tenant/source/collector/hash/version/policy, external claims mismatch, expired/revoked identity and replay negatives; no production private-key/HSM action |
| S03-RECON | Reviewed transaction + receipt semantics | Fresh synchronous reaffirmation, CL-2 finalization, durable processing claim barrier, idempotent replay and contiguous checkpoints | Lost ACK, canceled commit, primary promotion, source replacement recovery authorization, gap and conflict audit; no external side effect on uncertain claim |

These subsequent increments remain authorized sequencing targets, not completed functionality or empty placeholder PRs. Their exact migrations, wire contract and trust/durability prerequisites must be reviewable before implementation/promotion. A valid signature is not replication proof. Physical HA remains deferred until production readiness, never marked passed by single-runner staging.

## 17 November focused model/migration review

Natural identity is database-unique on `(tenant_id, source_id, event_id)` independently of digest/version; conflicting retries cannot create a second registry identity. Digest/version equality still needs the S02 transaction comparison. Nine new tables use restrictive foreign keys and immutable subject/payload guards. No migration 0001–0038, historical retention function or legacy table definition is modified.

Review found independently valid foreign keys did not establish inbox installation ownership or audit source ownership. New INSERT guards join ManagedAgent → Collector → DataSource and WorkerIdentity against the event's tenant/source under shared row locks, and validate source ownership on conflict/gap audit insertion. These relationship guards do not certify mTLS, current generation, capability, revocation, HA or synchronous replication. Legacy reassignment is not prohibited by a new trigger on a legacy table; the next service must coordinate authoritative mutations and preserve historical event identity.

Expanded disposable probe exercises matching and wrong-source/wrong-customer installations, cross-customer audits, all nine DELETE guards, immutable payload/ledger/receipt/audit/outbox subjects and generation regression, while allowing operational-state updates. It calls the real downgrade inside a rolled-back SAVEPOINT: empty schema removal/restoration, populated-evidence refusal, unchanged legacy organization snapshot and Alembic version. All synthetic writes (including unsigned receipt fixtures) are rolled back; no receipt is issued. Exact-head live results remain pending until CI completes.

Prepared next increment: [transactional ingestion implementation brief](TRANSACTIONAL_INGESTION_PLAN.md). Receipts and reconciliation remain separate reviewable changes, with positive durability acknowledgments disabled pending demonstrated guarantees.
