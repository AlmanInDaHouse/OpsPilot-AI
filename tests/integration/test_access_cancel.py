"""T03-04 real PG18/Keycloak authorization, CAS, locks and commit failures."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from opspilot.adapters.postgres.models import EventRow
from opspilot.adapters.postgres.workflows import PostgresAccessUow, PostgresWorkflows
from opspilot.audit.domain.envelope import canonical_bytes, event_hash, verify_chain
from opspilot.identity.domain.principal import Role
from opspilot.workflows.domain.access import WorkflowTag

from .conftest import IDP_BASE, ISSUER, LOCAL, ROOT, pkce_tokens
from .test_identity import authorization
from .test_incident_intake import BODY, change, headers, process_line, wait_ready
from .test_workflow_persistence import evidence, read, seed, transition

pytestmark = pytest.mark.integration
CONTRACT = json.loads((ROOT / "contracts/workflows.openapi.json").read_text(encoding="utf-8"))
V2 = json.loads((ROOT / "contracts/workflow-events-v2.schema.json").read_text(encoding="utf-8"))


def accepted(api, tokens):
    response = api.post("/v1/incidents", json=BODY, headers=headers(tokens))
    assert response.status_code == 202
    return response.json()


def tag(wid, version=1):
    return WorkflowTag(UUID(str(wid)), version).wire()


def cancel(api, tokens, wid, version=1, role="operator", value=None):
    return api.post(
        f"/v1/workflows/{wid}/cancel",
        headers={
            **authorization(tokens, role),
            "If-Match": value if value is not None else tag(wid, version),
        },
    )


def snapshot(pg, wid):
    with pg["engines"]["admin"].connect() as conn:
        workflow = dict(
            conn.execute(text("SELECT * FROM workflows WHERE id=:id"), {"id": wid}).mappings().one()
        )
        jobs = [
            dict(row)
            for row in conn.execute(
                text("SELECT * FROM jobs WHERE workflow_id=:id ORDER BY id"), {"id": wid}
            ).mappings()
        ]
        events = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE stream_id=:id"), {"id": wid}
        ).scalar_one()
    return {"workflow": workflow, "jobs": jobs, "events": events}


def conform(response, schema):
    spec = {**CONTRACT["components"]["schemas"][schema], "$defs": CONTRACT["components"]["schemas"]}
    # Resolve the independent contract's internal refs using the existing recursive helper.
    from tests.contract.test_api import deref

    Draft202012Validator(deref(spec, CONTRACT), format_checker=FormatChecker()).validate(
        response.json()
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert UUID(response.headers["X-Request-ID"])


def test_read_cancel_replay_and_closed_audit(api, pg, tokens, mapped, record_property):
    ids = accepted(api, tokens)
    wid = ids["workflow_id"]
    incident = api.get("/v1/incidents/" + ids["incident_id"], headers=authorization(tokens))
    conform(incident, "Incident")
    assert incident.json() == {
        **ids,
        "creator_id": str(mapped["operator"]),
        **BODY,
        "status": "OPEN",
        "version": 1,
    }
    workflow = api.get("/v1/workflows/" + wid, headers=authorization(tokens))
    conform(workflow, "Workflow")
    assert workflow.headers["ETag"] == tag(wid)
    assert workflow.json()["evidence"] == []
    before = snapshot(pg, wid)
    response = cancel(api, tokens, wid)
    assert response.status_code == 202
    conform(response, "CancelAccepted")
    assert response.headers["ETag"] == tag(wid, 2)
    after = snapshot(pg, wid)
    assert after["workflow"]["state"] == "CANCELLED" and after["workflow"]["version"] == 2
    assert after["events"] == 1
    assert after["jobs"][0]["state"] == "DEAD" and after["jobs"][0]["fence"] == 1
    assert after["jobs"][0]["owner"] is after["jobs"][0]["lease_until"] is None
    assert cancel(api, tokens, wid).json()["code"] == "VERSION_CONFLICT"
    replay = cancel(api, tokens, wid, 2)
    assert replay.status_code == 202 and replay.content == response.content
    assert snapshot(pg, wid) == after
    assert (
        api.get("/v1/incidents/" + ids["incident_id"], headers=authorization(tokens)).content
        == incident.content
    )
    events, head = read(pg, UUID(wid))
    assert verify_chain(events, head.last_seq, head.last_hash)
    public = {key: value for key, value in events[0].items() if key not in {"hash", "prev_hash"}}
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(public)
    assert public["actor_id"] == str(mapped["operator"])
    assert public["payload"]["reason_code"] == "CANCELLED_BY_OPERATOR"
    with pg["sessions"]["app"]() as session:
        row = session.scalars(select(EventRow).where(EventRow.stream_id == UUID(wid))).one()
        assert (
            hashlib.sha256(canonical_bytes(row.state_snapshot)).hexdigest()
            == row.payload["snapshot_hash"]
        )
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "cancel_replay",
                "before": before,
                "after": after,
                "http": [response.status_code, replay.status_code],
                "etag": response.headers["ETag"],
            },
            default=str,
        ),
    )


@pytest.mark.parametrize("role", ["operator", "auditor", "admin", "approver", "unmapped"])
def test_real_route_role_matrix(api, tokens, role):
    ids = accepted(api, tokens)
    for kind in ("incident", "workflow"):
        response = api.get(f"/v1/{kind}s/{ids[kind + '_id']}", headers=authorization(tokens, role))
        assert response.status_code == (200 if role in {"operator", "auditor"} else 403)
    assert cancel(api, tokens, ids["workflow_id"], role=role).status_code == (
        202 if role == "operator" else 403
    )


def test_hidden_missing_and_other_entity_tag_never_leak(api, pg, tokens):
    foreign = seed(pg)
    for kind in ("incident", "workflow"):
        responses = [
            api.get(f"/v1/{kind}s/{rid}", headers=authorization(tokens))
            for rid in (foreign[kind], uuid4())
        ]
        assert all(r.status_code == 404 and r.json()["code"] == "NOT_FOUND" for r in responses)
        assert all(
            set(r.json()) == {"code", "request_id"} and "ETag" not in r.headers for r in responses
        )
    for rid in (foreign["workflow"], uuid4()):
        r = cancel(api, tokens, rid, value=tag(uuid4(), 99))
        assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    own = accepted(api, tokens)
    assert (
        cancel(api, tokens, own["workflow_id"], value=tag(foreign["workflow"])).json()["code"]
        == "VERSION_CONFLICT"
    )
    assert (
        api.get(
            "/v1/audit-events",
            params={"stream_id": foreign["workflow"]},
            headers=authorization(tokens),
        ).status_code
        == 403
    )
    assert cancel(api, tokens, own["workflow_id"], role="approver").status_code == 403


@pytest.mark.parametrize("action", ["revoke", "disable"])
@pytest.mark.parametrize("role", ["operator", "auditor"])
def test_revocation_before_reads_and_cancel(api, pg, tokens, mapped, action, role):
    ids = accepted(api, tokens)

    change(pg, mapped[role], action, None if action == "disable" else Role(role))
    try:
        for kind in ("incident", "workflow"):
            assert (
                api.get(
                    f"/v1/{kind}s/{ids[kind + '_id']}", headers=authorization(tokens, role)
                ).status_code
                == 403
            )
        assert cancel(api, tokens, ids["workflow_id"], role=role).status_code == 403
        assert snapshot(pg, ids["workflow_id"])["workflow"]["version"] == 1
    finally:
        if action == "disable":
            with pg["engines"]["admin"].begin() as conn:
                conn.execute(
                    text("UPDATE principals SET enabled=true WHERE id=:id"), {"id": mapped[role]}
                )
        else:
            change(pg, mapped[role], "grant", Role(role))


@pytest.mark.parametrize(
    "value",
    [
        None,
        "*",
        'W/"wf-{id}-v1"',
        '"wf-{id}-v01"',
        '"wf-{id}-v0"',
        '"wf-{id}-v9223372036854775808"',
        '"wf-{id}-v1" ',
        ' "wf-{id}-v1"',
        '"wf-{id}-v1", "wf-{id}-v2"',
        '"wf-{id}-v-1"',
    ],
)
def test_real_invalid_match_headers(api, pg, tokens, value):
    ids = accepted(api, tokens)
    wid = ids["workflow_id"]
    hdr = authorization(tokens)
    if value is not None:
        hdr["If-Match"] = value.replace("{id}", wid)
    before = snapshot(pg, wid)
    response = api.post(f"/v1/workflows/{wid}/cancel", headers=hdr)
    assert response.status_code == 422 and response.json()["code"] == "INVALID_REQUEST"
    assert snapshot(pg, wid) == before


@pytest.mark.parametrize("route", ["incident", "workflow", "cancel"])
def test_transport_and_auth_negatives_on_real_routes(api, pg, tokens, route):
    ids = accepted(api, tokens)
    path = (
        "/v1/incidents/" + ids["incident_id"]
        if route == "incident"
        else "/v1/workflows/" + ids["workflow_id"] + ("/cancel" if route == "cancel" else "")
    )
    method = "POST" if route == "cancel" else "GET"
    hdr = {**authorization(tokens), "If-Match": tag(ids["workflow_id"])}
    before = snapshot(pg, ids["workflow_id"])
    for bad in (
        {},
        {"Authorization": "Bearer invalid"},
        {"Authorization": "Bearer " + tokens["operator"]["id_token"]},
    ):
        r = api.request(method, path, headers=bad)
        assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"
        conform(r, "Error")
    for kwargs in ({"content": b"{}"}, {"params": {"unexpected": "1"}}):
        assert api.request(method, path, headers=hdr, **kwargs).status_code == 422
    duplicate = [*hdr.items(), ("If-Match", tag(ids["workflow_id"]))]
    assert api.request(method, path, headers=duplicate).status_code == 422
    # If-None-Match is not implemented as a conditional GET.
    if route != "cancel":
        assert api.get(path, headers={**hdr, "If-None-Match": hdr["If-Match"]}).status_code == 200
    assert snapshot(pg, ids["workflow_id"]) == before


@pytest.mark.parametrize("requests", [2, 20])
def test_simultaneous_cancel_has_one_winner(api, pg, tokens, requests, record_property):
    wid = accepted(api, tokens)["workflow_id"]
    before = snapshot(pg, wid)
    barrier = threading.Barrier(requests)

    def send(_):
        barrier.wait(timeout=10)
        return cancel(api, tokens, wid)

    with ThreadPoolExecutor(max_workers=requests) as pool:
        responses = list(pool.map(send, range(requests)))
    codes = [r.status_code for r in responses]
    assert codes.count(202) == 1 and codes.count(409) == requests - 1
    assert all(r.json()["code"] == "VERSION_CONFLICT" for r in responses if r.status_code == 409)
    after = snapshot(pg, wid)
    assert (
        after["workflow"]["version"] == 2
        and after["events"] == 1
        and after["jobs"][0]["state"] == "DEAD"
    )
    record_property(
        "observation",
        json.dumps(
            {"scenario": "simultaneous_cancel", "http": codes, "before": before, "after": after},
            default=str,
        ),
    )


def wait_for_lock(pg, pending, query):
    deadline = time.monotonic() + 4
    with pg["engines"]["admin"].connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        while time.monotonic() < deadline:
            rows = conn.execute(
                text(
                    "SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE :query"
                ),
                {"query": query},
            ).all()
            if rows:
                assert not pending.done()
                return
            threading.Event().wait(0.01)
    pytest.fail("Expected PostgreSQL lock wait was not observed")


@pytest.mark.parametrize("target", ["workflow", "job", "audit"])
def test_real_lock_order_and_no_202_before_commit(api, pg, tokens, target, record_property):
    ids = accepted(api, tokens)
    wid = ids["workflow_id"]
    # Create a workflow stream so the appender must contend on an existing head.
    if target == "audit":
        with pg["engines"]["admin"].begin() as conn:
            conn.execute(
                text("INSERT INTO audit_streams VALUES(:id,0,repeat('0',64))"), {"id": wid}
            )
    before = snapshot(pg, wid)
    table, key = {
        "workflow": ("workflows", "id"),
        "job": ("jobs", "workflow_id"),
        "audit": ("audit_streams", "stream_id"),
    }[target]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg["engines"]["admin"].begin() as blocker:
            blocker.execute(
                text(f"SELECT * FROM {table} WHERE {key}=:id FOR UPDATE"), {"id": wid}
            ).all()
            pending = pool.submit(cancel, api, tokens, wid)
            wait_for_lock(
                pg,
                pending,
                {
                    "workflow": "SELECT id AS workflow_id%",
                    "job": "SELECT id FROM jobs%",
                    "audit": "SELECT audit_append_v2%",
                }[target],
            )
            assert snapshot(pg, wid) == before
            # No transaction can observe a half-cancelled workflow while blocked.
            if target == "job":
                blocker.execute(
                    text(
                        "UPDATE jobs SET state='LEASED',owner=:owner,lease_until=clock_timestamp()+interval '60 seconds',fence=3 WHERE workflow_id=:id"
                    ),
                    {"owner": uuid4(), "id": wid},
                )
        response = pending.result(timeout=10)
    assert response.status_code == 202
    after = snapshot(pg, wid)
    assert after["events"] == 1 and after["jobs"][0]["state"] == "DEAD"
    if target == "job":
        assert after["jobs"][0]["fence"] == 4
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "locked_" + target,
                "db_lock_observed": True,
                "http": response.status_code,
                "before": before,
                "after": after,
            },
            default=str,
        ),
    )


@pytest.mark.parametrize("race", ["version", "revoke", "disable"])
def test_lock_wait_rechecks_version_and_permissions(api, pg, tokens, mapped, race):
    wid = accepted(api, tokens)["workflow_id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg["engines"]["admin"].begin() as blocker:
            blocker.execute(text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"), {"id": wid})
            pending = pool.submit(cancel, api, tokens, wid)
            wait_for_lock(pg, pending, "SELECT id AS workflow_id%")
            if race == "version":
                blocker.execute(
                    text("UPDATE workflows SET version=version+1 WHERE id=:id"), {"id": wid}
                )
            else:
                change(pg, mapped["operator"], race, None if race == "disable" else Role.OPERATOR)
        try:
            response = pending.result(timeout=10)
            assert response.status_code == (409 if race == "version" else 403)
            assert response.json()["code"] == (
                "VERSION_CONFLICT" if race == "version" else "FORBIDDEN"
            )
            after = snapshot(pg, wid)
            assert after["workflow"]["state"] == "QUEUED" and after["events"] == 0
        finally:
            if race == "disable":
                with pg["engines"]["admin"].begin() as conn:
                    conn.execute(
                        text("UPDATE principals SET enabled=true WHERE id=:id"),
                        {"id": mapped["operator"]},
                    )
            elif race == "revoke":
                change(pg, mapped["operator"], "grant", Role.OPERATOR)


@pytest.mark.parametrize("target", ["workflows", "jobs", "audit_events", "commit"])
def test_real_sql_failure_rolls_back_all_cancel_writes(api, pg, tokens, target, record_property):
    wid = accepted(api, tokens)["workflow_id"]
    before = snapshot(pg, wid)
    table = "audit_events" if target == "commit" else target
    operation = "INSERT" if table == "audit_events" else "UPDATE"
    with pg["engines"]["admin"].begin() as conn:
        conn.exec_driver_sql(
            "CREATE FUNCTION cancel_failure_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST cancellation rollback'; END $$"
        )
        conn.exec_driver_sql(
            f"CREATE {'CONSTRAINT ' if target == 'commit' else ''}TRIGGER cancel_failure_test AFTER {operation} ON {table} {'DEFERRABLE INITIALLY DEFERRED' if target == 'commit' else ''} FOR EACH ROW EXECUTE FUNCTION cancel_failure_test()"
        )
    try:
        response = cancel(api, tokens, wid)
        assert response.status_code == 503 and response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
        assert snapshot(pg, wid) == before
    finally:
        with pg["engines"]["admin"].begin() as conn:
            conn.exec_driver_sql(f"DROP TRIGGER cancel_failure_test ON {table}")
            conn.exec_driver_sql("DROP FUNCTION cancel_failure_test()")
    assert cancel(api, tokens, wid).status_code == 202
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "sql_failure_" + target,
                "rollback_exact": True,
                "before": before,
                "http": response.status_code,
            },
            default=str,
        ),
    )


def test_lock_timeout_is_503_and_rolls_back(api, pg, tokens, record_property):
    wid = accepted(api, tokens)["workflow_id"]
    before = snapshot(pg, wid)
    original = PostgresAccessUow.__enter__

    def short_wait(self):
        result = original(self)
        self.session.execute(text("SET LOCAL lock_timeout='100ms'"))
        return result

    with pg["engines"]["admin"].begin() as conn:
        conn.execute(text("SELECT id FROM jobs WHERE workflow_id=:id FOR UPDATE"), {"id": wid})
        with patch.object(PostgresAccessUow, "__enter__", short_wait):
            response = cancel(api, tokens, wid)
        assert response.status_code == 503 and snapshot(pg, wid) == before
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "lock_timeout",
                "http": response.status_code,
                "rollback_exact": True,
                "before": before,
            },
            default=str,
        ),
    )


def test_leased_job_fence_and_sql_no_resurrection(api, pg, tokens):
    wid = accepted(api, tokens)["workflow_id"]
    owner = uuid4()
    with pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text(
                "UPDATE jobs SET state='LEASED',owner=:owner,lease_until=clock_timestamp()+interval '60 seconds',fence=7 WHERE workflow_id=:id"
            ),
            {"id": wid, "owner": owner},
        )
    assert cancel(api, tokens, wid).status_code == 202
    after = snapshot(pg, wid)
    assert after["jobs"][0]["fence"] == 8 and after["jobs"][0]["state"] == "DEAD"
    with pg["engines"]["worker"].begin() as conn:
        # A representative SQL predicate, not an implemented worker completion handler.
        assert (
            conn.execute(
                text(
                    "UPDATE jobs SET state='DONE',owner=NULL,lease_until=NULL WHERE workflow_id=:id AND owner=:owner AND fence=7 AND lease_until>clock_timestamp()"
                ),
                {"id": wid, "owner": owner},
            ).rowcount
            == 0
        )
    with pytest.raises(DBAPIError), pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text("UPDATE workflows SET state='INVESTIGATING',version=version+1 WHERE id=:id"),
            {"id": wid},
        )
    assert snapshot(pg, wid) == after


def test_evidence_projection_and_cancel_preserves_evidence(api, pg, tokens, mapped):
    ids = seed(pg, mapped["operator"])
    transition(pg, ids)
    eid = evidence(pg, ids)
    transition(pg, ids, "INVESTIGATING", "NEEDS_OPERATOR", "LOCAL_SNAPSHOT_RECORDED", [str(eid)])
    response = api.get(f"/v1/workflows/{ids['workflow']}", headers=authorization(tokens))
    conform(response, "Workflow")
    assert set(response.json()["evidence"][0]) == {
        "evidence_id",
        "kind",
        "content_hash",
        "observed_at",
        "collector_id",
        "source_ref",
        "independence_role",
    }
    assert cancel(api, tokens, ids["workflow"], 3).status_code == 202
    assert (
        api.get(f"/v1/workflows/{ids['workflow']}", headers=authorization(tokens)).json()[
            "evidence"
        ]
        == response.json()["evidence"]
    )


@pytest.mark.parametrize("state", ["EXECUTING", "VERIFYING", "OUTCOME_UNKNOWN"])
def test_future_ambiguous_state_only_persists_intention_once(api, pg, tokens, mapped, state):
    ids = seed(pg, mapped["operator"], state=state)
    response = cancel(api, tokens, ids["workflow"])
    assert response.status_code == 202 and response.json()["state"] == state
    after = snapshot(pg, ids["workflow"])
    assert after["workflow"]["version"] == 2 and after["jobs"][0]["state"] == "DEAD"
    events, head = read(pg, ids["workflow"])
    assert events[0]["event_type"] == "workflow.cancel_requested"
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(
        {k: v for k, v in events[0].items() if k not in {"hash", "prev_hash"}}
    )
    assert verify_chain(events, head.last_seq, head.last_hash)
    assert cancel(api, tokens, ids["workflow"], 2).content == response.content
    assert cancel(api, tokens, ids["workflow"]).status_code == 409
    assert snapshot(pg, ids["workflow"]) == after


@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED"])
def test_terminal_current_and_stale_etag_order(api, pg, tokens, mapped, state):
    ids = seed(pg, mapped["operator"], state=state)
    before = snapshot(pg, ids["workflow"])
    assert cancel(api, tokens, ids["workflow"]).json()["code"] == "TERMINAL_WORKFLOW"
    assert cancel(api, tokens, ids["workflow"], 2).json()["code"] == "VERSION_CONFLICT"
    assert snapshot(pg, ids["workflow"]) == before


@contextmanager
def api_process(pg, tmp_path, mode="serve"):
    path = tmp_path / (uuid4().hex + ".dsn")
    path.write_text(
        pg["engines"]["app"].url.render_as_string(hide_password=False), encoding="utf-8"
    )
    if os.name != "nt":
        path.chmod(0o600)
    env = {
        **os.environ,
        "OPSPILOT_ENVIRONMENT": "lab",
        "OPSPILOT_DATABASE_DSN_FILE": str(path),
        "OPSPILOT_OIDC_ISSUER": ISSUER,
        "OPSPILOT_OIDC_AUDIENCE": "opspilot-api",
        "OPSPILOT_OIDC_JWKS_URL": IDP_BASE + "/realms/opspilot/protocol/openid-connect/certs",
    }
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("cancel_process.py")), mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    )
    try:
        url = "http://127.0.0.1:" + str(process_line(process)["port"])
        wait_ready(url)
        yield process, url
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdin.close()
        process.stdout.close()
        path.unlink()


@pytest.mark.parametrize("mode", ["before_commit", "after_commit"])
def test_http_crash_at_cancel_commit_boundary(api, pg, tokens, tmp_path, mode, record_property):
    wid = accepted(api, tokens)["workflow_id"]
    before = snapshot(pg, wid)
    with (
        api_process(pg, tmp_path, mode) as (process, url),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        # An HTTP client with the process origin reaches the production composition.
        def send_to_process():
            with httpx.Client(base_url=url, trust_env=False, timeout=12) as http:
                return cancel(http, tokens, wid)

        pending = pool.submit(send_to_process)
        assert process_line(process) == {"phase": mode}
        during = snapshot(pg, wid)
        assert not pending.done()
        assert (
            during == before
            if mode == "before_commit"
            else during["workflow"]["state"] == "CANCELLED"
        )
        process.kill()
        process.wait(timeout=10)
        with pytest.raises(httpx.TransportError):
            pending.result(timeout=10)
        assert process.returncode != 0
    after = snapshot(pg, wid)
    assert after == before if mode == "before_commit" else after == during
    current = 1 if mode == "before_commit" else 2
    response = cancel(api, tokens, wid, current)
    assert response.status_code == 202
    stable = snapshot(pg, wid)
    assert stable["workflow"]["version"] == 2 and stable["events"] == 1
    assert cancel(api, tokens, wid, 2).content == response.content
    assert snapshot(pg, wid) == stable
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "http_crash_" + mode,
                "exit_code": process.returncode,
                "http_before_kill": None,
                "transport_error": True,
                "before": before,
                "during": during,
                "after_retry": stable,
                "retry_http": response.status_code,
            },
            default=str,
        ),
    )


@pytest.mark.parametrize("state", ["DONE", "DEAD"])
def test_finished_jobs_are_not_rewritten(api, pg, tokens, state):
    wid = accepted(api, tokens)["workflow_id"]
    with pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text("UPDATE jobs SET state=:state WHERE workflow_id=:id"), {"id": wid, "state": state}
        )
    jobs = snapshot(pg, wid)["jobs"]
    assert cancel(api, tokens, wid).status_code == 202
    assert snapshot(pg, wid)["jobs"] == jobs


def test_fence_overflow_rolls_back_and_max_version_header_is_valid(api, pg, tokens):
    wid = accepted(api, tokens)["workflow_id"]
    assert cancel(api, tokens, wid, 9223372036854775807).json()["code"] == "VERSION_CONFLICT"
    with pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text("UPDATE jobs SET fence=9223372036854775807 WHERE workflow_id=:id"), {"id": wid}
        )
    before = snapshot(pg, wid)
    response = cancel(api, tokens, wid)
    assert response.status_code == 503 and snapshot(pg, wid) == before


def test_operator_foreign_token_and_multiple_grants(api, pg, tokens, mapped):
    ids = accepted(api, tokens)
    change(pg, mapped["approver"], "grant", Role.OPERATOR)
    try:
        # A real second operator token has a valid grant but does not own these resources.
        assert cancel(api, tokens, ids["workflow_id"], role="approver").status_code == 404
        assert (
            api.get(
                "/v1/incidents/" + ids["incident_id"], headers=authorization(tokens, "approver")
            ).status_code
            == 404
        )
        change(pg, mapped["approver"], "grant", Role.AUDITOR)
        assert (
            api.get(
                "/v1/workflows/" + ids["workflow_id"], headers=authorization(tokens, "approver")
            ).status_code
            == 200
        )
        assert cancel(api, tokens, ids["workflow_id"], role="approver").status_code == 404
    finally:
        change(pg, mapped["approver"], "revoke", Role.OPERATOR)
        change(pg, mapped["approver"], "revoke", Role.AUDITOR)


def test_twenty_cancellations_in_two_real_api_processes(api, pg, tokens, tmp_path, record_property):
    wid = accepted(api, tokens)["workflow_id"]
    with api_process(pg, tmp_path) as (_, one), api_process(pg, tmp_path) as (_, two):
        barrier = threading.Barrier(20)

        def send(index):
            barrier.wait(timeout=10)
            with httpx.Client(base_url=(one, two)[index % 2], trust_env=False, timeout=12) as http:
                return cancel(http, tokens, wid)

        with ThreadPoolExecutor(max_workers=20) as pool:
            responses = list(pool.map(send, range(20)))
    codes = [r.status_code for r in responses]
    assert codes.count(202) == 1 and codes.count(409) == 19
    assert snapshot(pg, wid)["events"] == 1
    with (
        api_process(pg, tmp_path) as (_, restarted),
        httpx.Client(base_url=restarted, trust_env=False, timeout=5) as http,
    ):
        response = cancel(http, tokens, wid, 2)
    assert response.status_code == 202
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "two_api_processes",
                "http": codes,
                "restart_http": response.status_code,
                "after": snapshot(pg, wid),
            },
            default=str,
        ),
    )


def test_revocation_between_role_check_and_read_cannot_reuse_auditor(api, pg, tokens, mapped):
    wid = accepted(api, tokens)["workflow_id"]
    original = PostgresWorkflows.authorize

    def revoke_after_authorize(self, principal, cancel=False):
        result = original(self, principal, cancel)
        change(pg, mapped["auditor"], "revoke", Role.AUDITOR)
        return result

    try:
        with patch.object(PostgresWorkflows, "authorize", revoke_after_authorize):
            response = api.get("/v1/workflows/" + wid, headers=authorization(tokens, "auditor"))
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    finally:
        change(pg, mapped["auditor"], "grant", Role.AUDITOR)


@pytest.mark.parametrize(
    "state",
    ["QUEUED", "INVESTIGATING", "RETRY_WAIT", "NEEDS_OPERATOR", "PLAN_READY", "AWAITING_APPROVAL"],
)
def test_every_safe_state_cancels_with_real_appender(api, pg, tokens, mapped, state):
    if state in {"PLAN_READY", "AWAITING_APPROVAL"}:
        # Synthetic future history in an ephemeral DB, NOT produced by a worker.
        # Its closed v2 baseline describes a blocked unsupported definition at version 2.
        ids = seed(pg, mapped["operator"], definition=2, state=state)
        from .test_workflow_persistence import snapshot as state_snapshot

        with pg["sessions"]["admin"]() as session:
            session.execute(
                text(
                    "UPDATE workflows SET version=2,reason_code='UNSUPPORTED_DEFINITION' WHERE id=:id"
                ),
                {"id": ids["workflow"]},
            )
            stored = state_snapshot(session, ids["workflow"])
            event = {
                "event_id": str(uuid4()),
                "schema_version": 2,
                "stream_id": str(ids["workflow"]),
                "seq": 1,
                "event_type": "workflow.blocked",
                "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "actor_id": None,
                "trace_id": uuid4().hex,
                "payload": {
                    "reason_code": "UNSUPPORTED_DEFINITION",
                    "aggregate_id": str(ids["workflow"]),
                    "aggregate_version": 2,
                    "evidence_ids": [],
                    "snapshot_hash": hashlib.sha256(canonical_bytes(stored)).hexdigest(),
                },
            }
            Draft202012Validator(V2, format_checker=FormatChecker()).validate(event)
            event["prev_hash"] = "0" * 64
            digest = event_hash(event)
            session.execute(
                text("INSERT INTO audit_streams VALUES(:id,1,:hash)"),
                {"id": ids["workflow"], "hash": digest},
            )
            session.execute(
                text("""INSERT INTO audit_events(event_id,stream_id,seq,event_type,schema_version,occurred_at,actor_id,trace_id,payload,prev_hash,hash,state_snapshot)
                VALUES(:event,:stream,1,'workflow.blocked',2,:stamp,NULL,:trace,CAST(:payload AS jsonb),:prev,:hash,CAST(:snapshot AS jsonb))"""),
                {
                    "event": event["event_id"],
                    "stream": ids["workflow"],
                    "stamp": event["occurred_at"],
                    "trace": event["trace_id"],
                    "payload": json.dumps(event["payload"]),
                    "prev": event["prev_hash"],
                    "hash": digest,
                    "snapshot": json.dumps(stored),
                },
            )
            session.commit()
        version = 2
    else:
        ids = seed(pg, mapped["operator"])
        version = 1
        if state != "QUEUED":
            transition(pg, ids)
            version = 2
        if state == "RETRY_WAIT":
            transition(pg, ids, "INVESTIGATING", state, "TRANSIENT_LOCAL_FAILURE")
            version = 3
        if state == "NEEDS_OPERATOR":
            transition(pg, ids, "INVESTIGATING", state, "PERMANENT_LOCAL_FAILURE")
            version = 3
    before = snapshot(pg, ids["workflow"])
    response = cancel(api, tokens, ids["workflow"], version)
    assert response.status_code == 202
    after = snapshot(pg, ids["workflow"])
    assert after["workflow"]["state"] == "CANCELLED" and after["workflow"]["resume_state"] is None
    assert after["workflow"]["definition_version"] == before["workflow"]["definition_version"]
    assert after["events"] == before["events"] + 1
    events, head = read(pg, ids["workflow"])
    assert verify_chain(events, head.last_seq, head.last_hash)


def test_real_signed_token_expires_and_all_three_routes_deny(
    api, pg, tokens, accounts, record_property
):
    ids = accepted(api, tokens)
    # Change only the synthetic local PKCE client's token lifespan, restoring it
    # immediately after issue. No clock/signature/JWT verification mocks.
    with httpx.Client(base_url=IDP_BASE, trust_env=False, timeout=10) as http:
        admin = http.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": "lab-admin",
                "password": (LOCAL / "kc_admin").read_text().strip(),
            },
        )
        admin.raise_for_status()
        hdr = {"Authorization": "Bearer " + admin.json()["access_token"]}
        clients = http.get(
            "/admin/realms/opspilot/clients", params={"clientId": "opspilot-lab-pkce"}, headers=hdr
        )
        clients.raise_for_status()
        client = clients.json()[0]
        path = "/admin/realms/opspilot/clients/" + client["id"]
        original = client.get("attributes", {})
        try:
            updated = http.put(
                path, json={"attributes": {**original, "access.token.lifespan": "1"}}, headers=hdr
            )
            updated.raise_for_status()
            issued = pkce_tokens(accounts["operator"])
        finally:
            # Keycloak merges attribute maps. Omission does NOT clear the override.
            restored = {
                **original,
                "access.token.lifespan": original.get("access.token.lifespan", ""),
            }
            http.put(path, json={"attributes": restored}, headers=hdr).raise_for_status()
            check = http.get(path, headers=hdr)
            check.raise_for_status()
            assert (
                check.json().get("attributes", {}).get("access.token.lifespan", "")
                == restored["access.token.lifespan"]
            )
    import jwt

    claims = jwt.decode(issued["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] <= 2
    fresh = pkce_tokens(accounts["operator"])
    fresh_claims = jwt.decode(fresh["access_token"], options={"verify_signature": False})
    assert fresh_claims["exp"] - fresh_claims["iat"] == 300
    deadline = time.monotonic() + 40
    while time.time() <= claims["exp"] + 30:
        assert time.monotonic() < deadline
        threading.Event().wait(0.1)
    auth = {
        "Authorization": "Bearer " + issued["access_token"],
        "If-Match": tag(ids["workflow_id"]),
    }
    responses = [
        api.get("/v1/incidents/" + ids["incident_id"], headers=auth),
        api.get("/v1/workflows/" + ids["workflow_id"], headers=auth),
        api.post("/v1/workflows/" + ids["workflow_id"] + "/cancel", headers=auth),
    ]
    assert all(
        r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer" for r in responses
    )
    assert snapshot(pg, ids["workflow_id"])["workflow"]["version"] == 1
    record_property(
        "observation",
        json.dumps(
            {
                "scenario": "real_expired_access_token",
                "http": [r.status_code for r in responses],
                "signature_clock_mocks": False,
            }
        ),
    )
