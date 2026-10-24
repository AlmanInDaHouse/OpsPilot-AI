"""Independent durable local worker. Never launched by FastAPI."""

import argparse
import json
import secrets
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.database import make_engine, require_database
from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.jobs import Claim, WorkerRejected


def emit(event: str, worker: UUID, claim: Claim | None = None, **values: Any) -> None:
    item = {
        "event": event,
        "worker_id": str(worker),
        "occurred_at": datetime.now(UTC).isoformat(),
        **values,
    }
    if claim:
        item.update(job_id=str(claim.job_id), workflow_id=str(claim.workflow_id), fence=claim.fence)
    print(json.dumps(item, sort_keys=True), flush=True)


def lease_diagnostic(worker: UUID, claim: Claim, code: str) -> None:
    emit("lease.status", worker, claim, code=code)


class Heartbeat:
    """Independent short PG transactions; Event synchronizes local shutdown, not DB ownership."""

    def __init__(self, jobs: Jobs, claim: Claim, diagnostic: Callable[[str], None]) -> None:
        self.jobs, self.claim, self.diagnostic = jobs, claim, diagnostic
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, name="lease-heartbeat", daemon=True)

    def _run(self) -> None:
        while not self.stop.wait(15):
            try:
                self.jobs.renew(self.claim)
            except Exception:
                self.lost.set()
                self.diagnostic("OWNERSHIP_LOST")
                return
            self.diagnostic("LEASE_RENEWED")

    def __enter__(self) -> "Heartbeat":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop.set()
        # DB statement/lock/connect/pool waits are independently bounded.
        self.thread.join()


def worker_engine(path: Path, environment: str) -> Engine:
    dsn = path.read_text(encoding="utf-8").strip()
    url = make_url(dsn)
    if url.drivername != "postgresql+psycopg" or url.username != "opspilot_worker":
        raise WorkerRejected("WORKER_ROLE_REQUIRED")
    if environment == "production" and url.query.get("sslmode") != "verify-full":
        raise WorkerRejected("TLS_REQUIRED")
    engine = make_engine(dsn)
    try:
        with engine.connect() as connection:
            allowed = connection.execute(
                text("""SELECT current_user='opspilot_worker'
                AND session_user='opspilot_worker' AND NOT (rolsuper OR rolcreatedb OR
                rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit)
                AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                FROM pg_roles r WHERE rolname=current_user""")
            ).scalar_one()
            if not allowed:
                raise WorkerRejected("WORKER_ROLE_REQUIRED")
        require_database(engine)
        return engine
    except Exception:
        engine.dispose()
        raise


def run(jobs: Jobs, stop: threading.Event, worker: UUID, max_polls: int, drain: bool) -> int:
    completed = 0
    polls = 0
    emit("worker.started", worker)
    while not stop.is_set() and (max_polls == 0 or polls < max_polls):
        polls += 1
        claim = jobs.claim(uuid4())
        if claim is None:
            if drain:
                break
            stop.wait(2 + secrets.SystemRandom().uniform(0, 1))
            continue
        emit("job.claimed", worker, claim, version=claim.version)
        try:
            with Heartbeat(jobs, claim, partial(lease_diagnostic, worker, claim)) as heartbeat:
                trace = uuid4().hex
                started = jobs.start(claim, trace)
                if started is None:
                    emit("job.held", worker, claim)
                    continue
                emit("step.started", worker, claim, version=started.version, trace_id=trace)
                try:
                    snapshot = started.incident.snapshot()
                except (ValueError, TypeError):
                    snapshot = None
            # Join the renewal before checking loss: no heartbeat failure can race this check.
            # The short result transaction independently checks DB time after audit.
            if heartbeat.lost.is_set():
                raise WorkerRejected("OWNERSHIP_LOST")
            if snapshot is None:
                jobs.fail(claim, started, trace)
                emit("job.held", worker, claim, code="SNAPSHOT_FAILED", trace_id=trace)
                continue
            evidence = jobs.complete(claim, started, snapshot, trace)
            completed += 1
            emit(
                "job.completed",
                worker,
                claim,
                version=started.version + 1,
                evidence_id=str(evidence),
                trace_id=trace,
            )
        except WorkerRejected as exc:
            emit("job.rejected", worker, claim, code=exc.code)
            if exc.code in {
                "POSTGRES_TRANSIENT",
                "POSTGRES_FAILED",
                "AUDIT_FAILED",
                "COMMIT_FAILED",
                "COMMIT_UNCERTAIN",
            }:
                return 1
            # No automatic retry/reclaim. Any still-LEASED row is retained for T03-06.
    emit("worker.stopped", worker, completed=completed, polls=polls)
    return 0


def nonnegative(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("Must be nonnegative")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-file", required=True, type=Path)
    parser.add_argument("--environment", choices=["lab", "production"], default="lab")
    parser.add_argument("--max-polls", type=nonnegative, default=0, help="0 runs until shutdown")
    parser.add_argument(
        "--drain", action="store_true", help="Stop after first empty claim (bounded lab runs)"
    )
    args = parser.parse_args()
    stop = threading.Event()
    worker = uuid4()
    engine = None

    def shutdown(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        engine = worker_engine(args.dsn_file, args.environment)
        jobs = Jobs(lambda: PostgresJobUow(sessionmaker(engine)))
        return run(jobs, stop, worker, args.max_polls, args.drain)
    except WorkerRejected as exc:
        emit("worker.failed", worker, code=exc.code)
        return 1
    except Exception:
        # Includes parsing/configuration/connect and uncertain commit failures; never traceback/DSN.
        emit("worker.failed", worker, code="DEPENDENCY_OR_CONFIGURATION_FAILURE")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
