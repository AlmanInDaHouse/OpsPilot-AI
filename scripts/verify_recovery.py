"""Real lab outage/restart proof. Operates only the dedicated opspilot-s02 project."""

import importlib.util
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.audit import envelope
from opspilot.adapters.postgres.database import make_engine
from opspilot.adapters.postgres.models import EventRow, StreamRow
from opspilot.audit.domain.envelope import verify_chain

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/compose.yaml")]
API = "http://127.0.0.1:59000"


def snapshot(engine) -> dict:
    with sessionmaker(engine)() as session:
        heads = session.scalars(select(StreamRow).order_by(StreamRow.stream_id)).all()
        streams = []
        for head in heads:
            rows = session.scalars(
                select(EventRow).where(EventRow.stream_id == head.stream_id).order_by(EventRow.seq)
            ).all()
            assert verify_chain(
                [envelope(row, True) for row in rows], head.last_seq, head.last_hash
            )
            streams.append(
                {"stream_id": str(head.stream_id), "seq": head.last_seq, "hash": head.last_hash}
            )
        assert streams, "Provisioned audit streams required"
        return {"streams": streams, "events": sum(row["seq"] for row in streams)}


def compose(*args) -> None:
    subprocess.run([*COMPOSE, *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "recovery_pkce", ROOT / "tests/integration/conftest.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    local = ROOT / "artifacts/local"
    accounts = json.loads((local / "accounts.json").read_text(encoding="utf-8"))
    account = next(row for row in accounts if row["role"] == "auditor")
    tokens = helper.pkce_tokens(account)
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    engine = make_engine((local / "app.dsn").read_text(encoding="utf-8").strip())
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "verdict": "FAIL"}
    try:
        before = snapshot(engine)
        with httpx.Client(timeout=15, trust_env=False) as http:
            assert http.get(API + "/v1/me", headers=headers).status_code == 200
            compose("stop", "postgres")
            try:
                statuses = {
                    path: http.get(API + path, headers=headers).status_code
                    for path in ("/health/live", "/health/ready", "/v1/me")
                }
                assert statuses == {"/health/live": 200, "/health/ready": 503, "/v1/me": 503}
            finally:
                compose("up", "-d", "--wait", "postgres")
            compose("restart", "keycloak", "api")
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    response = http.get(API + "/health/ready")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Readiness did not recover")
            # Obtain a NEW real PKCE token: confirms IdP keys and accounts persisted.
            fresh = helper.pkce_tokens(account)
            me = http.get(
                API + "/v1/me", headers={"Authorization": "Bearer " + fresh["access_token"]}
            )
            assert me.status_code == 200 and me.json()["principal_id"] == account["principal_id"]
        engine.dispose()
        after = snapshot(engine)
        assert before == after
        report.update(
            verdict="PASS",
            during_database_outage=statuses,
            before=before,
            after=after,
            idp_pkce_after_restart="PASS",
            principal_persisted=True,
            limitation="Restart persistence only; not backup/restore or S03 durable workflows",
        )
        return 0
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        engine.dispose()
        destination = ROOT / "artifacts/session-02/recovery.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
