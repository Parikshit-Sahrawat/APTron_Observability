"""Real constraints in the owner-authorized disposable staging database only."""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models import Organization, DataSource
from app.critical_events.models import registry


def main():
    if (
        os.environ.get("APTRON_DISPOSABLE_STAGING") != "1"
        or os.environ.get("ENVIRONMENT") != "test"
    ):
        raise RuntimeError("Disposable synthetic staging required")
    checks = []
    with SessionLocal() as db:
        if db.scalar(text("SELECT current_database()")) != "aptron_staging":
            raise RuntimeError("Wrong database for disposable constraint probe")
        orgs = db.scalars(
            select(Organization)
            .where(Organization.code.in_(["LAB-N", "LAB-S"]))
            .order_by(Organization.code)
        ).all()
        if len(orgs) != 2:
            raise RuntimeError("Synthetic tenant fixture absent")
        source = DataSource(
            id=uuid4(),
            organization_id=orgs[0].id,
            name="Critical schema fixture",
            source_type="LINUX",
        )
        db.add(source)
        db.flush()
        event = dict(
            event_key=uuid4(),
            tenant_id=orgs[0].id,
            source_id=source.id,
            event_id="schema-event",
            schema_version="1.0",
            canonicalization_version="1.0",
            payload_sha256=b"a" * 32,
            first_seen_at=datetime.now(timezone.utc),
        )
        db.execute(registry.insert().values(**event))
        checks.append("insert-exact-identity")
        cases = [
            (
                "duplicate-natural-key",
                registry.insert().values(**{**event, "event_key": uuid4()}),
            ),
            (
                "short-hash",
                registry.insert().values(
                    **{
                        **event,
                        "event_key": uuid4(),
                        "event_id": "short",
                        "payload_sha256": b"bad",
                    }
                ),
            ),
            (
                "cross-customer-source",
                registry.insert().values(
                    **{
                        **event,
                        "event_key": uuid4(),
                        "tenant_id": orgs[1].id,
                        "event_id": "forged",
                    }
                ),
            ),
            (
                "immutable-hash",
                registry.update()
                .where(registry.c.event_key == event["event_key"])
                .values(payload_sha256=b"b" * 32),
            ),
            (
                "retained-identity",
                registry.delete().where(registry.c.event_key == event["event_key"]),
            ),
        ]
        for name, statement in cases:
            try:
                with db.begin_nested():
                    db.execute(statement)
            except IntegrityError:
                checks.append(name)
            else:
                raise AssertionError(
                    "Database accepted invalid critical event: " + name
                )
        assert (
            db.scalar(
                select(registry.c.payload_sha256).where(
                    registry.c.event_key == event["event_key"]
                )
            )
            == b"a" * 32
        )
        db.rollback()  # All fixture writes are disposable and uncommitted.
    print(
        json.dumps(
            {
                "status": "PASS",
                "checks": checks,
                "production_eligible": False,
                "ha_certified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
