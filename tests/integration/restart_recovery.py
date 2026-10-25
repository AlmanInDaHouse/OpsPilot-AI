"""Standalone local PG restart proof; run sequentially, outside normal pytest suites."""

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from opspilot.adapters.postgres.database import make_engine
from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.jobs import WorkerRejected
from tests.integration.conftest import ROOT, dsn_for, postgres_database
from tests.integration.test_recovery import eligible, expire, integrity
from tests.integration.test_worker import rows
from tests.integration.test_workflow_persistence import seed


def main():
    compose = ["docker", "compose", "-f", str(ROOT / "infra/compose.yaml")]

    def lab_snapshot():
        engine = make_engine(dsn_for("admin", "opspilot_lab"))
        try:
            with engine.connect() as conn:
                result = {}
                for table in (
                    "principals",
                    "role_grants",
                    "audit_streams",
                    "audit_events",
                    "incidents",
                    "workflows",
                    "workflow_steps",
                    "jobs",
                    "evidence",
                    "api_idempotency",
                    "alembic_version",
                ):
                    data = (
                        conn.execute(
                            text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                        )
                        .scalars()
                        .all()
                    )
                    result[table] = {
                        "rows": len(data),
                        "hash": hashlib.sha256(
                            json.dumps(data, sort_keys=True, default=str).encode()
                        ).hexdigest(),
                    }
                return result
        finally:
            engine.dispose()

    lab_before = lab_snapshot()
    with postgres_database() as pg:
        jobs = Jobs(lambda: PostgresJobUow(pg["sessions"]["worker"]))
        retry = seed(pg)
        claim = jobs.claim(uuid4())
        started = jobs.start(claim, uuid4().hex)
        jobs.retry(claim, started, uuid4().hex)
        pending = seed(pg, creator=retry["creator"])
        with pg["engines"]["admin"].begin() as lock:
            lock.execute(text("SELECT id FROM jobs WHERE id=:id FOR UPDATE"), {"id": retry["job"]})
            leased = jobs.claim(uuid4())
        assert leased.job_id == pending["job"]
        expire(pg, pending["job"])
        before = [rows(pg, item) for item in (retry, pending)]
        subprocess.run([*compose, "stop", "postgres"], cwd=ROOT, check=True)
        try:
            try:
                jobs.claim(uuid4())
            except WorkerRejected:
                rejected = True
            else:
                raise AssertionError("Claim accepted with PostgreSQL down")
        finally:
            subprocess.run(
                [*compose, "up", "-d", "--no-deps", "--wait", "postgres"], cwd=ROOT, check=True
            )
        for engine in pg["engines"].values():
            engine.dispose()
        after = [rows(pg, item) for item in (retry, pending)]
        assert before == after
        lab_after = lab_snapshot()
        assert lab_before == lab_after
        assert jobs.recover(uuid4().hex)
        eligible(pg, retry["job"])
        for _ in range(2):
            claim = jobs.claim(uuid4())
            started = jobs.start(claim, uuid4().hex)
            jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
        final = [integrity(pg, item) for item in (retry, pending)]
        assert all(item["job"]["state"] == "DONE" and len(item["evidence"]) == 1 for item in final)
        raw = json.dumps(
            {"before": before, "after_restart": after, "final": final}, indent=2, default=str
        ).encode()
        (ROOT / "artifacts/local/recovery-pending-restart-raw.json").write_bytes(raw)

        def summary(items):
            return [
                {
                    "workflow": {
                        key: item["workflow"][key]
                        for key in (
                            "state",
                            "version",
                            "definition_version",
                            "deadline_at",
                            "budget_spent_ms",
                        )
                    },
                    "job": item["job"],
                    "step_status": item["step"]["status"],
                    "evidence_count": len(item["evidence"]),
                    "audit_count": len(item["audit"]),
                }
                for item in items
            ]

        report = {
            "verdict": "PASS",
            "database": pg["database"],
            "claim_during_outage_rejected": rejected,
            "before": summary(before),
            "after_restart": summary(after),
            "final": summary(final),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "lab_before": lab_before,
            "lab_after": lab_after,
            "scope": "Two ephemeral jobs across real PostgreSQL stop/start; existing volume preserved",
        }
        Path("artifacts/session-03/recovery/pending-restart.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
