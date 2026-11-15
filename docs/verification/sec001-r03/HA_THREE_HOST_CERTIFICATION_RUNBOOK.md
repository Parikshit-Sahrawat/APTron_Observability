# SEC001-R03 — Three-host Patroni / etcd isolated certification runbook

**Scope:** Authorized engineering test design only. **Execution:** NOT STARTED.
**Owner selection Q5:** Existing, independently approved three physical test hosts only.
**Reference architecture:** three hosts with PostgreSQL 17, Patroni and etcd co-located; quorum and correct fencing; Linux and Docker Compose + external HA.
**Forbidden:** production hosts or data, public cloud provisioning, automated power/VM fencing, persistent infrastructure changes, unapproved host contact.

## 0. Required input — do not invent it

- Host inventory: three exact physical host IDs, independent failure domains, owner authorization per host, isolation proof, OS/CPU/architecture, SHA-256 host attestations.
- Image identity: PostgreSQL/gosu **candidate** config digest, independently qualified immutable Patroni and etcd digests, corresponding SBOM/Grype output.
- Secrets: ephemeral lab-only CA, individual mTLS certs, scoped PostgreSQL users; external secret distribution requires platform review.
- Safety authorization: **specific** host failure/partition/fencing experiment tickets and approved rollback operator. Merely approving this runbook is NOT approval for stopping a physical host.
- Test records: synthetic customer/tenant only, expected critical event IDs/receipts, baseline SHA-256 of event ledger and WAL checkpoints.

Run read-only preflight (not a deployment command):

```sh
python scripts/ci/r03_ha_lab_plan.py --inventory lab-authorized-hosts.json --output lab-plan.json
python scripts/ci/r03_ha_evidence_contract.py --output ha-readiness.json
```

The first script generates a plan only. The second **intentionally reports BLOCKED**
until nine scenarios and real evidence exist. Neither opens sockets, SSH, Docker, or triggers fencing.

## 1. Architecture and necessary safety prerequisites

```text
                     HAProxy + Keepalived / VRRP
                           (lab only)
                                 |
              +------------------+------------------+
              |                  |                  |
        Physical host A    Physical host B     Physical host C
        PG17 + Patroni     PG17 + Patroni      PG17 + Patroni
        etcd voting #1     etcd voting #2      etcd voting #3
        watchdog/fence     watchdog/fence      watchdog/fence
              \_________________  ________________/
                    etcd quorum = 2 / 3
       synchronous commit + CL-2/CL-3 receipt evidence
```

Before failure exercises, a DBA must verify **all** of the following:
- TLS-authenticated etcd/Patroni endpoints, 3 voters, observed leader/term,
  quorum majority (2 of 3), identical cluster IDs.
- PostgreSQL `synchronous_commit` (candidate-configured strict semantics),
  `synchronous_standby_names`, actual `pg_stat_replication`, and durability
  receipt barriers matched to APTron CL-2 HOST_PROTECTED and CL-3 CENTRAL_DURABLE.
- Acknowledged critical event ledger is populated with independent, immutable
  tenant/source/event identities; count and SHA-256 recorded **before** any disruption.
- Signed platform plan for watchdog and external power/VM fencing in the
  *actual* lab. Without independently approved fencing, do **not** run a host-stop
  or partition; fail closed to dry-run review.
- Operator-owned restore points, rollback procedure and change window.

Illustrative **read-only** commands to execute manually only on authorized hosts:

```sh
etcdctl --endpoints="$ETCD_ENDPOINTS" --cacert="$ETCD_CA" --cert="$ETCD_CERT" --key="$ETCD_KEY" endpoint status --write-out=table
patronictl -c /path/to/approved/patroni.yml list
psql "$LAB_PG_DSN" -XAtqc "SHOW synchronous_commit"
psql "$LAB_PG_DSN" -XAtqc "SHOW synchronous_standby_names"
psql "$LAB_PG_DSN" -XAtqc "SELECT application_name,state,sync_state,replay_lsn FROM pg_stat_replication"
```

Do not copy customer credentials to GitHub logs or evidence artifacts.

## 2. Nine independent exercises

| ID | Scenario | Required independently captured evidence |
|---|---|---|
| HA-01 | etcd 3-voter quorum and leader | etcd member IDs/terms, 2/3 quorum, mutual TLS, configuration digests |
| HA-02 | synchronous PostgreSQL replication | observed primary/standby LSN and synchronous ACK barrier |
| HA-03 | loss of active PostgreSQL **physical** host including colocated etcd | pre-approved failure injection, new leader, fencing, zero loss of previously acknowledged IDs |
| HA-04 | loss of a standby/etcd voter | no dual-primary, quorum and deterministic degraded behavior |
| HA-05 | primary isolation / network partition and fencing | old primary write denial; no split brain |
| HA-06 | stale former leader rejoin | timeline/LSN reconciliation, no overwrite of committed identity history |
| HA-07 | acknowledged critical event durability | CL-2/CL-3 receipt proof, count/sha before+after, zero missing/duplicated natural IDs |
| HA-08 | populated synthetic backup/restore and PITR | transactional schema, migration history, ledger and recovery point equivalence |
| HA-09 | recovery/rejoin under bounded synthetic load | timings and SLI, quorum, source replay and gap accounting |

The machine-readable contract uses exactly the scenario names from
`scripts/ci/r03_ha_evidence_contract.py`:
`etcd_three_voters_and_quorum`, `synchronous_pg_replication`,
`primary_host_loss`, `standby_host_loss`, `partition_and_fencing`,
`stale_leader_rejoin`, `acknowledged_events_preserved`,
`populated_backup_restore`, `post_failover_recovery_and_rejoin`.

## 3. Acceptance / independent review

- Exact post-test image config IDs and published OCI registry digest (when published),
  image SBOM and scanner database date; all three physical-host attestation hashes.
- Each scenario `result: PASS`, immutable `artifact_sha256` referencing real
  sanitized logs/traces/LSN proofs; signed observation timestamps and operator.
- Durability `acknowledged_critical_events > 0`,
  `acknowledged_event_loss = 0`, `critical_identity_duplicates = 0`.
- DBA checks populated data migration, locale/collation/extension versions,
  rollback, PITR, RPO/RTO; Platform/Security checks fence correctness and
  independently available failure domains.
- `r03_ha_evidence_contract.py` can advance at most to
  `READY_FOR_INDEPENDENT_DBA_REVIEW` after genuine evidence.
  **It never sets `release_eligible=true` and cannot sign an approval.**

**Current disposition:** HOSTS NOT DESIGNATED, FAILURE TESTS NOT RUN,
INDEPENDENT DBA/PLATFORM SIGNATURES NOT RECEIVED, RELEASE NO-GO.
