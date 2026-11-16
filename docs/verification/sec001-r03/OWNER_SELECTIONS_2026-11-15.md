# SEC001-R03 — Owner-selected qualification scope (15 November 2026)

**Decision authority:** Product owner. **Effect:** approve **isolated engineering
evaluation and review preparation only**. This record is NOT a technical test
report, cryptographic attestation, legal opinion, reviewer signature,
vulnerability waiver, release approval, deployment, or authorization to merge.

| Decision | Authorized action | Boundary |
|---|---|---|
| Q1 SQLite | Conditionally **evaluate** Root.io signed Alpine 3.23 SQLite patches | No API-key enrollment, external provider data transfer, unverified vendor APK ingestion, dependency replacement or distribution without independent security/platform and license review |
| Q2 PostgreSQL | Full **isolated** Patroni+etcd certification plan: quorum, fencing, failover, acknowledged data durability, populated restore and exercises | No existing databases, customer data, production host/network/VM, infra power fencing or permanent infrastructure. Single-host Docker containers cannot prove loss of one physical host |
| Q3 Collector | Full **isolated** patched Collector certification: TLS, identity, file checkpoints, replay, interoperability, rollback | Active 0.123.0 pin/native Collector migration unchanged; test credentials and synthetic data only |
| Q4 Legal | Request independent third-party licence, attribution, NOTICE and source-offer review per **final immutable image identity** | No reviewer has yet signed; generated `licenses.json` stays `PENDING_ACCOUNTABLE_REVIEW`; do not mark `REVIEWED` |
| Q5 GitHub | Request independent write-access reviewer **after** technical and compliance gates pass | No owner self-approval, no branch-rule adjustment, no premature reviewer request or merge |

## Preconditions / evidence routing

- Current parent [PR #105](https://github.com/Parikshit-Sahrawat/OpsControl_Dashboard/pull/105), remediation [draft PR #108](https://github.com/Parikshit-Sahrawat/OpsControl_Dashboard/pull/108), tracking [#106](https://github.com/Parikshit-Sahrawat/OpsControl_Dashboard/issues/106), legal [#97](https://github.com/Parikshit-Sahrawat/OpsControl_Dashboard/issues/97).
- SQLite: four High matches on `sqlite-libs 3.53.4-r0`, third-party patch claim `3.53.4-r00073`; supplier signature, patch provenance, source licence, supported architecture and installed-image Syft/Grype qualification **not verified**.
- PostgreSQL: isolated PG17/gosu0-severe scan; tested disposable restart, logical dump/restore, `fsync`, `pgcrypto`; full Patroni/etcd 3-host HA and acknowledged-event failover **not certified**.
- Collector: 0.165.0 rebuilt/zero-severe isolated image; full mTLS, checkpoint/replay and native handoff **not yet certified**.
- Legal: reviewer appointment, final image source/manifests, licence expression resolution, obligations and independently signed verdicts **missing**.
- Required workflow: original eight-image severe and Licence/NOTICE Tier C remains **unchanged and mandatory** for release, and a final full rerun is required after all accepted replacements.

**NO-GO** for release and merge pending the above independently verified criteria.
