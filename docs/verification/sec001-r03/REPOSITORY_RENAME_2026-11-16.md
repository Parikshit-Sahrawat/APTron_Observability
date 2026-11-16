# Repository canonical rename — APTron Observability (2026-11-16)

**Canonical repository:** https://github.com/Parikshit-Sahrawat/APTron_Observability
**Clone remote:** `https://github.com/Parikshit-Sahrawat/APTron_Observability.git`
**Prior repository:** `Parikshit-Sahrawat/OpsControl_Dashboard` (retained only as a historical name).

## Verified against GitHub's live repository object

- Both old and new repository lookup resolve to the **same immutable repository ID** `1409408069`.
- Default branch is `main`; existing Git history, repository metadata, PR numbers and issue history remain on the renamed repository.
- The existing unmerged APTron feature PR is [#105](https://github.com/Parikshit-Sahrawat/APTron_Observability/pull/105).
- The existing security/Collector/HA qualification draft PR is [#108](https://github.com/Parikshit-Sahrawat/APTron_Observability/pull/108); it remains stacked on PR #105's feature branch.
- The separate self-hosted documentation draft PR is [#104](https://github.com/Parikshit-Sahrawat/APTron_Observability/pull/104).
- The independent legal review docket is [issue #97](https://github.com/Parikshit-Sahrawat/APTron_Observability/issues/97).
- The image security/physical HA certification record is [issue #106](https://github.com/Parikshit-Sahrawat/APTron_Observability/issues/106).

## Operational migration notes — no automatic changes

Existing local clones can change their Git remote with:

```sh
git remote set-url origin https://github.com/Parikshit-Sahrawat/APTron_Observability.git
git remote -v
git fetch --prune origin
```

`git remote set-url` updates only the operator's **local Git configuration**. This review work did **not** change anyone's local clone. Owners of CI outside GitHub, webhooks, deployment manifests, documentation badges, external package publishing and OAuth app allowlists must independently check whether they used the old repository name. GitHub usually redirects old repository URLs, but an explicit new canonical URL is safer for new configuration.

**Do not** rewrite old evidence ZIP checksums, source commit SHAs, immutable Docker image IDs, package coordinates, or signed historical attestations merely because the repository display name changed. This commit changes only maintained Markdown navigation URLs, not provenance.

## Gate/status continuity

Rename does **NOT** certify Collector rollback, eliminate SQLite/container findings, establish real three-host independence, appoint a qualified Legal signer, or create an eligible independent PR approval. Original eight-image Tier C remains mandatory and unchanged, current signed license decisions pending, production deployment forbidden, and **release NO-GO**. No branch-protection modification, merge, infrastructure provisioning, purchase or destructive HA test was authorized by this migration note.
