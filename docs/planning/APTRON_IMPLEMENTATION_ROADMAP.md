# APTron Observability — implementation journey

Architecture alignment: 23 November 2026; historical implementation evidence below remains dated to its original source.

Owner direction of 18 November supersedes the mandatory three-host initial production topology: default is one customer Linux host, Docker Compose and three steady-state central containers. Multi-host HA is optional and customer-managed. [SH-01 candidate and acceptance boundaries](../../deploy/single-host/README.md) implements packaging only on a separate branch; no runtime, backup, receipt or release certification is implied. Existing CI/security policies are unchanged.

Historical reconciliation: 16 November 2026. Customer self-hosted, fully open-source product.
This register replaces the old OpsControl implementation roadmap for current product planning. Historical source, tests, approvals and protected customer records remain evidence, not automatic APTron acceptance.

## Authority and verified baseline

- Owner instruction: clean the PR/branch queue, continue bounded implementation, show the roadmap.
- Owner staging-first policy: isolated staging may proceed under documented, unexpired exceptions; production certification remains mandatory before promotion.
- [ENG-001 proposed workstreams](https://drive.google.com/file/d/1WM6-SHDHAinjOotD83Db_qytz8VgnUlp/view): read-only audit of main `2e4fe5d8cb0f39170b0d789fdd7e07be4ac0219a`. Its PR-00–PR-13 labels identify workstreams, not GitHub PR numbers or blanket implementation approval.
- Main remains `2e4fe5d8cb0f39170b0d789fdd7e07be4ac0219a`. Active draft [PR #110](https://github.com/Parikshit-Sahrawat/APTron_Observability/pull/110) now targets main directly. Nothing has been merged by this cleanup.
- Disposable staging passed at code head `8ca9a7753c0c5f16574629873d2a57a86d518185`, tested merge `766bddb54d8e6668bc45587359b0abf9788d0da3`, tree `279e5b185a2b67ae505819de11b535fc95959b79`: [run 43806123729](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43806123729). New commits require their own evidence.
- All eight production images were scanned at the same head: [run 43806123753](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43806123753). Production remains blocked. Staging exceptions expire 30 November 2026 at 23:59:59 IST.

## Ordered milestones and exit evidence

| Milestone | Current state | Next implementation and acceptance | Dependencies |
|---|---|---|---|
| M0 — Queue and baseline truth (PR-00) | One active candidate; historical heads archived | Close superseded PRs, remove only unchanged archived refs, retain restoration ledger and exact-SHA evidence | Owner cleanup authorization |
| M1 — Product foundation (PR-02 and part of PR-03) | Implemented in draft #110; staging sign-in/title/reload verified | APTron brand, guarded Compute Instances / Data Pipelines / APIs navigation, excluded dedicated Incidents UI, self-hosted Documentation / Learning / Training. Independent owner visual acceptance remains open | M0; current tenant/API contracts preserved |
| M2 — Operator staging journeys (part of PR-03) | Current bounded implementation | Reuse the real PostgreSQL browser oracle in disposable staging: three inventory routes + reload, retired incident bookmark, local Help links, light/dark at 1366/768/390, keyboard focus and actual viewer permissions. Capture screenshots and exact-head CI results | M1; real synthetic auth fixture; no mocked authorization |
| M3 — Resource lifecycle and identity (PR-03 / PR-04) | Legacy partial; selective reconciliation needed | Reconcile archived onboarding/resource changes by file and acceptance requirement. Prove draft→activate, edit/reload, tenant rejection, data preservation, operator settings/profile. Specify MSP/customer/environment/resource and privileged settings contracts before expanding identity | M2; no wholesale merge of #89; no generic settings editor |
| M4 — Native Collector and reliable receipts (PR-05 / PR-07 / PR-08) | Approved architecture; runtime not certified | Independently authored Linux/Windows Collector and installers; CL-1 SQLite WAL FULL spool, CL-2 PostgreSQL HOST_PROTECTED copy, CL-3 signed CENTRAL_DURABLE ledger/receipts. Crash/replay, unknown commit, key lifecycle, dedup and no false acknowledgments | M3 identity + approved security/wire contracts; production HSM/KMS work separately authorized |
| M5 — Compute and log monitoring (PR-06) | Legacy partial | Real Windows/Linux metrics, selected process/service identity, restart/gap markers, native log checkpoints/rotation/redaction, synchronized historical range/frequency views | M4 Collector; M3 resource lifecycle; real OS evidence |
| M6 — Job Monitoring (PR-09) | SOS 1.x / JS7 runtime acceptance pending | Read-only version-aware capabilities; pipelines/jobs/jobchains/orders/executions, immutable attempts/retries/recovery, scheduler authority and independent provenance. Real scheduler version matrix | M3 identity; M4 event durability; approved adapter contracts |
| M7 — API / Synthetic / RUM (PR-10 / PR-11) | API legacy partial; Synthetic/RUM first-class acceptance pending | Endpoint latency/status/errors/TLS and gRPC; private scheduled browser/API nodes and Chromium/Firefox/WebKit evidence; consent/masking/sampling RUM SDK and tenant isolation. Correlated Alerts investigation and audited ITSM delivery | M3; M4/M5 common collection; privacy/egress/credential contracts |
| M8 — Deployment / recovery; optional customer-managed HA (PR-12) | SH-01 single-host packaging candidate; runtime/recovery acceptance pending | Default: one Linux host / three central containers, qualified persistent storage, off-host encrypted backup and tested restore with explicit RPO/RTO. Optional customer-managed multi-host HA requires separate fencing/failover acceptance and documented guarantees | M4 durability boundaries; representative capacity/recovery evidence; explicit lab/infrastructure authority |
| M9 — Production release (PR-01 / PR-13) | BLOCKED | Final-image security remediation/rescans, compatibility/upgrade/rollback, eight digest-bound accountable License/NOTICE approvals, legal OSS license decision, recovery evidence for the selected topology (physical HA/fencing only when HA is offered), privacy/brand gates and owner acceptance | M3–M8 evidence for shipped scope; no promotion on staging success |

M4–M7 can progress in separately bounded slices once their contracts and prerequisites are concrete. Milestones do not imply invented dates, completed percentages or authorization for infrastructure changes.

## Active release hardening lane

| Work | Preserved status | Exit condition |
|---|---|---|
| Hardened Alpine backend SQLite | Four High matches in backend-runtime; also four in backend-migration | Remediate actual linked SQLite/runtime, rebuild both final images and independently rescan; verify application/migration compatibility |
| Older embedded Collector | UAT 112 severe matches; pinned OTel image 108, image-scoped at the recorded head | Qualify replacement version against supervision, configuration, restart/durability and full-image compatibility. Candidate zero-severe scans alone do not establish adoption |
| PostgreSQL / rebuilt Collector candidates | Qualification evidence exists; full production adoption remains open | Security + compatibility + representative HA/durability certification on final candidates |
| License / NOTICE | Independent approvals pending for all eight final images | Named accountable independent reviewers, approval decisions bound to final immutable image digests, SBOMs, NOTICE/license/source obligations |
| Physical HA for optional multi-host topology | Historical DEFERRED_NOT_PASSED evidence retained; not the default single-host guarantee | Separate authorized failure/fencing/recovery evidence before offering multi-host HA. Single-host release instead needs qualified backup/restore and explicit loss/recovery limits. Existing automated policies remain unchanged pending separate reconciliation |

The 228 image-scoped severe matches above are 4 + 4 + 112 + 108; the four other image roles had zero severe matches at the recorded scan. They are not 228 distinct vulnerabilities. Evidence, secret detection, build/functionality and isolation remain mandatory. Every temporary exception retains scope, owner, risk, expiry and exit criteria in `.ci/staging-exceptions.json`.

## Product boundaries

Linux customer deployment defaults to single-host Docker Compose with gateway/frontend, supervised API/monitoring engine and PostgreSQL. Multi-host HA is optional and customer-managed. Container restart is not host-failure protection; positive HOST_PROTECTED/CENTRAL_DURABLE receipts stay deferred until their separate guarantees are demonstrated. Windows/Linux monitored resources remain core. Native independently authored collection replaces upstream Collector only after parity and durability acceptance; current upstream 0.123.0 remains a quarantined compatibility boundary.

Job Monitoring targets SOS JobScheduler 1.x and JS7, plus log-file monitoring. Historical Pentaho/ETL providers and records are migration evidence, not the current product target. Kubernetes/OpenShift inventory/deployment and a standalone Incidents UI remain excluded. Preserve protected data and Alerts investigation/audit functionality. API Monitoring, Synthetic Monitoring and RUM remain first-class core domains. No proprietary product tiers or hosted product SaaS are introduced.

## Recovery and unresolved historical work

[Archive restoration ledger](https://github.com/Parikshit-Sahrawat/APTron_Observability/tree/archive/pre-cleanup-20261116/docs/verification/queue-cleanup/2026-11-16) preserves all 61 original branch tips and original open PR descriptions. Archive anchor `774854a210866573b0ad6fcdcfd8bd2b3e022b60` connects independent histories without merging their product trees. The archive also retains the exact one-time cleanup implementation and its expiry.

Closed PRs #80/#82/#84/#89 and assessment PRs #101/#102 still contain unreconciled historical requirements. PR closure means queue retirement, not delivery or certification. PR #104 Help was adapted; #105 foundation was incorporated except its obsolete UAT base-image pin; #108/#109 are ancestors of #110. Restore and selectively port proven relevant changes only after exact-file reconciliation.

## M3-A increment — 16 November 2026

Organizations lifecycle visibility is implemented on `feat/aptron-organization-lifecycle-20261116`, a separate draft stacked on #110. It adds active/inactive filtering, saved-ID page selection after create/edit, valid pagination and pending/error form handling. Four mandatory unit regressions and a real disposable PostgreSQL/browser regression cover the increment. [Manifest and evidence boundary](../verification/aptron-m3a-organizations/IMPLEMENTATION.md).

Local verification is reported in the draft PR; new live CI and independent Organizations UAT remain pending. No original UAT finding is closed. Compute identity/draft/collector reconciliation follows Organizations in the approved sequence. The remaining M3 identity/settings contracts, M4–M9 and production gates retain their prior states.

## SH-01 increment — 23 November 2026

Separate packaging slice on PR #116 head `4b9c346f53e16217e2a93e855c7d89507f11be1d`: three-service candidate manifest, supervised existing API/worker, worker-heartbeat health, exact gateway proxy trust, persistent PostgreSQL bind mount and same-origin TLS/CSP template. No ingestion activation, receipt issuance, reconciliation, automatic migration or production deployment. No wholesale historical branch merge. Native Collector direction and all security/license gates remain. Source tests are separate from pending Docker/container/backup/restore acceptance. Historical three-host design and exception records remain evidence; this roadmap update does not edit or waive existing release gate policies.
