"""Prove non-root image initialization on a new anonymous volume, then remove only it."""

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    name = "opspilot-s02-fresh-" + uuid4().hex[:12]
    credential_file = ROOT / "artifacts/local/pg_admin"
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "container": name, "verdict": "FAIL"}
    started = False
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                name,
                "--network",
                "none",
                "--memory",
                "256m",
                "--cpus",
                "1",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                f"type=bind,source={credential_file},target=/run/secrets/pg_admin,readonly",
                "--env",
                "POSTGRES_PASSWORD_FILE=/run/secrets/pg_admin",  # pragma: allowlist secret (environment name and file reference)
                "opspilot-postgres:18.6-s02",
            ],
            check=True,
            capture_output=True,
        )
        started = True
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Fresh cluster did not start")
        result = subprocess.run(
            [
                "docker",
                "exec",
                name,
                "psql",
                "-U",
                "postgres",
                "-Atc",
                "SELECT current_user, current_setting('server_version');",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        uid = subprocess.run(
            ["docker", "exec", name, "id", "-u"], check=True, capture_output=True, text=True
        ).stdout.strip()
        assert uid == "70" and result.stdout.strip() == "postgres|18.6"
        report.update(verdict="PASS", uid=70, server="18.6", fresh_volume=True, network="none")
        return 0
    finally:
        if started:
            subprocess.run(["docker", "stop", name], check=True, capture_output=True)
        destination = ROOT / "artifacts/session-02/fresh-postgres.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
