#!/usr/bin/env bash
# Own a fresh PG17 database, migration history and test-only PKI for each run.
set -euo pipefail
cd "$(dirname "$0")/../backend"
python_bin=${OPSCONTROL_TEST_PYTHON:-python}
export POSTGRES_PASSWORD
POSTGRES_PASSWORD=$("$python_bin" -c 'import secrets; print(secrets.token_hex(32))')
container=$(docker run -d --rm -e POSTGRES_PASSWORD -e POSTGRES_DB=s03_auth_lab -p 127.0.0.1::5432 -p 127.0.0.1::5433 postgres:17 -c synchronous_commit=local -c synchronous_standby_names=s03_test_standby)
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
# Seed a genuine unenrolled installation in the pre-registry schema.
export APTRON_LAB_LEGACY_ROW
APTRON_LAB_LEGACY_ROW=$("$python_bin" - <<'PYTHON'
import os
from sqlalchemy import create_engine, text
from scripts.collector_certificate_probe import fixture

engine = create_engine(os.environ["DATABASE_URL"])
scope, _ = fixture(engine)
with engine.connect() as db:
    print(db.scalar(text("SELECT to_jsonb(a)::text FROM managed_agents a WHERE id=:id"),
                    {"id": scope["installation_id"]}))
PYTHON
)
"$python_bin" -m alembic upgrade head
"$python_bin" -m scripts.collector_certificate_probe
# A physical standby shares the primary system identifier but must deny admission.
docker exec -u postgres "$container" pg_basebackup -D /tmp/s03-replica -R -X stream -c fast
docker exec -u postgres "$container" pg_ctl -D /tmp/s03-replica -l /tmp/s03-replica.log -o "-p 5433 -c listen_addresses='*'" -w start
export APTRON_LAB_STANDBY_PORT
APTRON_LAB_STANDBY_PORT=$(docker port "$container" 5433/tcp | cut -d: -f2)
export APTRON_LAB_PRIMARY_ADDRESS
APTRON_LAB_PRIMARY_ADDRESS=$(docker inspect -f '{{(index .NetworkSettings.Networks "bridge").IPAddress}}' "$container")
export APTRON_LAB_SYSTEM_ID
APTRON_LAB_SYSTEM_ID=$(docker exec -u postgres "$container" psql -Atqc 'SELECT system_identifier FROM pg_control_system()')
APTRON_TXN_LAB=1 "$python_bin" -m unittest discover -s tests -p test_transactional_ingestion.py -v
