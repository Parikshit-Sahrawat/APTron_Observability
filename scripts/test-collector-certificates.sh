#!/usr/bin/env bash
# Own a fresh PG17 database, migration history and test-only PKI for each run.
set -euo pipefail
cd "$(dirname "$0")/../backend"
python_bin=${OPSCONTROL_TEST_PYTHON:-python}
export POSTGRES_PASSWORD
POSTGRES_PASSWORD=$("$python_bin" -c 'import secrets; print(secrets.token_hex(32))')
container=$(docker run -d --rm -e POSTGRES_PASSWORD -e POSTGRES_DB=s03_auth_lab -p 127.0.0.1::5432 postgres:17)
trap 'docker stop "$container" >/dev/null' EXIT
address=$(docker port "$container" 5432/tcp)
export DATABASE_URL="postgresql+psycopg://postgres:$POSTGRES_PASSWORD@$address/s03_auth_lab"
export ENVIRONMENT=test APTRON_DISPOSABLE_STAGING=1
for attempt in {1..60}; do
    if docker exec "$container" pg_isready -h 127.0.0.1 -U postgres -d s03_auth_lab >/dev/null; then break; fi
    sleep 1
done
"$python_bin" -m alembic upgrade head
"$python_bin" -m alembic check
"$python_bin" -m alembic downgrade 0039_critical_event_storage
"$python_bin" -m alembic upgrade head
"$python_bin" -m scripts.collector_certificate_probe
