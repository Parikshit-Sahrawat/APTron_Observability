# APTron Observability — Evidence-first host, fencing, HA witness and legal-signoff decision (v1.0)

**Date:** 2026-11-16 | **Owner authorization:** engineering preparation / research / source qualification.
**NOT:** evidence of three existing hosts, permission to provision, a physical fault window, witness execution, independent legal advice, approval to merge, or a Tier C waiver.
**Binding architecture:** customer self-hosted; Linux Docker Compose + external HA; 3 hosts with colocated PG17 + Patroni + etcd; one-host loss has **zero centrally acknowledged CL-3 critical-event loss**. Native Collector and release gates unchanged. Full production candidate sizing remains **3 × 16 vCPU / 64 GiB**, NOT replaced by this functional-lab proposal of **3 × 8 vCPU / 32 GiB / 200 GiB**.

## 1. Actual host discovery: selection, not fabrication

**Best choice for the currently authorized internal lab:** **three already-owned bare-metal machines or three proven separate physical hypervisor hosts**, each Ubuntu 24.04 LTS, x86-64, and meeting the owner-approved LAB size. Select from the **owner's actual asset/CMDB inventory**, after operator inspection and independent Platform/SRE attestations. We searched existing APTron Drive documentation and PR #108: it contains no actual lab serials, CMDB records, valid host IP allocation or host-specific authorization. **No three machines have been identified.**

Rank only when evidence exists:
1. **Existing, physically separate bare-metal lab hosts with independent BMC/watchdog:** preferred; no purchase; cleanest real host-failure test.
2. **Existing VMs explicitly mapped 1:1 to three different physical hypervisors:** conditional; require signed hypervisor host IDs, anti-affinity/evacuation mapping and independent failure-domain proof. The current `physical_host:true` lab inventory MUST NOT be spoofed for VMs; a separately approved inventory schema is needed.
3. **Three VMs on one desktop/hypervisor or a single GitHub runner:** useful for functional simulation only; **cannot** certify physical-host loss.

Collect read-only CPU/memory/disk facts using `ha-lab/collect_host_facts.py` on *each owner-authorized host* through its own operator. Collect **without publishing to GitHub:** hardware model/serial or certified hypervisor UUID, actual isolated private IP, BMC identity, rack, power feed, host failure domain, attester's identity/signature, machine-specific owner authorization. No hidden SSH/network scan or cloud purchasing. Blank intake: `REAL_HOST_DISCOVERY_REQUEST.template.json`.

## 2. Proposed network, NOT an allocated network

A **candidate** only: isolated data VLAN **10.77.30.0/27** and physically/administratively separated BMC/control VLAN **10.77.31.0/27**. The three candidate data node IPs are **10.77.30.11 / .12 / .13**, and an optional client VIP candidate is **10.77.30.10**. None is a discovered/assigned usable IP. The existing TEST-NET example `192.0.2.11/12/13` remains intentionally non-deployable. Network owner must check address overlap, sign VLAN/ACL isolation and reserve real addresses before any render/deploy.

**Default-deny east-west ACL matrix (no Internet ingress):**

| Destination | Port | Allowed source ONLY | Required defense |
|---|---|---|---|
| etcd client API | TCP 2379 | Three Patroni nodes and authorized etcd admin endpoints | Dedicated member/client mTLS, independently approved CA and least privilege |
| etcd Raft peer | TCP 2380 | Exactly the three etcd members | Member-specific peer mTLS/SAN; quorum 2/3 |
| PostgreSQL | TCP 5432 | Cluster replication peers, controlled lab app/test client or approved proxy | TLS + SCRAM; credential roles and ACLs |
| Patroni REST | TCP 8008 | Cluster nodes and authorized health/proxy client only | REST **verify_client=required**, valid ctl.client cert, HTTPS; Basic auth for unsafe actions |
| SSH | TCP 22 | Lab bastion only | Per-operator credentials / logging; no public SSH |
| HAProxy listener | proposed TCP 5000 | Synthetic client CIDR only | Authenticated writer-role health check; optional, not provisioned |
| BMC/Redfish | TCP 443, management VLAN | Independent approved fence controller / authorized break-glass operator only | Separate credentials, TLS key verification and audit; NEVER from app containers |

NTP/PKI/backup egress must be explicitly allowlisted and validated; no unrestricted external egress. Do not enable `network_mode:host` Compose until network approval. The lab renderer's declared inventory and signer fields remain **untrusted assertions** until independently cross-checked against CMDB and signed evidence.

## 3. Fencing decision: do not enable unsafe HA

**Preferred fail-closed safety:** Patroni `watchdog.mode=required` with a genuine, tested **host watchdog**; add independently controlled **out-of-band BMC/Redfish or verified VM power fence** and dedicated control network wherever available. A watchdog protects against a stalled old primary, and verified fencing protects against duplicate writers during authorized isolation tests. Require **independent DBA and Platform/Security signoff**.

**Critical discovered gap in current build:** the Compose lab deliberately DOES NOT pass `/dev/watchdog` into the container; the signed unit-test documentation does not prove that a real watchdog can be driven by UID 70 under the hardened container capability/security profile. **Therefore this bundle MUST NOT be started or called HA-qualified.** Do not switch `watchdog.mode` to `off` or `automatic` to obtain a green test. If least-privilege watchdog integration cannot be independently certified, stop and request a separately approved host-level fencing/Patroni alternative. No shutdown, power-cycle, partition, IPMI or Redfish action is authorized by this document.

**Config hardening implemented:** Patroni REST `verify_client=required`, explicit `ctl` client certificate/key/CA, and PostgreSQL minimum TLS v1.2. These parameters are **offline-rendered only**, and must be runtime tested with the *actual* Patroni/image versions after independently authenticated cert issuance.

Primary documentation: https://patroni.readthedocs.io/en/latest/watchdog.html ; https://patroni.readthedocs.io/en/latest/security.html ; https://patroni.readthedocs.io/en/latest/replication_modes.html ; https://etcd.io/docs/v3.6/op-guide/security/ .

## 4. Independently witnessed nine-scenario HA evidence

Use `PHYSICAL_HA_WITNESS.template.json` and the existing `HA_THREE_HOST_CERTIFICATION_RUNBOOK.md`. All 9 scenarios must remain `NOT_EXECUTED` until actual isolated host instrumentation and authorized fault windows exist.

Before tests, require: three separately signed physical asset/failure-domain attestations; 3-member etcd TLS/quorum and Patroni CLI proof; actual hardware watchdog activation; separate BMC fence/cutoff proof; validated backup/rollback; synthetic CL-2/CL-3 receipts and independent immutable natural identity records; UTC+monotonic time; exact image OCI digests and package/source evidence; operator, witness and stop authority **distinct persons**.

**Pass or fail, without rewriting history:**
- HA-01/02: 3 etcd voters, 2/3 quorum, PG synchronous standby with verified flush/replay LSN and safe ACK semantics.
- HA-03/04: independently authorized **actual** primary/standby host loss; no split-brain, promoted node and fencing witness; no loss of previously acknowledged CL-3 natural IDs.
- HA-05/06: network partition and stale former-primary return; old writer fenced before new writer can ACK; no conflicting leaders/writes.
- HA-07: nonzero central CL-3 acknowledgments, **zero previously acknowledged missing event IDs**, zero identity duplicates, match registry/inbox/ledger/receipt/outbox and signed hashes.
- HA-08: populated synthetic PITR/backup + recovery, schema/extension/receipt continuity.
- HA-09: bounded load and recovery/rejoin, observed RPO/RTO/SLIs, no silent gaps.

Stop tests immediately on conflicting primaries, invalid clock/witness, missing fence or unexpected data movement. A single-host 0-CL-3-loss result is **not** proof of site-level RPO≤300s or RTO≤900s/3600s; those are distinct later site/DR tests. A passing machine-readable contract is still `READY_FOR_INDEPENDENT_DBA_REVIEW` at most; not a signature.

## 5. Independent final OCI License/NOTICE signature path

**Historical owner workbook approved for triage only:** 2,506 repeated image/component rows across eight roles; UAT 941 and pinned Collector 934 missing scanner-reported SPDX declarations. These are missing metadata, not legal infringements. The confirmed snapshot source commit `96c8b8c810c81dd92dd6d9f969c24fa00bf7822d` and eight Docker config IDs are **not** final distribution OCI manifest IDs.

**Best legal path:** nominate an **independent OSS licensing lawyer or authorized independent internal Legal/Compliance specialist**, independent of the engineering author. Candidate referral source: official OpenChain partner directory https://openchainproject.org/partners (includes Mishi Choudhary & Associates among listed law firms), or separately vet a suitable India OSS counsel. **No engagement, fees, reviewer credential or signature is assumed or authorized.** An OpenChain ISO/IEC 5230 program can structure obligations but does not itself constitute legal advice or product-license approval (OpenChain FAQ).

For **each of all eight final images**, the release engineer provides: `registry/name@sha256:<actual OCI manifest>`; verified architecture + Docker config ID; exact Git SHA; immutable Syft and CycloneDX SBOM; Grype DB timestamp + raw findings; license expressions/dual license choices; license/NOTICE text; source/patch changes, copyright and source-offer obligations; resolved GPL/LGPL/MPL/EPL and proprietary-license exceptions; vendor patch redistribution authorization if Root.io bits enter any image. No scanner findings may be suppressed to pass the gate. The reviewer independently signs an image **digest-bound PDF/memo or similarly verifiable digital record**, identity, independence, applicable jurisdiction, decision scope, SHA-256 of evidence/NOTICE bundle, timestamp, verifier, and signed exception list. Validate signature with the actual independent signer's approved certificate/key; do not invent a legal signature.

The blank `FINAL_OCI_LEGAL_SIGNOFF_REQUEST.template.json` records all eight roles as PENDING. **Separate GitHub approval:** an eligible independent writer submits a real approval after the technical/legal gates; an owner comment or assistant commit is not a code-review approval.

Helpful public controls: https://spdx.org/licenses/ ; https://openchainproject.org/license-compliance ; https://openchainproject.org/resources/faq ; https://docs.sigstore.dev/cosign/verifying/verify/ .

## 6. Decision table and final gates

| Evidence/decision | Recommended assumption | Actual status | Independent release authority |
|---|---|---|---|
| Three test hosts | Existing separate physical hosts; 8/32/200 each | **NOT IDENTIFIED** | Per-host CMDB + Platform witness |
| Data subnet / ACL | 10.77.30.0/27 isolated, 2379/2380/5432/8008 etc | **NOT ALLOCATED** | Network/Security approval |
| BMC/control subnet | 10.77.31.0/27 separate | **NOT ALLOCATED** | Platform/Security |
| Watchdog/fence | Host watchdog required + independent OOB fence | **NOT IMPLEMENTED/TESTED** | DBA/SRE/Security |
| Live 9 HA scenarios | Signed synthetic ledger/receipts and witness | **NOT EXECUTED** | Independent DBA/Platform |
| Eight-image legal | Actual release OCI digest and independent signature | **NOT SIGNED** | Qualified independent lawyer/compliance |
| Mandatory Tier C | Zero unreviewed Critical/High/Unknown and legal approvals | **BLOCKED** | Existing unchanged CI + humans |
| Merges/releases | Approved PR branch, no automatic merge | **NO-GO** | Owner after all gates |

No procurement, resource provision, outbound vendor contact, real host connection, fault injection, production deployment, PR merge, or change to eight-role Tier C occurred.
