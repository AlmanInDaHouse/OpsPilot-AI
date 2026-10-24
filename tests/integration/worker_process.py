"""Test-only stdin barriers around the REAL worker loop; no product fault switches."""

import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.entrypoints.worker import run, worker_engine
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.jobs import IntakeRecord


def main():
    mode, path = sys.argv[1:]
    engine = worker_engine(Path(path), "lab")
    if mode == "snapshot_failure":

        def broken_snapshot(self):
            raise ValueError("Test-only local handler failure")

        IntakeRecord.snapshot = broken_snapshot

    def pause(phase):
        if mode == phase:
            print(json.dumps({"phase": phase}), flush=True)
            assert sys.stdin.readline(), "Missing test barrier release"

    class PausingJobs(Jobs):
        def claim(self, owner):
            result = super().claim(owner)
            if result:
                pause("after_claim")
            return result

        def start(self, claim, trace):
            result = super().start(claim, trace)
            pause("after_start")
            return result

        def complete(self, claim, started, snapshot, trace):
            pause("before_result")
            result = super().complete(claim, started, snapshot, trace)
            pause("after_result")
            return result

    try:
        print(json.dumps({"phase": "ready"}), flush=True)
        assert sys.stdin.readline(), "Missing start barrier"
        return run(
            PausingJobs(lambda: PostgresJobUow(sessionmaker(engine))),
            threading.Event(),
            uuid4(),
            0,
            True,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
