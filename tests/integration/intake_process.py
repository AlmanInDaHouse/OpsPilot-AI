"""Test-only process harness. Production code contains no fault switches."""

import json
import os
import socket
import sys
from uuid import UUID, uuid4

import uvicorn
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.database import make_engine
from opspilot.adapters.postgres.incidents import PostgresIntakeUow
from opspilot.entrypoints.api.app import create_app
from opspilot.incidents.application.create import CreateIncident
from opspilot.incidents.domain.intake import IncidentInput


def main():
    mode = sys.argv[1]
    if mode.startswith("serve"):
        original_commit = PostgresIntakeUow.commit

        def interrupted_commit(self):
            if mode == "serve_before_commit":
                print(json.dumps({"phase": mode}), flush=True)
                sys.stdin.readline()
            original_commit(self)
            if mode == "serve_after_commit":
                print(json.dumps({"phase": mode}), flush=True)
                sys.stdin.readline()

        PostgresIntakeUow.commit = interrupted_commit
        # The real production composition, restricted app login and real OIDC verifier.
        app = create_app()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
            uvicorn.Server(uvicorn.Config(app, log_level="critical")).run(sockets=[listener])
        return

    engine = make_engine(os.environ["OPSPILOT_TEST_DSN"])
    sessions = sessionmaker(engine)

    class PausedCommit(PostgresIntakeUow):
        def commit(self):
            if mode == "before_commit":
                print(json.dumps({"phase": mode}), flush=True)
                sys.stdin.readline()
            super().commit()
            if mode == "after_commit":
                print(json.dumps({"phase": mode}), flush=True)
                sys.stdin.readline()

    result = CreateIncident(lambda: PausedCommit(sessions)).execute(
        UUID(os.environ["OPSPILOT_TEST_PRINCIPAL"]),
        UUID(os.environ["OPSPILOT_TEST_KEY"]),
        IncidentInput("Proceso", "Laboratorio sintético"),
        uuid4().hex,
    )
    print(json.dumps(result.body()), flush=True)
    engine.dispose()


if __name__ == "__main__":
    main()
