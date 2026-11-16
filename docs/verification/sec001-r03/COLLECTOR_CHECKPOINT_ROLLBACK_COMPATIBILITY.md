# SEC001-R03 — Collector checkpoint rollback qualification (v0.165 → v0.123)

**Owner scope:** isolated side-by-side upgrade/rollback tests only, NO Collector pin
change, deployment, integration merge, security/legal approval, or final release.
**Current direct-rollback verdict:** **INCOMPATIBLE / BLOCKED**, based on
[CI run 43762882492, job 132961394195](https://github.com/Parikshit-Sahrawat/APTron_Observability/actions/runs/43762882492/job/132961394195).

## Reproduced failure

The exact legacy v0.123.0 Collector successfully exported its initial log marker
using the local filelog receiver's file_storage checkpoint.
The isolated, patched v0.165.0 binary read that earlier checkpoint and exported
the newly appended marker (without reported duplicate).
But after a clean v0.165.0 stop, restarting v0.123.0 against that same
checkpoint failed before starting its pipeline:

```
start stanza: read known files from database:
decoding file count: invalid character 'c' looking for beginning of value
```

This is **a genuine backward checkpoint format incompatibility**, not merely a
test timing/flaky Docker problem or an acceptable downgrade. **NEVER** delete the
checkpoint, hide/relabel the error, or claim zero loss/duplicates by starting
with fresh state.

OpenTelemetry documents the switch: v0.164.0 and newer always write filelog
checkpoints as Protocol Buffers (older versions wrote JSON), while newer
readers accept both. See
https://opentelemetry.io/blog/2026/filelog-protobuf-checkpoints/ .
Documentation for v0.163.2's
`filelog.protobufCheckpointEncoding` feature gate states that v0.163.2 can
**read both** checkpoint formats and write JSON with its gate disabled:
https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.163.2/receiver/filelogreceiver/README.md .

## Explicit intermediate JSON-bridge experiment — NOT certification

The updated [isolated script](../../../../scripts/ci/r03_collector_side_by_side_rollback.sh)
performs a four-stage test using exact pinned OCI image identities:

1. **v0.123.0**: process synthetic filelog event, persist JSON checkpoint.
2. **patched v0.165.0**: accept legacy JSON, process next synthetic event,
   persist protobuf checkpoint, and verify no prior marker replay.
3. **v0.163.2, EVALUATION ONLY**: read protobuf checkpoint and write back JSON
   after processing a new event, with default-disabled protobuf encoding.
   Verify no replay, no checkpoint deletion, and identity continuity.
4. **v0.123.0**: read converted JSON, process next marker, reject duplicate
   delivery of all prior markers; allow clean shutdown.

The bridge image is pinned to
`otel/opentelemetry-collector-contrib:0.163.2@sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849`
from the repository's prior **evaluation-only** image identity ledger.
It is **not** a final-image candidate and has not been approved by Security,
Architecture, Legal, or Collector owner for a customer deployment.

If v0.163.2 cannot read, rewrite, or preserve offset continuity, the
experiment fails and the safe rollback path remains **BLOCKED**. A positive
single-file local result does not certify distributed durable receipts,
multi-file rotation, truncation, filesystem faults, customer tenant/source
identity, transport identity, TLS rotation, reprocessing, central staging or
native Collector migration.

## Mandatory production acceptance still missing

- Security-scan and legal/NOTICE review the **bridge** if it is proposed for
  any *real* rollout or rollback role. An intentionally vulnerable intermediate
  image must never be silently promoted.
- Validate real-world SOS JobScheduler 1.x / JS7 job monitoring and log-file
  examples, on Linux and Windows where relevant, with explicit existing
  operator approval and synthetic data.
- Bounded synthetic multi-file checkpoint/rotation/truncation, 0.123→0.165→
  bridge→0.123 under failure injection, network drops, retries and gaps.
- Prove end-to-end immutable natural event IDs, duplicate reconciliation and
  CL-2 HOST_PROTECTED / CL-3 CENTRAL_DURABLE receipt contract under
  host/Collector restarts and PostgreSQL promotion.
- Independent Collector Architecture and Security review, plus actual
  image-bound legal approval and the unchanged mandatory Tier C security gate.

**Decision until independently accepted:** active v0.123.0 pin unchanged,
native migration boundary unchanged, rollback **NOT CERTIFIED**, release NO-GO.
