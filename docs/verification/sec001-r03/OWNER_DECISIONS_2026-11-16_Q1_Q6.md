# Owner SEC001-R03 decision update — 16 November 2026

This update follows the previous [Q1–Q5 selections](OWNER_SELECTIONS_2026-11-15.md).
**This record is engineering authorization, NOT Security/DBA/Legal certification,
release permission, waiver, merge permission or vendor credential approval.**

| Question | Latest controlling owner selection | Authorized code scope / explicit boundaries |
|---|---|---|
| Q1 SQLite | **A** conditional Root.io supplier evaluation | Offline source/supplier trust, signed APK provenance and license preflight. **No** Root.io API key, package ingest, vendor purchase or patched APK installation before independently authenticated, explicitly approved trust and redistribution rights |
| Q2 Vulnerable images | **A** hardened UAT/backend replacement candidates | Build **isolated** Alpine runtime, migration and UAT targets; include exact Syft/CycloneDX/Grype evidence; do not replace any of eight existing production scan roles or suppress findings |
| Q3 Legal | **C** prepare legal evidence only, reviewer later | Eight-role final image manifest/SBOM, NOTICE/source-offer review packet and unsigned template. No designated legal reviewer, automatic APPROVED status, or representation of completed licensing review |
| Q4 GitHub | **A** independent existing write-access reviewer after gates | No PR reviewer request until verified technical, security and legal acceptance; independent human approval required; no merge automatically |
| Q5 HA | **A** prepare full 3-host lab using separately owner-authorized existing hosts | Read-only host authorization plan and complete runbook; no external SSH, host contact, VM provisioning, power/fencing/partition injection, or production data. Require 3 physical failure domains and separate fault approval |
| Q6 Collector | **A** patched 0.165 side by side with pinned 0.123, rollback before any switch | Ephemeral two-version local checkpoint/identity tests, mTLS and log delivery; no active pinned Collector update, runtime promotion or native Collector migration |

**Retained mandatory gate:** original `OC Dev - Tier C - Image SBOM Vulnerabilities and Licenses` for **all eight** roles; zero unreviewed High/Critical/Unknown matches, independent license/NOTICE signoff tied to the *actual final image*, and GitHub writer approval. Security policy is not a workaround for incomplete vendor or deployment qualification.

**Current result:** engineering preparation only, PR #108 DRAFT; parent #105 OPEN;
all independent acceptance signatures PENDING; RELEASE NO-GO.
