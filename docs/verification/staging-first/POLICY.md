# APTron Observability — approved staging-first validation

Owner approval: 16 November 2026. The owner explicitly selected **Disposable CI staging** in this session. This supersedes earlier instructions that treated final independent License/NOTICE approval and formal physical HA certification as prerequisites for this isolated staging deployment. It does not approve production, publishing images, contacting existing machines, procuring infrastructure or automatically merging PRs.

## Approved policy

1. Defer independent License/NOTICE sign-off and formal physical HA certification until production readiness.
2. Continue vulnerability scanning, SBOM collection and license inventories. Approved, documented temporary exceptions do not block isolated staging.
3. Preserve all findings and evidence. Deferred checks are not passed or remediated.
4. Keep build, functional, secret-detection and deployment-isolation safeguards blocking.
5. Do not promote staging artifacts to production before security, licensing, compatibility and HA requirements are completed.
6. Every exception records scope, owner, risk, expiry and exit criteria.
7. Reassess deferred findings after staging validation and before production.

Exit condition: staging deployment and validation completed, followed by explicit reassessment and closure of production-release requirements. A successful disposable staging run satisfies the deployment/validation part only. It does not close the production reassessment.

## Implementation and temporary exceptions

`.ci/staging-exceptions.json` contains six accountable staging exception records: four exact per-role vulnerability sets (228 image-scoped severe matches in the current hardened eight-image inventory), one eight-role legal deferral and one physical HA deferral. Owner: Project Owner — Parikshit Sahrawat, from the explicit approval in this session. **Expiry: 30 November 2026, 23:59:59 IST**, selected as a bounded two-week staging window; no automatic renewal.

The vulnerability entries enumerate advisory, namespace, package, version, package type and severity from the verified current hardened-release scan artifacts in run `43803115925`. They are not blanket CVE exceptions: a new advisory, version or severity stops staging. Independent reviewer identities and signatures remain absent; owner staging approval is not misrepresented as legal approval.

`staging_image_gate.py` verifies scan freshness, file checksums, source SHA, Dockerfile inputs, image identity and complete role coverage before assessing staging exceptions. The existing `security-sbom`, `image_security_gate.py`, `security_manifest.py`, `release_authorization.py`, production publication workflows and required branch contexts retain their production behavior. A separate `staging-eligibility` job evaluates all eight collected images. Its status is **STAGING_ELIGIBLE_WITH_EXCEPTIONS**, never production policy PASS.

## Disposable deployment scope

The new `staging-first.yml` workflow runs on an isolated GitHub-hosted runner. It retains blocking gitleaks, source tests, lint and builds; builds and scans the actual compatible UAT backend, frontend and rebuilt PostgreSQL release Dockerfile; then deploys those exact local configuration image IDs. The UAT binary remains Collector 0.123.0 because the application currently rejects 0.165.0. The patched Collector remains a separate qualification candidate.

The stack contains one-shot migration, API, worker, PostgreSQL and frontend services. It uses synthetic test data and newly created project-local volumes, an internal Docker network, and loopback-only API/UI ports. It rejects external networks/volumes, host bind mounts, privileged execution, devices, remote Docker targets and mutable image tags. No host socket is mounted inside an application container; no image registry push or release-publication operation exists.

Validation runs real PostgreSQL migrations, API startup, authenticated tenant and nested authorization probes, browser login/branding/authenticated reload, actual Docker image/network inspection, and API/worker restart with retained database/authentication state. Only this UUID-named stack and its synthetic volumes are removed afterward. Raw scan artifacts and exception decisions remain available even when staging validation fails.

## Evidence and current limits

- Verified all ten downloaded artifact ZIP hashes for original eight-role run `43800966005`; verified all eight image evidence provenance checksums and SBOM/scan identities.
- Tested merge `0da78733ce8dae4177dd77b61dd1712e5aac796d` has the same tree `bc5eb42a9282ee6531dbae491c3be1e7284f5682` as PR #108 head `63cd004327bf22559320745c12bf030576a17aa6`.
- After reconciling concurrent release-source hardening through head `366cd9f`, verified all eight actual release artifacts from run `43803115925`, tested merge `e0c0a8d2cd31d6ad6a544a7f1e0de8e25fccb885`. Current severe counts: runtime 4, migration 4, UAT 112, pinned Collector 108; PostgreSQL/frontend/gateway/production frontend zero severe. Production legal decisions remain pending.
- Locally evaluated all eight current hardened image artifacts under the separate staging policy: **STAGING_ELIGIBLE_WITH_EXCEPTIONS**, retained in `VERIFIED_CURRENT_STAGING_DECISION.json`. The earlier 445-finding baseline decision is historical preparation, superseded by the current exception sets. Neither decision claims deployment completion.
- The current editing environment has no Docker executable or daemon. Actual container and browser staging evidence must come from the new hosted workflow; no local container deployment is claimed.

The earlier SQLite supplier intake, patched UAT Collector qualification, physical HA preparations and unsigned legal templates remain preserved for production readiness. Formal certification is deferred for staging, not fabricated or marked passed.
