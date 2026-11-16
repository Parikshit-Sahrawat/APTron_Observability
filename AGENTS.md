# APTron engineering execution rules

Confirmed owner instructions adopted on 16 November 2026. The current staging-first policy overrides older staging restrictions only within its documented scope.

- Implement one bounded, approved workstream per draft PR. Reconcile exact source/commit overlap; do not wholesale merge historical branches.
- Preserve server-side tenant isolation, RBAC, immutable evidence, existing API contracts, historical records and the native Collector migration boundary. Fail closed when identity or authority is missing.
- Run essential affected local tests, lint/build and available focused verification. Fix implementation defects without removing tests, lowering thresholds, suppressing failures or fabricating acceptance.
- Push the reviewed changes, open a draft PR, and trigger existing CI. Confirm the remote head and clean worktree, then exit. The owner monitors CI and manually merges. Do not wait for or poll new CI runs, or rerun passing workflows without a new reason.
- Never force-push, change branch protections, bypass required checks, auto-merge, fabricate independent approvals, or claim unverified runtime/certification results.
- Keep exact commits, commands, outcomes, limitations and evidence in the PR. Distinguish implementation, controlled verification, independent owner UAT and production certification.
- Preserve mandatory eight-image security/SBOM/license coverage and all existing findings. Approved, unexpired exceptions may permit isolated disposable staging; they never authorize production promotion.
- Every temporary exception needs scope, owner, risk, expiry and exit criteria. Deferred legal License/NOTICE and physical HA checks remain DEFERRED_NOT_PASSED until actually approved/certified.
- No production deployment, purchases/provisioning, destructive persistent-data tests, HSM/KMS operations, unverified supplier binary adoption or unrelated infrastructure changes under routine implementation authorization.
- The cumulative UAT register is `docs/uat/GLOBAL_UAT_REGISTER_2026-10-28.md`. Retain historical findings and append audited updates. No finding closes on merge alone. Organizations precedes Compute Instances in independent UAT.
- Current product roadmap: `docs/planning/APTRON_IMPLEMENTATION_ROADMAP.md`. APTron is customer self-hosted and fully open source; Scheduled Job Monitoring targets SOS JobScheduler 1.x / JS7. API, Synthetic and RUM are core domains. Kubernetes/OpenShift and a dedicated Incidents UI remain excluded. Preserve historical data during migration.
