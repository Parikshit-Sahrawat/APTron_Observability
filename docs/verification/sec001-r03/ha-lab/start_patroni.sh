#!/bin/sh
# For later independently approved isolated lab execution only.
# No secret echo, xtrace, fallback or provisioning.
set -eu
for secret in /run/lab-secrets/pg-superuser.pass /run/lab-secrets/pg-replication.pass /run/lab-secrets/patroni-api.pass; do
  [ -r "$secret" ] || { echo 'Approved lab-only secret file missing' >&2; exit 1; }
done
export PATRONI_POSTGRESQL_AUTHENTICATION_SUPERUSER_PASSWORD="$(cat /run/lab-secrets/pg-superuser.pass)"
export PATRONI_POSTGRESQL_AUTHENTICATION_REPLICATION_PASSWORD="$(cat /run/lab-secrets/pg-replication.pass)"
export PATRONI_RESTAPI_AUTHENTICATION_PASSWORD="$(cat /run/lab-secrets/patroni-api.pass)"
exec /usr/local/bin/patroni "${1:-/etc/aptron/patroni.yaml}"
