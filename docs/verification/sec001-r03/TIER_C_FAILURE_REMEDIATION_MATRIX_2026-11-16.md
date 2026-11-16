# SEC001-R03 — Mandatory Tier C release-image remediation matrix

**Observed at:** 2026-11-16. **Source:** draft PR #108 head `6cae804cd647e0402a8ff04106e38683d102468c`.
**Gate:** `OC Dev - Tier C - Image SBOM Vulnerabilities and Licenses`, [run 43795602221](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43795602221).

**This is a truthful FAILED gate, not a broken Python test.**
`scripts/ci/image_security_gate.py` calls `security_manifest.validate()`
for every exact-image identity in the unchanged eight-role
`.ci/image-coverage.json`. All eight image-evidence collection jobs succeeded
and exact candidate coverage passed. The gate returns nonzero on *any*
Critical/High/Unknown match or pending independent License/NOTICE approval.
Do not `continue-on-error`, skip roles, allow vulnerability exceptions,
replace legal status with owner workbook approval, alter branch protection
or fabricate shipping OCI manifest digests.

## Release scan vs. qualified *non-release* candidates

| Mandatory release role | Actual release source at this head | Tier C blocker | Closest isolated candidate / measured result | Next real engineering action |
|---|---|---|---|---|
| backend-runtime | `backend/Dockerfile.runtime` (Debian/trixie) | **75 severe** | `backend/Dockerfile.alpine-r03-candidate --target runtime`: **4 High** SQLite | Resolve four High SQLite advisories with signed patched upstream/vetted Root.io package; run real backend API/RBAC/tenant isolation, library/musl, security and rollback qualification **before** any release Dockerfile switch |
| backend-migration | Same Dockerfile `migration` target | **75 severe** | Alpine target `migration`: **4 High** SQLite; real disposable PG17/Alembic upgrade PASSED | Qualify downgrade/data backup, schema compatibility, deterministic migrations and restore; reuse independent SQLite fix evidence |
| uat-backend | `backend/Dockerfile.uat`; embeds legacy Contrib 0.123.0 | **187 severe** | Alpine target `uat`: **112 severe** (19 Critical, 90 High, 3 Unknown) | Embedded 0.123.0 retains Go stdlib and x/crypto vulnerabilities. Qualify removal/separation/replacement of legacy binary and preserve operational UAT semantics; no silent removal or active pin change |
| frontend | `frontend/Dockerfile.demo` | **No severe block reported; License/NOTICE pending** | Same active image; not a legal approval | Final-image SPDX/NOTICE/source-offer review by independently appointed qualified reviewer |
| postgres | `deploy/release/Dockerfile.postgres` | **36 severe** | `deploy/release/Dockerfile.postgres-gosu-r03-candidate`: **zero severe**; disposable PG17 dump/restore, fsync etc passed | DBA + three real physically separate host Patroni/etcd/fencing certification, exact image manifest and independent Legal/NOTICE before release selection |
| ingestion-gateway | `deploy/release/Dockerfile.gateway` | **No severe block reported; License/NOTICE pending** | Active image; not a legal approval | Final image nginx assets/NOTICE/license/signature independent review |
| otel-contrib | Pinned upstream `0.123.0@sha256:e39311df...` | **108 severe** | Rebuilt patched 0.165 full Contrib **zero severe**; isolated mTLS and local filelog checkpoint rollback test PASSED via `0.163.2` JSON bridge | No active pin switch. Certify bridge/replacement's security, complete multi-stream checkpoint/rotation/truncation, tenant/source identity, CL-1/CL-2/CL-3 receipt durability, HA and legal; native Collector migration boundary preserved |
| production-frontend | `frontend/Dockerfile.runtime` | **No severe block reported; License/NOTICE pending** | Active image; not a legal approval | Independently signed final OCI image license, attribution, source-offer review |

Measured candidate findings are from **the same source head**, [isolated SEC001-R03 run 43795602184](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43795602184). The image config SHA-256 recorded by Syft/Grype is **not** by itself a final registry OCI manifest digest. Rebuilding or replacing a final image invalidates previous image-specific approvals.

## Important newly qualified result

The patched 0.165 rebuilt Collector **passed** local mTLS admission and local filelog
restart. The isolated test `0.123.0 → patched 0.165.0 →
0.163.2 --feature-gates=-filelog.protobufCheckpointEncoding → 0.123.0`
also **passed** on [job 133063668281](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43795602184/job/133063668281)
without deleting the checkpoint or replaying previously observed log markers.

This is a **bounded local test** only; 0.163.2 is a non-release interim
image and is not itself zero-severe, DBA certified, independently legally
approved or proven safe for durable CL-2/CL-3 workload recovery.

## Practical order of work — never turn off Tier C

1. Collect digest-bound candidate Syft, CycloneDX and Grype reports; retain
   exact OS, component, package and advisory IDs in the evidence archive.
2. Resolve Alpine SQLite four High advisories by independently authenticated
   vendor/upstream fix and **verify actual binary/ABI and redistribution**.
   Current Root.io supplier keys/APKs/entitlements are **not supplied**.
3. For UAT, qualify the whole observability topology when replacing embedded
   0.123.0; no deleting its executable just for a clean scanner result.
4. Finish Collector end-to-end and rollback certification before release pin
   change. Keep upstream 0.123 until native/transition boundary owner accepted.
5. Finish three actual independent hosts / Patroni/etcd/fencing, durable
   receipt loss oracle and all nine independently witnessed failure scenarios.
6. Have **qualified independent** security/legal reviewer sign license, NOTICE,
   source offers and allowed vendor redistribution for **all eight final
   immutable OCI manifest digests**, then seek independent GitHub writer
   review and owner release decision. Prior owner-reviewed workbook is
   technical triage only.

**Current mandatory Tier C verdict:** eight of eight release roles blocked.
**Policy:** `UNMODIFIED_ZERO_SEVERE_AND_ACCOUNTABLE_LICENSE_REVIEW`.
**Merge/deploy/release:** NOT APPROVED. No branch protection/policy change.
