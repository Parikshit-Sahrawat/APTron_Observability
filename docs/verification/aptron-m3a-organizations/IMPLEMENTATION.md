# M3-A — Organizations lifecycle visibility

Owner authorized the next implementation phase on 16 November 2026. This is the Organizations increment of M3, preceding Compute Instances in the cumulative UAT sequence. It is implemented on a separate branch from reviewed staging head `bf0f77ee505fca2eda4b1656382038ac398445d2`, stacked on draft #110. It now includes the separate base CI transport correction `ff26451423d9cd3369aba66548d8e8c927c403f1`. Main remains `2e4fe5d8cb0f39170b0d789fdd7e07be4ac0219a`.

## Confirmed execution rules

The recovered instructions require bounded changes, preserved tenant/RBAC/data/Collector boundaries, essential local checks, exact evidence, draft PR review and owner-controlled merge. The owner's existing workflow preference is implement → local checks → push/draft PR → trigger CI → exit, without waiting/polling. These confirmed instructions are recorded in root `AGENTS.md`. Retrieval did not expose a complete, independently identifiable rule set for the named “PR Acceptance Actions” chat; no additional unseen rule or approval is invented.

The approved staging-first policy remains current: security evidence and documented exceptions stay explicit; legal/physical HA deferrals are not passes. Mandatory image coverage, release guards, secret detection, functionality and isolation remain enforced.

## Concrete defects and resulting behavior

The current Organizations editor previously reloaded the list after saving but retained its old query and page. A newly created or renamed organization could be persisted in PostgreSQL and still be invisible behind the old filter or on another page. The UI also lacked active/inactive selection and allowed another form submission or dismissal while a save was pending.

- Save now resets the conflicting search/status and selects the page containing the exact returned organization ID. An absent saved ID produces an actionable inventory/access message.
- Organizations has All statuses / Active / Inactive filtering combined with name/code/ID search. Derived pagination clamps to an existing page after filtering or inventory changes.
- Organization saves retain form values on server errors, reject whitespace-only required identity, apply existing API field lengths, expose an accessible error and prevent repeated submission/dismissal until the save completes.
- Organization ID, creation timestamp, customer authority and inactive records stay server-owned. No schema/API or backend authorization change.

## Exact-file reconciliation and boundary

Reviewed `frontend/src/pages/ResourceManagementV2.jsx` and `UnifiedResourceManagement.jsx` at current staging head against archived #89 head `ecfdff2cf3f9d1a7b7b284e79a7f708d1baea8ce`. Their existing deltas contain selective Resource Management/foundation reconciliation. This increment builds on the current files; it does not merge or cherry-pick historical branch contents.

| Changed path | Purpose |
|---|---|
| `AGENTS.md` | Confirmed owner execution and acceptance rules |
| `frontend/src/organizationInventory.js` | Pure presentation filter/paging and saved-ID page selection |
| `frontend/src/pages/ResourceManagementV2.jsx` | Organization status, post-save visibility and pending/error form behavior |
| `frontend/scripts/organization_inventory.test.mjs` | Four focused state/identity regressions |
| `frontend/package.json` | Run the four tests in the mandatory frontend suite |
| `.ci/scope-manifest.json` | Add four mandatory identities; retain all 726 original tests and all required checks |
| `frontend/scripts/organization_lifecycle_acceptance.mjs` | Real API/PostgreSQL browser regression, synthetic fixtures only |
| `scripts/staging/browser.mjs` | Invoke Organizations checks in an independent browser context before existing domain/foundation checks |
| This report, roadmap, cumulative UAT register | Audited phase/acceptance status and remaining scope |

## Validation and pending evidence

Local commands: `npm ci --prefix frontend --no-audit --no-fund`; `npm test --prefix frontend`; `npm run lint --prefix frontend`; `npm run build --prefix frontend`; `python scripts/ci/policy.py`; `python -m unittest discover -s tests -v`; Node syntax and `git diff --check`.

The first policy run correctly rejected the four unregistered new test identities. They were added with RUN disposition; no original identity, classification, protected assertion or required context was removed. The final test results and exact remote commit are recorded in the draft PR.

The new browser regression is wired into the existing disposable staging workflow. It creates 26 real synthetic organizations to exercise both pages/statuses, delays an unchanged real POST response to test pending-form reentrancy, proves create/rename/deactivation ID preservation and reload, checks real duplicate-code rejection, checks light/dark edit form at 1366/768/390, and probes a real viewer's list/read/write denial. It uses actual authenticated API and PostgreSQL state, not fabricated responses. Its independent browser context preserves the existing foundation fixture session. Only synthetic CI data is changed; no HAR or bearer/enrollment material is emitted. Screenshots and `organization-lifecycle.json` go to the existing staging evidence artifact.

Live browser/DB results are **PENDING CI**, not local passes. No new CI run is polled or rerun by the agent after triggering; the owner monitors and reports failures. Backend code is unchanged; all existing backend/tenant security suites remain enabled in CI. Independent owner UAT stays OPEN. Build's existing large-chunk warning is retained, with no threshold changes.

## Retained baseline failures and remaining scope

Baseline #110 at `bf0f77e`: 17 of 19 workflows succeeded. The production eight-image security/license gate remains blocked; candidate qualification failed in job `133114675473` at “Build patched UAT candidate using only verified named binary context” ([run 43809469010](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43809469010)). The producer artifact omitted seven checksummed files in hidden `.github` directories. Base correction `ff26451423d9cd3369aba66548d8e8c927c403f1` preserves those files and rechecks the complete legal manifest immediately after download; new CI is pending. This Organizations increment does not claim candidate adoption or clearance of its findings.

The four backend SQLite High matches (also four migration matches), UAT/pinned Collector findings, eight digest-bound independent legal approvals and physical HA/fencing certification remain open production requirements. Exceptions retain their 30 November 2026 23:59:59 IST expiry. No merge, production deployment, image publication, branch-protection change or certification claim.

Next bounded work: owner Organizations UAT, then Compute identity/draft/edit/reload and collector association reconciliation. Full eight-step native onboarding, installers, enrollment, activation, telemetry health, performance under ingestion and broader identity/settings contracts are not completed by this increment.

## PR #111 stabilization

At head `f2428bd1d939deefc9796a8dcf56bc22472e9c82`, run `43830509609` / job `133174443869` failed before completing `combined-status-search-pagination`. The captured browser showed an empty global customer scope and no organization rows. The fixture now verifies the real platform administrator's ALL capability and explicitly selects it through the existing customer selector before creating synthetic rows. Viewer checks retain their separate, restricted session and direct read/write denials. Search/status controls now have explicit accessible labels; substep failure diagnostics identify search versus status. Counts, real PostgreSQL requests, duplicate-save and tenant assertions are retained. New exact-stack CI is pending; no accepted-runtime claim from local checks.

PR #110 content was statically reviewed at its recorded baseline and its harness correction is documented in `FOUNDATION_REVIEW.md`. The stack is updated by adding its exact reviewed base as a parent, preserving all published #111 commits. Neither PR is merged or retargeted. Production image/licensing enforcement remains unchanged.

## 17 November — actual failed browser evidence and scoped expectation

Run 43838968390 (head 791b5840) failed with the screenshot showing **Inactive**, the lifecycle seed search and zero loaded records. The old phase spanned both active and inactive assertions; its `organization-status-active` label did not identify the failing assertion. The actual resource client already uses the paginated `/api/v1/organizations` endpoint. `boundaries.choose(ALL)` intersects the current active customer directory; neither inactive fixtures nor a deactivated customer belong to that selection. No endpoint, selector authority or tenant predicate is changed.

The corrected real-browser scenario seeds 26 active and 13 inactive customers. It expects 25 active rows on page one and one on page two, exact seed codes, and no inactive rows under ALL. Rename/reload, duplicate rejection and responsive keyboard checks run while the customer is authorized. Deactivation checks the real successful PATCH response for retained ID/code/creation time, then requires exclusion from inventory and a 404 scoped read. The existing viewer read/write/create negatives remain. Direct fixture reads now explicitly use the same ALL header as the browser, rather than accidentally testing an empty selection.

Local: 43 frontend tests pass; lint, build and browser-script syntax pass. Disposable browser/PG execution must be established by new exact-head CI. Build emits its existing large-chunk advisory. No production, legal, physical HA or independent owner-UAT result is asserted.

Run 44043988705 at 331c5b42 passed the corrected status/search/pagination checks, then timed out waiting for the newly created target. Its screenshot shows the saved record count increased to 29 but the view reset to page one. `onCustomerCreated` refreshes the directory and changes the global scope key even though the explicit ALL filter has not changed. Organizations now keeps its instance for this ALL-directory refresh, preserving the saved-ID page; authorization revision, mode, environment and explicit-selection changes still reset it. The browser assertion is retained.
