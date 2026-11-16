# SEC001-R03 — Actual release-source hardening, pending final PR-head rescans

**Prepared 16 November 2026; draft PR #108.** This report is not a license
decision, a security waiver, a final registry OCI digest, or a release approval.

## Engineering changes selected into draft release sources

| Tier C role | Prior mandatory scan | New exact release-source selection | Verified precursor evidence | New current-head mandatory scan |
|---|---|---|---|---|
| postgres | 36 severe | `deploy/release/Dockerfile.postgres` builds verified gosu 1.19 under Go1.27.4 over original PG17 base | **0 severe** in mandatory run [43800567508](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43800567508) after selecting source | Must regenerate at latest PR merge SHA |
| backend-runtime | 75 severe | `backend/Dockerfile.runtime` selects Alpine 3.23, exact Python 3.12.16, musl/pinned psutil wheel | Independent candidate **4 High**, `sqlite-libs 3.53.4-r0` | **PENDING** fresh mandatory Tier C |
| backend-migration | 75 severe | Same Alpine Dockerfile, stage `migration`, retains Alembic | Independent candidate **4 High**, real PG17 migrations passed | **PENDING** fresh mandatory Tier C |
| uat-backend | 187 severe | `backend/Dockerfile.uat` selects Alpine hardened legacy UAT preserving pinned Contrib 0.123 binary | Independent candidate **112 severe** (19 Critical,90 High,3 Unknown) | **PENDING** fresh mandatory Tier C |
| frontend | License pending | unchanged | legal signoff missing | PENDING |
| ingestion-gateway | License pending | unchanged | legal signoff missing | PENDING |
| otel-contrib | 108 severe | release pinned upstream 0.123 unchanged | rebuilt patched 0.165 isolated **0 severe** with bounded local mTLS/checkpoint/JSON bridge tests; **not promoted** | PENDING independent full Collector durability and ABI security/legal |
| production-frontend | License pending | unchanged | legal signoff missing | PENDING |

### Important separate UAT experimental result — NOT a release image

[Isolated same-workflow UAT comparison run 43800966135, job 133084788289](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43800966135/job/133084788289):
hardened Alpine UAT with rebuilt 0.165 (exact binary SHA verified and same-source
artifact) **112 severe → 4 High SQLite only**. Verified nonroot FastAPI,
psycopg ABI, and PostgreSQL17/Alembic 100-table upgrade. The patched target
is `uat_patched` and **not selected** by the mandatory eight-image workflow.
Its built config ID `sha256:6bea47fdcc46321dc006f8a9a9aca94f452b818cf860579c5322dcd8c483ca21`
is a scan binding, **not final OCI registry manifest identity**.

### Two unbreakable boundaries

- **No verified SQLite patch yet:** no authentic Root.io signed APK/repo key,
  supplier patch/source and redistribution license, and no official Alpine 3.23
  fix confirmed. Four High remain in Alpine runtime/migration and patched UAT.
  Do not install unverified APKs or suppress the advisory.
- **No independent approvals yet:** actual 3 physical owner-authorized hosts and
  watched Patroni/etcd/fencing failures absent; 9/9 physical HA scenarios NOT
  EXECUTED; eight actual final-OCI Licence/NOTICE signoffs NOT RECEIVED;
  independent code reviewer not eligible for request until tech/legal gates pass.

**Security control:** the original eight-role
`UNMODIFIED_ZERO_SEVERE_AND_ACCOUNTABLE_LICENSE_REVIEW` policy, required
branch rules, native Collector migration boundary, pinned 0.123 release,
and no-merge/no-deployment restrictions remain intact. **RELEASE NO-GO.**
