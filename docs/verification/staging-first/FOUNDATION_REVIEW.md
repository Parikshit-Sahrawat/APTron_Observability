# PR #110 foundation review — 16 November 2026

Reviewed main `2e4fe5d8cb0f39170b0d789fdd7e07be4ac0219a` → candidate `ff26451423d9cd3369aba66548d8e8c927c403f1`, plus this bounded harness correction. The baseline diff spans 165 paths / 100 commits: 76 documentation paths, 15 frontend product paths, 21 browser/unit harness paths, 4 workflows, 3 staging scripts, image/build/scan tooling and associated contracts. This is a broad accumulated candidate, not a small patch.

**Merge decision: NOT GRANTED.** The owner retains merge authority. Required exact-head CI, independent owner visual/UAT review and production release requirements are distinct. Staging success does not clear the production gate.

- No `backend/app` or `backend/migrations` path differs in that foundation baseline. Existing backend authorization, tenant contracts, runtime history and database migration graph are retained.
- Dedicated frontend Incidents/IncidentView pages are removed; backend history/APIs remain. The new APTron navigation preserves guards and redirects retired bookmarks. Customer self-hosted Help ships locally. Broad UI and changed selector coverage still need owner review.
- Mandatory production zero-severe/accountable-license enforcement remains in `image_security_gate.py` / `security_manifest.py`; all eight roles are scanned. Explicit staging decisions have no production capability. No release authorization or branch protection is modified by this stabilization.
- Exact image IDs/source/build inputs bind the staging evidence. Exceptions remain scoped, expiring and DEFERRED_NOT_PASSED for independent legal/physical HA. Candidate Collector testing is not native Collector migration or release adoption.
- Source/image qualification tools and the image-selection changes require review alongside the frontend scope. Formal HA/fencing, upgrade/rollback, release images and all eight independent License/NOTICE decisions remain production blockers.

Latest concrete failure: run `43830040527`, job `133182375738` reached the application-negotiation probe and failed importing `app.telemetry` from `/probe.py`. The correction executes the mounted file as a module under `/app/scripts`; active Collector pin remains 0.123.0, and expected rejection of 0.165.0 must still produce BLOCKED_APPLICATION_VERSION_NEGOTIATION. The prior seven-hidden-legal-file artifact correction remains intact.

Thirteen required contexts are preserved by local policy: access-rbac, contracts, frontend-build, frontend-dependency-audit, image-validation, noc, pipeline-contracts, private-https, python-dependency-audit, restore-retention-tls, secret-history-scan, staging-smoke, verification. The live public GitHub `/rules/branches/main` endpoint confirms this exact set, strict_required_status_checks_policy=true, integration_id=15368 and repository ruleset 26082467. No protection change was made.

Local root tests and workflow lint are recorded in the PR. Newly triggered CI remains pending; no automatic polling, merge, retargeting, deployment or production-ready claim.
