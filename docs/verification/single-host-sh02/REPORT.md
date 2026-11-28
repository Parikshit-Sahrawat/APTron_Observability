# SH-02 — actual three-container runtime acceptance automation

## Authority and source boundary

Owner requested SH-02 on 23 November 2026: automate acceptance of the actual gateway/frontend, supervised API/monitoring engine and PostgreSQL topology before expanding monitoring features. Base is draft PR #117 at `3f37415f49f399c158b86f9ee526588cec61ed0e`. Separate branch `feat/aptron-sh02-runtime-acceptance-20261123`; no parent branch/PR edit, wholesale merge, production deployment or release decision.

**Implementation complete; hosted runtime result PENDING.** This environment has neither Docker CLI/daemon nor a GitHub-hosted runner identity. Local tests are not an executed Compose acceptance pass. Existing staging tests are retained; they do not substitute for this new job.

## Actual acceptance path

The new `single-host-acceptance` job in `.github/workflows/staging-first.yml` builds the existing backend-runtime, backend-migration, production-frontend and postgres roles from the clean current commit. Existing image binding, fresh scanner evidence and accountable staging-exception assessment are repeated before deployment. No image publication, new image role, changed finding fingerprint, extended exception or production gate bypass. All eight independent security roles and all 13 required contexts stay unchanged. The existing staging_roles selection is untouched; this explicitly authorized SH-02 job assesses the four already exception-covered roles individually with the same verification/assessment functions. Unknown/changed severe findings, checksum/source mismatch or expiry block deployment. Existing exceptions expire 30 November 2026, 23:59:59 IST.

The runner renders the actual `deploy/single-host/compose.yaml` and verifies the three scanned local Docker config IDs. It makes only two fixture isolation changes: remove gateway port publication and make ingress internal. These supplement the candidate's already internal DB network. Every bind mount/secret is under a fresh private directory; no existing customer project, disk or data is accepted. A runner-only localhost ephemeral-port HTTPS forwarder targets the live-inspected gateway IP on port 8443. Docker labels, image IDs, network ownership, addresses, nonroot engine identity and added capabilities are checked. Exactly three steady-state central containers are required; migration/seeding/inspection/cleanup helpers are temporary.

The migration image initializes the new synthetic database and a separate restricted runtime role. A production-mode owner-identity attempt is rejected by the actual supervisor entry point. The steady-state engine retains `ENVIRONMENT=production`, HTTPS enforcement, exact gateway-IP proxy trust and existing database-role restrictions. This is a fixture using production application controls, not production deployment authorization.

| Probe | Required evidence |
| --- | --- |
| TLS/CSP | Successful CA/hostname-verified gateway health; unknown CA and wrong hostname rejected; HSTS and exact-image SPA inline-script hashes |
| Browser | Real sign-in and reload, existing foundation/viewer/Help checks, responsive captures, no page errors or off-origin HTTP requests |
| Authorization | Anonymous 401, allowed source 200, foreign source 404 and viewer mutation 403 using real tokens/customer selection |
| API child SIGKILL | Whole engine exits/restarts, Docker restart count advances, health and persisted session recover |
| Worker child SIGKILL | Same bounded supervisor/restart proof |
| Worker SIGSTOP/SIGCONT | API remains reachable; worker heartbeat goes stale and engine becomes unhealthy without pretending Docker auto-restarts it; resume restores health |
| Persistence | Fixture identity/FK/user password-hash/job execution-history digests and PostgreSQL system identifier match before/after fault probes and complete container removal/recreation; persisted session remains valid |
| Cleanup | Exact-label temporary helpers and project containers/networks removed; only the freshly created synthetic PGDATA directory is erased, using the scanned PostgreSQL image; cleanup failure makes the entire result fail |

Python TLS verification is independent of browser rendering. Chromium accepts only the freshly generated fixture certificate's SPKI through a scoped browser flag; no global ignoreHTTPSErrors setting is used. Node's API requests trust the same fixture CA through subprocess-local NODE_EXTRA_CA_CERTS. No customer certificate/key or Collector PKI is used. Synthetic credentials and tokens are excluded/redacted from public evidence; only safe reports, image evidence, screenshots and sanitized service logs are uploaded as `aptron-sh02-runtime-evidence`.

## Candidate fixes discovered while preparing runtime acceptance

1. SH-01's plaintext `/health` check could never return HTTP 200 in production, because the API correctly requires HTTPS. Internal readiness now observes the exact production 403 HTTPS-required response plus the existing independent DB-checked worker heartbeat. It does not forge proxy headers or weaken TLS. The external acceptance path independently requires HTTP 200 over verified TLS. A real local HTTP-server regression rejects arbitrary denials, HTTP 500 and accidental production plaintext 200.
2. Production frontend Dockerfile now defaults to an empty same-origin API base rather than `https://api.example.invalid`, so its actual scanned default build is usable behind the candidate gateway. Explicit build overrides remain possible; dependency versions/lockfile are unchanged.
3. The deployment validator accepts local config IDs only with an explicit exact scanned-image map supplied by this runner. The normal CLI still requires OCI digest references. No tag-based deployment fallback is introduced.

## Local commands and outcomes

- `python -m unittest discover -s tests -v`: **170 PASS, zero FAIL/SKIP**, including four new SH-02 tests and eight retained SH-01 tests. Raw output: root-tests.log.
- `python scripts/ci/policy.py`: **PASS**, 29 workflows / 764 mandatory test identities / original 13 required contexts. Raw policy report retained.
- `npm ci --prefix frontend --offline --no-audit --no-fund --cache /workspace/scratch/74045a10eb8b/npm-cache`: PASS; no dependency/lockfile edit.
- `npm test --prefix frontend`: **43 PASS, zero FAIL/SKIP**. Raw output: frontend-tests.log.
- `npm run lint --prefix frontend`: PASS.
- `VITE_API_BASE_URL='' npm run build --prefix frontend`: PASS; existing >500 kB main chunk warning retained (575.10 kB JS).
- Black 26.10.1 and Ruff 0.14.0 on the changed/new Python modules: PASS after correcting an initial E402 import placement finding. No lint suppression added.
- `python -m compileall -q backend/scripts/check_single_host.py backend/scripts/single_host_fixture.py scripts/validate_single_host.py scripts/staging/single_host_acceptance.py`, `node --check scripts/staging/sh02_browser.mjs`, YAML policy parsing and `git diff --check`: PASS.

Docker build/startup, live container TLS/browser, PostgreSQL migration/role fixture, process fault injection, container recreation and cleanup in the new job are **NOT RUN locally**. New CI is triggered once after draft PR creation; owner monitors its result. Do not relabel this candidate runtime-tested until the new job and its complete cleanup report pass on the recorded source/image identities. Do not infer unrelated required checks or the eight-image security/license gate passed.

## Preserved limits

Receipt signing, positive LOCAL/HOST_PROTECTED/CENTRAL_DURABLE acknowledgments, receipt issuance/reconciliation workers and production PKI stay separate. No public S03 critical-event listener is introduced. Existing token-based API paths are not converted to mTLS by this harness. Container recreation is not power-loss, host-loss or multi-host HA certification. Backups, restore/RPO/RTO acceptance and native Collector/runtime provider qualification remain separate. No destructive test targets existing persistent data. Production remains subject to existing security/licensing and owner acceptance.
