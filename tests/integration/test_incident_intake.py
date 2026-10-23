"""AC03-01/02: actual PostgreSQL18/Keycloak intake, races, rollback and process deaths."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select, text

from opspilot.adapters.postgres.audit import PostgresAppender, PostgresWorkflowAppender, envelope
from opspilot.adapters.postgres.database import PostgresUow
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.adapters.postgres.incidents import PostgresIncidents, PostgresIntakeUow
from opspilot.adapters.postgres.models import EventRow
from opspilot.audit.domain.envelope import verify_chain
from opspilot.entrypoints.api.app import create_app
from opspilot.identity.application.provision import change_identity
from opspilot.identity.domain.principal import Role
from opspilot.incidents.application.create import CreateIncident
from opspilot.incidents.domain.intake import IncidentInput
from opspilot.shared.errors import DependencyUnavailable

from .conftest import IDP_BASE, ISSUER, ROOT
from .test_identity import authorization

pytestmark = pytest.mark.integration
BODY = {"title": "VPN de prueba", "description": "Laboratorio sintético"}
TABLES = (
    "incidents",
    "workflows",
    "workflow_steps",
    "jobs",
    "api_idempotency",
    "audit_events",
    "audit_streams",
)


def headers(tokens, key=None, role="operator"):
    return {**authorization(tokens, role), "Idempotency-Key": str(key or uuid4())}


def counts(pg):
    with pg["engines"]["admin"].connect() as connection:
        return {
            table: connection.execute(text("SELECT count(*) FROM " + table)).scalar_one()
            for table in TABLES
        }


def change(pg, pid, action, role=Role.OPERATOR):
    with PostgresUow(pg["sessions"]["provisioner"]) as uow:
        change_identity(
            IdentityWriter(uow.session),
            PostgresAppender(uow.session),
            pid,
            action,
            role,
            uuid4().hex,
        )
        uow.commit()


def test_complete_intake_replay_hash_conflict_and_redacted_chain(api, pg, tokens, mapped):
    key, before = uuid4(), counts(pg)
    response = api.post("/v1/incidents", json=BODY, headers=headers(tokens, key))
    assert response.status_code == 202
    result = response.json()
    after = counts(pg)
    assert after == {table: value + 1 for table, value in before.items()}
    with pg["engines"]["admin"].connect() as connection:
        incident = (
            connection.execute(
                text("SELECT * FROM incidents WHERE id=:id"), {"id": result["incident_id"]}
            )
            .mappings()
            .one()
        )
        assert (
            incident["creator_id"] == mapped["operator"]
            and incident["status"] == "OPEN"
            and incident["version"] == 1
        )
        workflow = (
            connection.execute(
                text("SELECT * FROM workflows WHERE id=:id"), {"id": result["workflow_id"]}
            )
            .mappings()
            .one()
        )
        assert (
            workflow["state"] == "QUEUED"
            and workflow["version"] == workflow["definition_version"] == 1
        )
        job = (
            connection.execute(
                text("SELECT * FROM jobs WHERE workflow_id=:id"), {"id": result["workflow_id"]}
            )
            .mappings()
            .one()
        )
        assert job["state"] == "READY" and job["owner"] is job["lease_until"] is None
        assert job["fence"] == job["attempts"] == 0
        record = (
            connection.execute(
                text("SELECT * FROM api_idempotency WHERE principal_id=:pid AND key=:key"),
                {"pid": mapped["operator"], "key": key},
            )
            .mappings()
            .one()
        )
        assert record["response_status"] == 202 and record["response_body"] == result
        assert record["request_hash"] == IncidentInput(**BODY).request_hash()
    with pg["sessions"]["admin"]() as session:
        row = session.scalars(
            select(EventRow).where(EventRow.stream_id == UUID(result["incident_id"]))
        ).one()
        event = envelope(row, True)
        assert event["schema_version"] == 2 and event["actor_id"] == str(mapped["operator"])
        assert event["event_type"] == "incident.created" and row.state_snapshot is None
        head = session.execute(
            text("SELECT last_seq,last_hash FROM audit_streams WHERE stream_id=:id"),
            {"id": result["incident_id"]},
        ).one()
        assert verify_chain([event], head.last_seq, head.last_hash)
        public = envelope(row)
        schema = json.loads(
            (ROOT / "contracts/workflow-events-v2.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(public)
        assert "VPN de prueba" not in json.dumps(event)
    # JSON order, escapes, whitespace, header case and new HTTP correlation do not alter the scope.
    replay = api.post(
        "/v1/incidents",
        content=json.dumps(dict(reversed(list(BODY.items()))), ensure_ascii=True),
        headers={**headers(tokens, str(key).upper()), "Content-Type": "application/json"},
    )
    assert replay.status_code == 202 and replay.content == response.content
    assert replay.headers["X-Request-ID"] != response.headers["X-Request-ID"]
    conflict = api.post(
        "/v1/incidents", json={**BODY, "title": "Distinto"}, headers=headers(tokens, key)
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert counts(pg) == after


@pytest.mark.parametrize("role", ["admin", "auditor", "approver", "unmapped"])
def test_other_roles_do_not_create(api, pg, tokens, role):
    before = counts(pg)
    assert (
        api.post("/v1/incidents", json=BODY, headers=headers(tokens, role=role)).status_code == 403
    )
    assert counts(pg) == before


@pytest.mark.parametrize("action", ["revoke", "disable"])
def test_replay_rechecks_current_identity_and_grants(api, pg, tokens, mapped, action):
    key = uuid4()
    assert api.post("/v1/incidents", json=BODY, headers=headers(tokens, key)).status_code == 202
    change(pg, mapped["operator"], action, None if action == "disable" else Role.OPERATOR)
    before = counts(pg)
    try:
        denied = api.post("/v1/incidents", json=BODY, headers=headers(tokens, key))
        assert denied.status_code == 403 and set(denied.json()) == {"code", "request_id"}
        assert counts(pg) == before
    finally:
        if action == "disable":
            with pg["engines"]["admin"].begin() as connection:
                connection.execute(
                    text("UPDATE principals SET enabled=true WHERE id=:id"),
                    {"id": mapped["operator"]},
                )
        else:
            change(pg, mapped["operator"], "grant")


def test_bad_signature_and_expired_real_token(api, tokens):
    token = tokens["operator"]["access_token"]
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    assert (
        api.post(
            "/v1/incidents", json=BODY, headers={"Authorization": "Bearer " + ".".join(parts)}
        ).status_code
        == 401
    )

    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(days=1)

    with patch("jwt.api_jwt.datetime", FutureClock):
        assert api.post("/v1/incidents", json=BODY, headers=headers(tokens)).status_code == 401


@pytest.mark.parametrize("scenario", ["same", "different_body", "independent_keys"])
def test_twenty_simultaneous_requests(api, pg, tokens, scenario, record_property):
    key, before, barrier = uuid4(), counts(pg), threading.Barrier(20)

    def request(index):
        barrier.wait(timeout=10)
        body = BODY if scenario != "different_body" else {**BODY, "title": str(index % 2)}
        return api.post(
            "/v1/incidents",
            json=body,
            headers=headers(tokens, uuid4() if scenario == "independent_keys" else key),
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(request, range(20)))
    accepted = [response for response in responses if response.status_code == 202]
    if scenario == "independent_keys":
        assert len(accepted) == 20 and len({response.text for response in accepted}) == 20
        expected = 20
    else:
        assert len({response.text for response in accepted}) == 1
        assert len(accepted) == (10 if scenario == "different_body" else 20)
        assert all(response.status_code in {202, 409} for response in responses)
        expected = 1
    assert counts(pg) == {table: value + expected for table, value in before.items()}
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": scenario,
                "requests": len(responses),
                "http_202": len(accepted),
                "http_409": sum(response.status_code == 409 for response in responses),
                "rows_added": {table: counts(pg)[table] - value for table, value in before.items()},
                "distinct_accepted_bodies": len({response.text for response in accepted}),
            }
        ),
    )


def test_separate_principals_same_key_and_token_renewal(api, pg, tokens, mapped, accounts):
    from .conftest import pkce_tokens

    change(pg, mapped["admin"], "grant")
    try:
        key = uuid4()
        barrier = threading.Barrier(2)

        def create(role):
            barrier.wait(timeout=5)
            return api.post("/v1/incidents", json=BODY, headers=headers(tokens, key, role))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, other = list(pool.map(create, ("operator", "admin")))
        assert first.status_code == other.status_code == 202 and first.json() != other.json()
        renewed = pkce_tokens(accounts["operator"])["access_token"]
        replay = api.post(
            "/v1/incidents",
            json=BODY,
            headers={"Authorization": "Bearer " + renewed, "Idempotency-Key": str(key)},
        )
        assert replay.status_code == 202 and replay.json() == first.json()
    finally:
        change(pg, mapped["admin"], "revoke")


@contextmanager
def database_failure(pg, table, deferred=False):
    # Actual server-side failures, not mock exceptions. Only the ephemeral test DB is modified.
    assert table in TABLES
    with pg["engines"]["admin"].begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION intake_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled intake failure' USING ERRCODE='23514'; END $$"
        )
        if deferred:
            statement = f"CREATE CONSTRAINT TRIGGER intake_test_failure AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION intake_test_failure()"
        else:
            statement = f"CREATE TRIGGER intake_test_failure BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION intake_test_failure()"
        connection.exec_driver_sql(statement)
    try:
        yield
    finally:
        with pg["engines"]["admin"].begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER intake_test_failure ON {table}")
            connection.exec_driver_sql("DROP FUNCTION intake_test_failure()")


@pytest.mark.parametrize(
    "table", ["incidents", "workflows", "workflow_steps", "jobs", "audit_events", "api_idempotency"]
)
def test_actual_write_failure_rolls_back_every_row(api, pg, tokens, table, record_property):
    before = counts(pg)
    with database_failure(pg, table):
        response = api.post("/v1/incidents", json=BODY, headers=headers(tokens))
        assert response.status_code == 503 and set(response.json()) == {"code", "request_id"}
        assert "controlled intake failure" not in response.text
    assert counts(pg) == before
    record_property(
        "observation",
        json.dumps(
            {"fault": table, "status": response.status_code, "before": before, "after": counts(pg)}
        ),
    )


def test_actual_deferred_commit_failure_has_no_accepted_response_or_rows(
    api, pg, tokens, record_property
):
    key, before, committed = uuid4(), counts(pg), []
    original_commit = PostgresIntakeUow.commit

    def observe_commit(self):
        # All writes exist in this transaction before PostgreSQL rejects COMMIT.
        assert (
            self.session.execute(
                text("SELECT count(*) FROM api_idempotency WHERE key=:key"), {"key": key}
            ).scalar_one()
            == 1
        )
        committed.append("attempt")
        return original_commit(self)

    with (
        database_failure(pg, "api_idempotency", deferred=True),
        patch.object(PostgresIntakeUow, "commit", observe_commit),
    ):
        response = api.post("/v1/incidents", json=BODY, headers=headers(tokens, key))
        assert response.status_code == 503 and committed == ["attempt"]
    assert counts(pg) == before
    record_property(
        "observation",
        json.dumps(
            {
                "fault": "deferred_constraint_at_actual_commit",
                "status": response.status_code,
                "commit_attempts": len(committed),
                "before": before,
                "after": counts(pg),
            }
        ),
    )
    assert api.post("/v1/incidents", json=BODY, headers=headers(tokens, key)).status_code == 202


def test_no_success_visible_before_commit(api, pg, tokens):
    arrived, release = threading.Event(), threading.Event()
    before = counts(pg)
    commit = PostgresIntakeUow.commit

    def pause(self):
        arrived.set()
        assert release.wait(5)
        commit(self)

    with (
        patch.object(PostgresIntakeUow, "commit", pause),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        pending = pool.submit(api.post, "/v1/incidents", json=BODY, headers=headers(tokens))
        try:
            assert arrived.wait(5)
            assert not pending.done() and counts(pg) == before
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 202


def test_two_transactions_forced_to_lose_unique_race(pg, mapped):
    barrier = threading.Barrier(2)
    find = PostgresIncidents.find
    key, before, first_reads = uuid4(), counts(pg), set()

    def simultaneous_find(self, pid, request_key):
        result = find(self, pid, request_key)
        if result is None and threading.get_ident() not in first_reads:
            first_reads.add(threading.get_ident())
            barrier.wait(timeout=5)
        return result

    service = CreateIncident(lambda: PostgresIntakeUow(pg["sessions"]["app"]))
    with (
        patch.object(PostgresIncidents, "find", simultaneous_find),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = list(
            pool.map(
                lambda _: service.execute(
                    mapped["operator"], key, IncidentInput(**BODY), uuid4().hex
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert counts(pg) == {table: value + 1 for table, value in before.items()}


def process_line(process):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(process.stdout.readline)
        try:
            line = pending.result(timeout=15)
            assert line, "Process ended before reporting its synchronization point"
            return json.loads(line)
        except Exception:
            process.kill()
            raise


@contextmanager
def child(pg, mode, pid=None, key=None, tmp_path=None):
    env = {
        **os.environ,
        "OPSPILOT_TEST_DSN": pg["engines"]["app"].url.render_as_string(hide_password=False),
        "OPSPILOT_TEST_PRINCIPAL": str(pid),
        "OPSPILOT_TEST_KEY": str(key),
    }
    if mode.startswith("serve"):
        path = tmp_path / (uuid4().hex + ".dsn")
        path.write_text(env["OPSPILOT_TEST_DSN"], encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
        env.update(
            {
                "OPSPILOT_ENVIRONMENT": "lab",
                "OPSPILOT_DATABASE_DSN_FILE": str(path),
                "OPSPILOT_OIDC_ISSUER": ISSUER,
                "OPSPILOT_OIDC_AUDIENCE": "opspilot-api",
                "OPSPILOT_OIDC_JWKS_URL": IDP_BASE
                + "/realms/opspilot/protocol/openid-connect/certs",
            }
        )
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("intake_process.py")), mode],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
        if mode.startswith("serve"):
            path.unlink()


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_process_death_at_actual_commit_boundaries(pg, mapped, phase, record_property):
    key, before = uuid4(), counts(pg)
    with child(pg, phase, mapped["operator"], key) as process:
        assert process_line(process) == {"phase": phase}
        assert counts(pg) == {
            table: value + (phase == "after_commit") for table, value in before.items()
        }
        process.kill()
        process.wait(timeout=10)
        assert process.returncode != 0
    service = CreateIncident(lambda: PostgresIntakeUow(pg["sessions"]["app"]))
    result = service.execute(
        mapped["operator"], key, IncidentInput("Proceso", "Laboratorio sintético"), uuid4().hex
    )
    assert (
        service.execute(
            mapped["operator"], key, IncidentInput("Proceso", "Laboratorio sintético"), uuid4().hex
        )
        == result
    )
    assert counts(pg) == {table: value + 1 for table, value in before.items()}
    record_property(
        "observation",
        json.dumps(
            {
                "phase": phase,
                "exit_code": process.returncode,
                "before": before,
                "after_replay": counts(pg),
            }
        ),
    )


def wait_ready(url):
    deadline = time.monotonic() + 15
    with httpx.Client(trust_env=False, timeout=2) as http:
        while time.monotonic() < deadline:
            try:
                if http.get(url + "/health/ready").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            threading.Event().wait(0.05)
    pytest.fail("Real API process did not become ready")


def test_two_real_api_processes_and_restart_recover_exact_response(
    pg, mapped, tokens, tmp_path, record_property
):
    key, before = uuid4(), counts(pg)
    with child(pg, "serve", tmp_path=tmp_path) as one, child(pg, "serve", tmp_path=tmp_path) as two:
        urls = ["http://127.0.0.1:" + str(process_line(proc)["port"]) for proc in (one, two)]
        for url in urls:
            wait_ready(url)
        barrier = threading.Barrier(20)

        def request(index):
            barrier.wait(timeout=10)
            with httpx.Client(trust_env=False, timeout=15) as http:
                return http.post(
                    urls[index % 2] + "/v1/incidents", headers=headers(tokens, key), json=BODY
                )

        with ThreadPoolExecutor(max_workers=20) as pool:
            responses = list(pool.map(request, range(20)))
        assert all(response.status_code == 202 for response in responses)
        assert len({response.content for response in responses}) == 1
        original = responses[0].content
    # Both processes and their memory are gone. The new process only has PostgreSQL state.
    with child(pg, "serve", tmp_path=tmp_path) as restarted:
        url = "http://127.0.0.1:" + str(process_line(restarted)["port"])
        wait_ready(url)
        with httpx.Client(trust_env=False, timeout=5) as http:
            replay = http.post(url + "/v1/incidents", headers=headers(tokens, key), json=BODY)
        assert replay.status_code == 202 and replay.content == original
    assert counts(pg) == {table: value + 1 for table, value in before.items()}
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "two_api_processes_then_restart",
                "requests": len(responses),
                "http_202": sum(response.status_code == 202 for response in responses),
                "distinct_accepted_bodies": len({response.text for response in responses}),
                "restart_replay_status": replay.status_code,
                "restart_replay_exact": replay.content == original,
                "before": before,
                "after": counts(pg),
            }
        ),
    )


@pytest.mark.parametrize("mode", ["serve_before_commit", "serve_after_commit"])
def test_http_connection_lost_on_process_kill(api, pg, tokens, tmp_path, mode, record_property):
    key, before = uuid4(), counts(pg)
    with child(pg, mode, tmp_path=tmp_path) as process:
        url = "http://127.0.0.1:" + str(process_line(process)["port"])
        wait_ready(url)
        with ThreadPoolExecutor(max_workers=1) as pool:

            def send():
                with httpx.Client(trust_env=False, timeout=10) as http:
                    return http.post(url + "/v1/incidents", headers=headers(tokens, key), json=BODY)

            pending = pool.submit(send)
            assert process_line(process) == {"phase": mode}
            assert not pending.done()
            assert counts(pg) == {
                table: value + (mode == "serve_after_commit") for table, value in before.items()
            }
            process.kill()
            process.wait(timeout=10)
            with pytest.raises(httpx.TransportError):
                pending.result(timeout=10)
    replay = api.post("/v1/incidents", json=BODY, headers=headers(tokens, key))
    assert replay.status_code == 202
    assert counts(pg) == {table: value + 1 for table, value in before.items()}
    record_property(
        "observation",
        json.dumps(
            {
                "phase": mode,
                "exit_code": process.returncode,
                "response_before_kill": False,
                "transport_error": True,
                "replay_status": replay.status_code,
                "before": before,
                "after_replay": counts(pg),
            }
        ),
    )


@pytest.mark.parametrize("invalid", ["payload", "type", "version", "actor"])
def test_real_appender_rejects_invalid_creation_atomically(api, pg, tokens, invalid):
    original = PostgresWorkflowAppender.append
    before = counts(pg)

    def changed(self, stream, kind, actor, trace, payload):
        if invalid == "payload":
            payload = {
                **payload,
                "secret": "forbidden-fixture",  # pragma: allowlist secret (closed audit schema rejection fixture)
            }
        elif invalid == "type":
            kind = "unapproved.event"
        elif invalid == "version":
            payload = {**payload, "aggregate_version": 2}
        else:
            actor = uuid4()
        return original(self, stream, kind, actor, trace, payload)

    with patch.object(PostgresWorkflowAppender, "append", changed):
        assert api.post("/v1/incidents", json=BODY, headers=headers(tokens)).status_code == 503
    assert counts(pg) == before


def test_actual_foreign_key_error_is_not_replay(api, pg, tokens):
    original, before = PostgresIncidents.create, counts(pg)

    def invalid_creator(self, principal, body):
        return original(self, uuid4(), body)

    with patch.object(PostgresIncidents, "create", invalid_creator):
        assert api.post("/v1/incidents", json=BODY, headers=headers(tokens)).status_code == 503
    assert counts(pg) == before


def test_unique_lock_wait_timeout_is_bounded_and_fail_closed(pg, mapped):
    service = CreateIncident(lambda: PostgresIntakeUow(pg["sessions"]["app"]))
    key, before = uuid4(), counts(pg)
    with PostgresIntakeUow(pg["sessions"]["app"]) as winner:
        repository = winner.incidents
        result = repository.create(mapped["operator"], IncidentInput(**BODY))
        repository.audit(mapped["operator"], result, uuid4().hex)
        repository.remember(mapped["operator"], key, IncidentInput(**BODY).request_hash(), result)

        class ShortWait(PostgresIntakeUow):
            def __enter__(self):
                super().__enter__()
                self.session.execute(text("SET LOCAL lock_timeout='100ms'"))
                return self

        with pytest.raises(DependencyUnavailable):
            CreateIncident(lambda: ShortWait(pg["sessions"]["app"])).execute(
                mapped["operator"], key, IncidentInput(**BODY), uuid4().hex
            )
        # No provisional success or data is externally visible while the winner is uncommitted.
        assert counts(pg) == before
        winner.commit()
    assert service.execute(mapped["operator"], key, IncidentInput(**BODY), uuid4().hex) == result
    assert counts(pg) == {table: value + 1 for table, value in before.items()}


def test_required_cold_jwks_unavailable_fails_closed(pg, tokens, tmp_path, monkeypatch):
    dsnfile = tmp_path / "intake-app.dsn"
    dsnfile.write_text(
        pg["engines"]["app"].url.render_as_string(hide_password=False), encoding="utf-8"
    )
    with socket.socket() as unavailable:
        # Reserve an actual local port with no listening service: connection refused.
        unavailable.bind(("127.0.0.1", 0))
        for name, value in {
            "ENVIRONMENT": "lab",
            "DATABASE_DSN_FILE": str(dsnfile),
            "OIDC_ISSUER": ISSUER,
            "OIDC_AUDIENCE": "opspilot-api",
            "OIDC_JWKS_URL": "http://127.0.0.1:" + str(unavailable.getsockname()[1]) + "/jwks",
        }.items():
            monkeypatch.setenv("OPSPILOT_" + name, value)
        before = counts(pg)
        with TestClient(create_app()) as client:
            response = client.post("/v1/incidents", json=BODY, headers=headers(tokens))
        assert response.status_code == 503 and response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
        assert counts(pg) == before


def test_waiting_unique_insert_succeeds_when_first_transaction_aborts(pg, mapped):
    key, before, blocked = uuid4(), counts(pg), threading.Event()
    backend = []

    class WaitingTransaction(PostgresIntakeUow):
        def __enter__(self):
            super().__enter__()
            backend.append(self.session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            blocked.set()
            return self

    with ThreadPoolExecutor(max_workers=1) as pool:
        with PostgresIntakeUow(pg["sessions"]["app"]) as aborted:
            result = aborted.incidents.create(mapped["operator"], IncidentInput(**BODY))
            aborted.incidents.audit(mapped["operator"], result, uuid4().hex)
            aborted.incidents.remember(
                mapped["operator"], key, IncidentInput(**BODY).request_hash(), result
            )
            pending = pool.submit(
                CreateIncident(lambda: WaitingTransaction(pg["sessions"]["app"])).execute,
                mapped["operator"],
                key,
                IncidentInput(**BODY),
                uuid4().hex,
            )
            assert blocked.wait(5)
            deadline, seen_lock = time.monotonic() + 3, False
            with (
                pg["engines"]["admin"]
                .connect()
                .execution_options(isolation_level="AUTOCOMMIT") as connection
            ):
                while time.monotonic() < deadline:
                    waiting = connection.execute(
                        text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                        {"pid": backend[0]},
                    ).scalar_one()
                    if waiting == "Lock":
                        seen_lock = True
                        break
                    threading.Event().wait(0.01)
            assert seen_lock and not pending.done()
            assert counts(pg) == before
            # No commit: exiting now rolls back the first, complete provisional intake.
        accepted = pending.result(timeout=10)
    assert accepted != result
    assert counts(pg) == {table: value + 1 for table, value in before.items()}
