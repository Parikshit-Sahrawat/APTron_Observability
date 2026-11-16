# SEC001-R03A — SQLite CVEs: vendor-patch candidate and accountable decision

**State (2026-11-15): REVIEW REQUIRED — NOT INSTALLED, APPROVED, OR RELEASED.**
**Target:** only the two *isolated* Alpine 3.23 backend candidates on draft PR #108.
Do not alter the active Debian backend, existing eight-role image-security gate,
Grype results, or its legal status.

## Exact open findings

Both isolated Python 3.12.16 Alpine 3.23 backend candidate scans reported
**four High and zero Critical/Unknown** for `sqlite-libs 3.53.4-r0`:

| CVE | Component | Public upstream/supplier status |
|---|---|---|
| CVE-2026-119373 | FTS5 | Upstream fixed with SQLite 3.54.x; Root.io lists patched Alpine 3.23 `sqlite 3.53.4-r00072` |
| CVE-2026-119374 | FTS5 | Upstream fixed with SQLite 3.54.x; Root.io lists patched Alpine 3.23 `sqlite 3.53.4-r00072` |
| CVE-2026-119379 | session extension | Upstream fixed with SQLite 3.54.x; Root.io lists patched Alpine 3.23 `sqlite 3.53.4-r00073` |
| CVE-2026-119586 | sqlite3 command-line `.recover` output, not core engine | SQLite's upstream CVE page says this is not a core-library bug; Root.io claims a patched Alpine 3.23 `sqlite 3.53.4-r00073` |

**No official Alpine 3.23/3.24 package update has yet been verified that
resolves all four**. The upstream 3.54.1 source fixes three but does not
demonstrate closure of the `.recover` shell CVE; do not use unpatched
`3.54.1` as an assertion that all four are resolved.

Supplier disclosures:
- https://osv.dev/vulnerability/ROOT-OS-ALPINE-323-CVE-2026-119373
- https://osv.dev/vulnerability/ROOT-OS-ALPINE-323-CVE-2026-119374
- https://osv.dev/vulnerability/ROOT-OS-ALPINE-323-CVE-2026-119379
- https://osv.dev/vulnerability/ROOT-OS-ALPINE-323-CVE-2026-119586
- https://www.sqlite.org/cves.html
- https://github.com/rootio-avr/rootio_patcher

The supplier's patcher documentation requires a `ROOTIO_API_KEY` and publishes
APK packages through a **separate vendor repository**, currently AMD64-only.
These are vendor-specific patched versions, **not authoritative Alpine
security release versions**.

## Exact gated validation steps, if the owner approves this supplier

1. **Security + Platform approval BEFORE ingesting third-party APK bytes**:
   authenticate patch supplier and distribution entitlement, pin patcher
   release SHA-256 or independently verified source commit, verify repository
   key fingerprint and signed APK, capture source patches and provenance,
   approve linux/amd64-only limitation and any external API/credential exposure.
   Do not store API credentials in code, build logs, or image layers.
2. Build isolated **new**, independently named Dockerfile candidates from the
   same official digest, with only the supplier-verified `sqlite-libs` package
   replaced; bind exact APK filename, version `3.53.4-r00073`, SHA-256,
   signing key and Python `sqlite3.sqlite_version`/ABI check to the image
   evidence. A supplier claim alone does **not** establish the installed bytes.
3. Run Syft, CycloneDX, Grype and **SQLite binary-linked component verification**
   against the actual immutable candidate image. Reject unrelated transitive
   package changes, removal of the installed sqlite package to hide findings,
   unverified vendor SBOM labels or severity modification.
4. Exercise FTS5 and SQLite session-extension tests in the disposable candidate,
   verify Python's `sqlite3` C binding, backend SQLAlchemy imports, non-root
   runtime, owned PostgreSQL17 connection, complete Alembic fresh migration,
   tenant/RBAC negative paths, recovery, and original release UI/API tests.
5. Obtain **independent legal approval** for patched APK redistribution,
   modifications, attribution, source-offer and customer-self-hosted license
   duties, **bound to final SHA-256 image IDs**. Record named reviewer, dated
   signed verdict and exact scope; do not auto-create `REVIEWED`.
6. Only then nominate a final image candidate and rerun the original unchanged
   eight-role zero High/Critical/Unknown + licensing policy on the final head.

**Fail closed:** any missing patch, expired/revoked key, missing provenance,
remaining Grype severe match, incomplete compatibility suite, or missing
accountable review means **NOT ELIGIBLE**. Treat calls for risk-based treatment
as *separate*, explicit, audited decisions, never as a scanner suppression.

## Current decision

- **Installed patched Root.io APK:** NO
- **Current Alpine candidate scan:** 4 High per image
- **Original Debian backend:** UNCHANGED (severe findings remain)
- **Supplier security/platform approval:** NOT RECEIVED
- **Image-bound licence/NOTICE approval:** NOT RECEIVED
- **Customer deployment or final-image promotion:** NOT AUTHORIZED
- **Release decision:** NO-GO

## Authenticated offline APK signature intake (new engineering tooling)

The supplier-claim preflight `scripts/ci/r03_supplier_evidence.py` still
reports `BLOCKED_INDEPENDENT_REVIEW_REQUIRED`. A separate, read-only
`scripts/ci/r03_verify_vendor_apk_offline.py` can cryptographically verify a
**locally furnished** APK with `apk verify`, provided Security supplies the
out-of-band trusted key fingerprint and a separately verified signer/source
reference. This does **not** fetch any supplier package or authenticate a
supplier merely because the key arrived with the package.

Manual isolated Alpine workstation/lab command (replace placeholders with
real *independently authenticated* data; do not commit APKs or keys):

```sh
python scripts/ci/r03_verify_vendor_apk_offline.py \
  --offline-apk /secure-lab/approved/sqlite-libs-3.53.4-r00073.apk \
  --trusted-public-key /secure-lab/approved/rootio-signing.rsa.pub \
  --apk-sha256 '<independently_verified_apk_sha256>' \
  --trusted-key-sha256 '<out_of_band_verified_public_key_sha256>' \
  --independent-trust-reference '<security_review_ticket>' \
  --output /secure-lab/supplier-signature-report.json
```

The command requires Alpine's `apk-tools` installed **before** the offline
test. It invokes `apk --network=no --keys-dir <ephemeral-directory> verify`,
never `apk add`, `apk upgrade`, a package script or a supplier API. It
confirms matching bytes and the cryptographic signature against the
out-of-band supplied key, not actual legal redistribution permission.

Only after a successful `apk verify`, independent Security/Platform review
of **who controls the signing key**, permitted entitlement and source-diff
review may the owner separately authorize an isolated build with those APK
bytes. Actual final-image Syft/CycloneDX/Grype, ABI/security compatibility,
redistribution/NOTICE approval and eight-role Tier C are still mandatory.

**As of 16 Nov 2026:** no authenticated Root.io key, APK, independent
supplier entitlement or legal signature was supplied. No patched package was
installed or promoted. All four SQLite High findings remain open.
