# Single-host deployment candidate — SH-01

Owner direction: 18 November 2026; bounded implementation requested 23 November.
This is a review candidate, not an approved release or an installer. No host,
database, TLS key, runtime identity or production environment is provisioned.
It is stacked on PR #116 at `4b9c346f53e16217e2a93e855c7d89507f11be1d`.

## Steady-state topology

| Service | Responsibility | Storage / exposure |
| --- | --- | --- |
| gateway | Same-origin SPA and HTTPS reverse proxy | Read-only exact-build nginx config and customer TLS files; only published port, loopback by default |
| engine | Existing API and monitoring worker, supervised together | Restricted database identity; temporary heartbeat; no published port |
| postgres | PostgreSQL 17, local synchronous commit with fsync/full-page writes | Pre-created persistent customer host directory; internal network only |

Exactly three **steady-state** central containers; migration or backup operations
may use a temporary maintenance container. Windows/Linux native Collectors remain
separate monitored-host agents. This slice does not implement or embed a native
Collector, expose S03 critical-event ingestion, issue receipts, or start deferred
receipt/reconciliation workers. Existing tenant/RBAC and monitoring APIs are reused.
SOS 1.x/JS7 Job Monitoring, API, Synthetic and RUM remain product domains; their
runtime certification is not supplied by packaging. No Grafana/Prometheus/EKS/AKS
module or dependency is added.

API and existing monitoring worker are separate child processes under one Python
supervisor. Startup validates the existing production database-role restrictions
before either child starts. An unexpected child exit terminates/reaps the pair
and exits nonzero. Compose can restart the container. SIGTERM/SIGINT initiate
bounded shutdown (SIGINT to both Python process groups, then SIGKILL after 20s).
The engine health check requires both HTTP health and the worker's existing
DB-checked heartbeat no older than 30s. Docker marks a stalled container unhealthy;
`restart: unless-stopped` does **not** restart a live but unhealthy container.
Customer operations must alert/investigate and perform a controlled restart.
This is health detection, not telemetry-completeness or job-success proof.

## Preparation contract

1. Select the supported Linux host and capacity after representative measurement.
   Reserve an unused ingress subnet; changing it requires matching gateway IP.
   Do not infer host-failure tolerance from containers, networks or restarts.
2. Build and qualify the existing backend runtime, frontend runtime and PostgreSQL
   image roles on the exact candidate source; bind security, SBOM, License/NOTICE
   decisions and acceptance to immutable image digests. This adds no ninth image
   role and changes none of the eight-image gates. Backend runtime already copies
   `scripts/`, including the new supervisor. No upstream Collector pin is changed.
3. Build the SPA for same-origin API calls (`VITE_API_BASE_URL=''`). Render nginx
   using the **same build's** index.html, not a different local build:

   ```sh
   node frontend/scripts/render-production-nginx.mjs \
     /path/to/exact-build/index.html /srv/aptron/config/nginx.conf \
     http://engine:8000 deploy/single-host/nginx.conf.template
   ```

   Preserve the existing CSP script-hash rules. The optional template argument
   leaves the old renderer invocation/default template compatible. Verify the SPA
   does not contain a remote or localhost API base. Gateway suppresses access logs
   to avoid credential-bearing query strings and overwrites forwarding headers.
4. Create the persistent PostgreSQL directory with the ownership required by the
   selected PG17 image. Store customer secrets/config outside this checkout with
   restrictive permissions. Compose secrets are bind-mounted files, not encrypted
   secret management. The frontend TLS key must be readable by the selected nginx
   master; engine env is read by Compose and is visible to Docker administrators.
5. Copy and fill `deployment.env.example` and `engine.env.example` outside git.
   Database owner credentials are used only for initialization/maintenance. Use
   the repository's separate migration image to apply the existing migrations,
   and separately provision the restricted runtime role (see
   `../examples/restricted-database-roles.sql`). The runtime role must not own
   tables, bypass RLS, disable triggers or mutate append-only evidence. **No
   automatic migrations or default admin credentials are included.** Do not
   bootstrap against existing customer data without a verified backup/review.
6. Validate the resolved Compose structure without writing its secret-bearing
   output to a report or terminal:

   ```sh
   set -o pipefail
   docker compose --env-file /srv/aptron/config/deployment.env \
     -f deploy/single-host/compose.yaml config --format json \
     | python scripts/validate_single_host.py
   ```

   The validator rejects mutable tags, extra services, published API/DB ports,
   host networking, privileged mode, missing persistent data and proxy mismatch.
   It does not validate image approval, TLS contents, runtime privileges or host
   firewall rules. No `up` command is an authorized production action here.
   Default binding is loopback; externally exposing HTTPS needs customer network
   and TLS review. Destination allowlists do not replace egress firewall policy.

## Backup, restore and durability boundary

Local PG commit protects against qualified process/restart scenarios only to the
extent supported by the host filesystem/storage. It does not protect against host
loss, disk loss, theft, corruption or off-site disaster. HOST_PROTECTED and
CENTRAL_DURABLE receipt classes remain disabled; no renamed receipt or implicit
positive acknowledgment is introduced. PR #116's disposable-only protection
policy is not converted to a production ingestion policy by this manifest.

Before any release of this topology, customer procedures must define measured
RPO/RTO, retention, access control, encrypted off-host backups, encryption-key
custody and recovery access. Establish a consistent database backup plus any
required WAL/PITR archive using the selected PG17 tooling. Keep application
configuration, approved image digests and separately protected secrets recoverable.
Do not copy a live PGDATA directory as a valid database backup. A second directory
on the same host is not an off-host backup. Backup encryption/upload tooling and
WAL archiving are **not configured or certified by this slice**.

Restore into a new, isolated directory/project; never overwrite the source data.
Use the matching PostgreSQL major version, verify backup integrity, restore roles
and data, apply only reviewed schema changes, and compare tenant/source identity,
immutable event evidence and known row counts/hashes. Verify sign-in, permissions,
API/worker recovery and unknown-commit handling before a customer-controlled
cutover. Preserve the original directory and evidence. Do not use `down -v`,
prune, truncate or an in-place destructive restore as a recovery procedure.

## Acceptance still required

- Real three-container Linux startup, TLS/CSP/browser/authentication, restricted DB
  role and destination policies, persistent restart and host-reboot tests.
- Worker/API crash and stalled-worker detection in actual images; same-origin SPA
  build/CSP coupling; native worker/package/monitoring parity and resource limits.
- Disposable off-host encrypted backup/restore and recovery measurement on the
  selected host/storage. Capacity targets require benchmarks, not this example.
- Existing eight-image security/licensing, privacy and owner release acceptance.
  Optional multi-host HA is a separate customer-managed topology with its own
  fencing/failover/durability acceptance, not a default initial deployment gate.
  Existing gate code/policies are unchanged; policy reconciliation is separate.

Local source-level tests and configuration review are not container/runtime,
backup, HA, native Collector or production acceptance.

## SH-02 automation

The `single-host-acceptance` job in the existing staging workflow builds/scans the actual backend runtime, migration, production frontend and PostgreSQL roles and exercises this manifest. See [SH-02 scope and evidence](../../docs/verification/single-host-sh02/REPORT.md). Automation implementation is not an executed runtime PASS. The health probe now expects the production plaintext rejection on its internal connection; the independent acceptance probe requires a successful verified HTTPS request through the gateway. The production frontend image defaults to same-origin API access.
