"""Fault barriers only in tests, around real PG statements and worker transactions."""

import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.entrypoints.worker import run, worker_engine
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.jobs import IntakeRecord


def main():
    mode, path = sys.argv[1:]
    engine = worker_engine(Path(path), "lab")
    stage = None

    def pause(point):
        if mode == point:
            print(json.dumps({"phase": point}), flush=True)
            assert sys.stdin.readline()

    class FaultUow(PostgresJobUow):
        def commit(self):
            pause(f"before_{stage}_commit")
            super().commit()
            pause(f"after_{stage}_commit")

    class FaultJobs(Jobs):
        def claim(self, owner):
            nonlocal stage
            stage = "claim"
            return super().claim(owner)

        def start(self, claim, trace):
            nonlocal stage
            stage = "start"
            return super().start(claim, trace)

        def complete(self, *args):
            nonlocal stage
            stage = "result"
            pause("before_evidence")
            return super().complete(*args)

    @event.listens_for(engine, "after_cursor_execute")
    def after_sql(conn, cursor, statement, parameters, context, executemany):
        if stage == "result":
            if "INSERT INTO evidence" in statement:
                pause("after_evidence")
            if "SELECT audit_append_v2" in statement:
                pause("after_audit")

    snapshot = IntakeRecord.snapshot

    def pausing_snapshot(self):
        pause("snapshot")
        return snapshot(self)

    IntakeRecord.snapshot = pausing_snapshot
    try:
        print(json.dumps({"phase": "ready"}), flush=True)
        assert sys.stdin.readline()
        jobs = FaultJobs(lambda: FaultUow(sessionmaker(engine)))
        if mode == "reclaim":
            print(json.dumps({"reclaimed": jobs.recover(uuid4().hex)}), flush=True)
            return 0
        return run(jobs, threading.Event(), uuid4(), 0, True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
