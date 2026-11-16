# Recoverable branch snapshot — 16 November 2026

This branch preserves every pre-cleanup branch tip through its commit ancestry. Its tree uses the validated APTron staging source; it does not merge historical feature contents into product code. BRANCH_SNAPSHOT.json records all original branch names, exact SHA values and open PR snapshots.

To restore an original branch using the recorded SHA:

```sh
git fetch origin archive/pre-cleanup-20261116
git branch ORIGINAL_BRANCH RECORDED_SHA
git push origin ORIGINAL_BRANCH
```

GitHub can also create a branch from the recorded commit. Historical PR conversations and CI artifacts remain available after closure. Archived source, design decisions and unresolved requirements remain references for selective reconciliation; no production or acceptance status is upgraded by this archive.
