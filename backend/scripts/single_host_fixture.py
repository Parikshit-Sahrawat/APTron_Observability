"""Synthetic SH-02 maintenance fixture. Never called by application startup."""

import hashlib
import json
import os
from pathlib import Path
import sys

from sqlalchemy import text
from app.db.session import engine


def main():
    if os.environ.get("APTRON_SH02_FIXTURE") != "1":
        raise RuntimeError("Disposable SH-02 fixture flag required")
    with engine.connect() as db:
        if db.scalar(text("SELECT current_database()")) != "aptron":
            raise RuntimeError("Unexpected fixture database")
    if sys.argv[1] == "initialize":
        from scripts.auth_tenant_probe import seed
        from psycopg import sql

        ids = seed()
        raw = engine.raw_connection()
        try:
            db = raw.driver_connection
            db.execute(Path("/fixture/restricted-roles.sql").read_text())
            db.execute(
                sql.SQL(
                    "CREATE ROLE sh02_app LOGIN PASSWORD {} IN ROLE opscontrol_app"
                ).format(sql.Literal(os.environ["SH02_APP_PASSWORD"]))
            )
            db.commit()
        finally:
            raw.close()
        print(json.dumps(ids))
    elif sys.argv[1] == "snapshot":
        # Stable fixture identities/FKs, not mutable worker timestamps/sessions.
        queries = {
            "organizations": "SELECT id,code FROM organizations ORDER BY id",
            "sources": "SELECT id,organization_id FROM data_sources ORDER BY id",
            "users": "SELECT id,username,password_hash FROM users ORDER BY id",
            "executions": "SELECT id,job_order_id,execution_type,status FROM job_order_histories ORDER BY id",
        }
        result = {}
        with engine.connect() as db:
            for name, query in queries.items():
                rows = [list(row) for row in db.execute(text(query))]
                result[name] = {
                    "count": len(rows),
                    "sha256": hashlib.sha256(
                        json.dumps(rows, default=str, sort_keys=True).encode()
                    ).hexdigest(),
                }
            result["cluster"] = str(
                db.scalar(text("SELECT system_identifier FROM pg_control_system()"))
            )
        print(json.dumps(result, sort_keys=True))
    else:
        raise ValueError("Unknown SH-02 fixture operation")


if __name__ == "__main__":
    main()
