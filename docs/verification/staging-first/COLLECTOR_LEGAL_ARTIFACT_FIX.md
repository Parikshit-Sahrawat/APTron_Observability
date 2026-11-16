# Patched UAT legal artifact transport correction — 16 November 2026

Failure: [run 43809469010, job 133114675473](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43809469010/job/133114675473), code head `bf0f77ee505fca2eda4b1656382038ac398445d2`, tested merge `9b37fb42cdd76a1fb245447188b3fa998fe941c6`.

The patched UAT build failed in the legal checksum verification, before the binary version command. Seven checksummed paths below compiled module `.github` directories were absent after artifact transport: two `license-header.txt`, three `license.yml`, and two `license-check.yml` files. Its log reports `sha256sum: WARNING: 7 of 1876 computed checksums did NOT match`. The original rebuilt image's version check separately printed `otelcol-contrib version 0.165.0`; a version mismatch was not the cause of this build failure.

The producer verified the legal files before upload, but the pinned [upload-artifact action](https://github.com/actions/upload-artifact/blob/ea165f8d65b6e75b540449e92b4886f43607fa02/README.md#uploading-hidden-files) excludes hidden paths by default. Its single generated `sec001-r03-rebuilt-collector-binary-for-uat` artifact now opts into hidden files. The upload path remains only `$RUNNER_TEMP/r03-patched-collector/`, containing the rebuilt binary, build information, source binding and captured legal material; the checkout, credentials and runner environment are outside that path.

The consumer now runs `sha256sum -c SHA256SUMS` immediately after source/binary/manifest binding checks and before the expensive Docker build. The existing Dockerfile checksum validation also remains mandatory. No manifest entries are removed, hashes rewritten, failures suppressed, version guards relaxed, production pin changed or legal approvals inferred.

The compiled-legal-material regression now captures nested `.github` license files, rejects symlink material, verifies every collected hash and checks the exact scoped artifact transport contract. Focused tests, policy/workflow syntax and the existing root suite are run locally; a new exact-source CI build and scan remain pending. Docker is unavailable locally, so this report does not claim a locally rebuilt or rescanned UAT image.

`security-sbom` remains a separate, genuine production policy failure: four backend and four migration SQLite High matches, 112 UAT and 108 pinned Collector severe image-scoped matches, and pending independent License/NOTICE decisions for all eight roles at the recorded baseline. The staging inventory decision passed under the owner's bounded exceptions. Independent legal and physical HA checks remain DEFERRED_NOT_PASSED until production readiness. This transport fix neither clears those findings nor authorizes promotion.

Organizations lifecycle work continues in its own stacked draft. CI is triggered by the pushes/PR; the owner monitors new results and controls merging. No waiting/polling, automatic merge, production deployment or publication.

## Subsequent harness import-path correction

At exact head `ff26451423d9cd3369aba66548d8e8c927c403f1`, run `43830040527` completed the patched UAT build, migration and mTLS/checkpoint work, then failed in job `133182375738`: `ModuleNotFoundError: app.telemetry`. Invoking the mounted file as `/probe.py` made `/` the script import root instead of the image's `/app` package root. The workflow now mounts it as `/app/scripts/r03_uat_version_probe.py` and invokes `python -m scripts.r03_uat_version_probe` from the existing `/app` WORKDIR. No application import hack, pin relaxation or image/license gate change.
