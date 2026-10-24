"""Test-only HTTP process pauses at the actual cancellation commit boundary."""

import json
import socket
import sys

import uvicorn

from opspilot.adapters.postgres.workflows import PostgresAccessUow
from opspilot.entrypoints.api.app import create_app


def main():
    mode = sys.argv[1]
    original = PostgresAccessUow.commit

    def paused(self):
        if mode == "before_commit":
            print(json.dumps({"phase": mode}), flush=True)
            sys.stdin.readline()
        original(self)
        if mode == "after_commit":
            print(json.dumps({"phase": mode}), flush=True)
            sys.stdin.readline()

    PostgresAccessUow.commit = paused
    app = create_app()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
        uvicorn.Server(uvicorn.Config(app, log_level="critical")).run(sockets=[listener])


if __name__ == "__main__":
    main()
