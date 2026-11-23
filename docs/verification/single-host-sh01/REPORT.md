# SH-01 — single-host three-container packaging candidate

## Scope and ancestry

Owner authorized the next bounded implementation step on 23 November 2026 after confirming the revised single-host architecture. Branch `feat/aptron-single-host-compose-20261123` starts at PR #116 head `4b9c346f53e16217e2a93e855c7d89507f11be1d`. No other branch was merged, edited or retargeted. PR #116 remains unmerged; inherited code is not newly accepted by this work.

Three steady-state services: gateway/frontend, supervised existing API + monitoring worker, PostgreSQL 17. Manifest requires selected images and customer configuration; it is not a production installer. Added persistent bind mounts, internal DB network, exact gateway-IP proxy trust, read-only engine, heartbeat/API health and bounded child shutdown/reaping. Actual child failure/termination tests use disposable local subprocesses.

Explicit empty frontend API base now selects same-origin requests (`??` rather than `||`); an absent variable retains the existing development default. Optional nginx renderer template preserves existing callers, CSP hashes and default template. Added customer preparation/backup/restore guidance, and aligned the roadmap without editing gate code. No automatic database migration, native Collector adoption, critical-event listener, receipt signer, reconciliation activation, host provisioning or production deployment.

## Local validation

| Exact command / check | Observed result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 166 PASS, zero FAIL/SKIP; includes 8 new supervision/health/isolation/renderer tests. Raw final output: root-tests.log. |
| `python scripts/ci/policy.py` | PASS; 29 workflows, 760 inventoried identities, all 13 required contexts preserved. Every previous test classification retained. |
| `npm ci --prefix frontend --no-audit --no-fund --cache /workspace/scratch/74045a10eb8b/npm-cache` | PASS; lockfile unchanged. |
| `npm test --prefix frontend` | 43 PASS, zero FAIL/SKIP. |
| `npm run lint --prefix frontend` | PASS. |
| `VITE_API_BASE_URL='' npm run build --prefix frontend` | PASS on Vite 7.3.7; existing >500 kB chunk warning retained (575.10 kB main JS). Built JS inspected: no `http://localhost:8000` fallback. |
| `node frontend/scripts/render-production-nginx.mjs frontend/dist/index.html /workspace/scratch/74045a10eb8b/single-host-nginx.conf http://engine:8000 deploy/single-host/nginx.conf.template` | PASS; rendered exact local build; not nginx runtime validation. |
| Black 26.10.1 `--check` and Ruff 0.14.0 `check` on the five new Python modules/test file | PASS, using isolated tooling directory. |
| `python -m compileall -q backend/scripts/run_single_host.py backend/scripts/check_single_host.py scripts/validate_single_host.py scripts/ci/check_single_host_compose.py` | PASS. |
| PyYAML parse and `git diff --check` | PASS. |
| `npm audit --prefix frontend --omit=dev --json`; `npm audit --prefix frontend --json` | Both current configured-registry responses report zero findings (raw JSON retained). This differs from inherited historical Picomatch evidence. No dependency/lockfile change or upstream advisory investigation was performed, so this is not a security-blocker closure or release approval. |

## Limits / pending acceptance

`docker compose version` failed because Docker is unavailable in this execution environment. Actual Compose rendering, image build/startup, nginx TLS, browser-on-containers, persistent restart, host reboot, backup/restore, backend PostgreSQL/mTLS runtime suites and final image rescans were not run locally. The existing disposable-staging workflow now includes `python scripts/ci/check_single_host_compose.py` to render the actual candidate without pulling images or deploying. Its result is pending, not inferred from local structural fixture tests. Existing staging deployment tests remain the historical staging topology, not three-container runtime acceptance.

No new image role or scan exemption; all eight security/SBOM/licensing roles remain. No exception extension or expiry change. Positive HOST_PROTECTED/CENTRAL_DURABLE receipts remain deferred. A live but stalled worker marks the engine unhealthy; Docker restart policy alone will not restart an unhealthy running process. This needs operations response and real-image acceptance. Single-host packaging makes no host-loss or HA guarantee; off-host backup/WAL tooling and measured RPO/RTO remain separate work.

Current roadmap changes supersede mandatory three-host initial deployment in product planning only. Existing automated production policies and historical failed/deferred evidence remain unchanged; any gate-policy reconciliation is a separately reviewed decision. No production gate is passed by this candidate.

## Review handoff

Intended draft PR base is #116. Remote publication is not completed: automatic approval review rejected the branch push because explicit owner authorization to publish a new GitHub branch is required. No workaround was attempted, no PR was opened and no new hosted CI was triggered. Source implementation commit is `a0f6e87968517258df14fa90f1d81e66d5c4aad8`. A read-only remote-head check returned no matching branch. After explicit publication authorization, trigger existing CI once, record the final remote head, then exit per AGENTS.md; owner monitors results and explicitly decides merges. Owner should review supervisor semantics, gateway trust/networking, exact same-origin frontend artifact/CSP coupling, restricted database preparation and backup/recovery limits. No automatic merge, deploy or production action.
