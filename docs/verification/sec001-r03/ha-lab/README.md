# APTron SEC001-R03 — owner-approved three-host functional HA lab blueprint

**DESIGN APPROVED / CONFIGURATION PREPARED / NOT DEPLOYED / NOT CERTIFIED.**
Host labels are proposals, **not discovered machines**. A physical-infrastructure
inventory is not part of the owner's prior approvals.

Each of 3 genuinely separate Ubuntu 24.04 LTS linux/amd64 hosts should have
at least 8 logical CPUs, 32 GiB RAM and a 200 GiB SSD, with one PostgreSQL 17
+ Patroni member and one etcd voter. This functional lab sizing is **not** the
3×16 vCPU/64 GiB production sizing candidate.

* `inventory.example.json` uses TEST-NET 192.0.2.11–13 and missing immutable
  image IDs, certificates, and physical attestations; it **must BLOCK**.
* `collect_host_facts.py` runs locally and read-only on each real, existing,
  owner-authorized Linux host. It collects only CPU, memory, filesystem size
  and OS; it cannot prove physical independence or authenticate its operator.
  Run as: `python3 collect_host_facts.py --existing-data-mount /existing/data --output /secure/ha-01-facts.json`.
  Do not commit private host inventory or credentials.
* Platform must map the facts to a signed inventory of 3 distinct physical
  machines/failure domains, real private RFC1918 IPs, explicit **individual**
  host authorization, isolated VLAN/firewall, and independent TLS/identity proof.
* `render_node.py` **only** checks declared fields and renders local JSON
  (valid YAML) Patroni config and node.env. It does NOT verify attestation
  signatures, run a container or prove physical hosts:
  `python3 render_node.py --inventory /secure/lab.json`,
  then `--node aptron-ha-01 --output-dir /secure/rendered-ha-01`.
* `compose.node.yaml` is inert unless an operator explicitly enables
  `--profile approved-certification`. No image digests/secrets or certs ship
  with it. A combined PostgreSQL17/Patroni image must be independently built
  and qualified before actual use, with exact OCI manifest digests.
* etcd peer/client TLS and Patroni REST/postgres TLS require real isolated
  SAN-bound certs and isolated passwords. All services use non-root UIDs,
  cap drop, read-only filesystems where supported, no automatic restart or
  public port bindings. Host networking requires separate network approval.
* Patroni has strict synchronous replication and
  `watchdog.mode=required`; the Compose template intentionally does not mount
  `/dev/watchdog` or support fault injection. Never weaken the fencing gate
  to make containers start. No HAProxy/VRRP or power/VM fencing is provisioned.

`ha-acceptance.template.json` lists the 9 required test scenarios as
NOT_EXECUTED. Only an independently authorized DBA/Platform/Collector operator
can execute actual host loss, partitions/fencing, populated backup/restore and
acknowledged critical-event durability checks. Evaluate real signed evidence
using `scripts/ci/r03_ha_evidence_contract.py`. Its success **only** means
READY_FOR_INDEPENDENT_DBA_REVIEW, never release approval.

Manual runbook: `../HA_THREE_HOST_CERTIFICATION_RUNBOOK.md`.
Architecture references: https://patroni.readthedocs.io/en/latest/yaml_configuration.html
and https://etcd.io/docs/v3.6/op-guide/security/.

**No provisioned physical hosts, no real IPs, no external secrets, no
signed attestation, no failure injections, no license decisions, and NO-GO.**
