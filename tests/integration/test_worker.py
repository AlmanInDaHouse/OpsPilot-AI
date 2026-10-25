"""T03-05 real PostgreSQL18, restricted role, locks and independent processes."""

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.adapters.postgres.workflows import PostgresAccessUow
from opspilot.workflows.application.access import WorkflowAccess
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.access import WorkflowTag
from opspilot.workflows.domain.jobs import WorkerRejected, snapshot_hash

from .conftest import LOCAL, dsn_for
from .test_incident_intake import process_line
from .test_workflow_persistence import read, seed

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(pg_factory):
    with pg_factory() as pg:
        yield pg, Jobs(lambda: PostgresJobUow(pg["sessions"]["worker"]))


def rows(pg, ids):
    with pg["engines"]["admin"].connect() as conn:
        result = {}
        for name, query, key in (
            ("workflow", "SELECT * FROM workflows WHERE id=:id", "workflow"),
            ("job", "SELECT * FROM jobs WHERE id=:id", "job"),
            ("step", "SELECT * FROM workflow_steps WHERE id=:id", "step"),
            ("incident", "SELECT * FROM incidents WHERE id=:id", "incident"),
        ):
            result[name] = dict(conn.execute(text(query), {"id": ids[key]}).mappings().one())
        result["evidence"] = [
            dict(r)
            for r in conn.execute(
                text("SELECT * FROM evidence WHERE workflow_id=:id"), {"id": ids["workflow"]}
            ).mappings()
        ]
        result["audit"] = [
            dict(r)
            for r in conn.execute(
                text("SELECT * FROM audit_events WHERE stream_id=:id ORDER BY seq"),
                {"id": ids["workflow"]},
            ).mappings()
        ]
        return result


def start(store):
    pg, jobs = store
    ids = seed(pg)
    claim = jobs.claim(uuid4())
    assert claim.job_id == ids["job"] and claim.version == 1 and claim.fence == 1
    started = jobs.start(claim, uuid4().hex)
    assert started.version == 2
    return ids, claim, started


def test_real_snapshot_and_atomic_result(store, record_property):
    pg, jobs = store
    ids, claim, started = start(store)
    initial = rows(pg, ids)
    assert initial["job"]["state"] == "LEASED" and initial["step"]["status"] == "RUNNING"
    assert initial["workflow"]["state"] == "INVESTIGATING"
    snapshot = started.incident.snapshot()
    schema = json.loads((ROOT / "contracts/incident-snapshot-v1.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
    eid = jobs.complete(claim, started, snapshot, uuid4().hex)
    final = rows(pg, ids)
    assert final["workflow"]["state"] == "NEEDS_OPERATOR" and final["workflow"]["version"] == 3
    assert final["incident"]["status"] == "OPEN" and final["incident"]["version"] == 1
    assert final["job"]["state"] == final["step"]["status"] == "DONE"
    assert final["job"]["owner"] is final["job"]["lease_until"] is None
    assert final["job"]["fence"] == 1 and final["job"]["attempts"] == 1
    assert final["step"]["evidence_id"] == eid
    evidence = final["evidence"][0]
    assert evidence["payload"] == snapshot and evidence["content_hash"] == snapshot_hash(snapshot)
    assert evidence["source_ref"] == f"incident:{ids['incident']}:v1"
    assert (
        evidence["collector_id"] == "local-intake-v1"
        and evidence["independence_role"] == "INTAKE_SNAPSHOT"
    )
    assert [r["payload"]["reason_code"] for r in final["audit"]] == [
        "LOCAL_STEP_STARTED",
        "LOCAL_SNAPSHOT_RECORDED",
    ]
    assert [r["payload"]["aggregate_version"] for r in final["audit"]] == [2, 3]
    for event in final["audit"]:
        assert event["actor_id"] is None and event["payload"]["snapshot_hash"] == snapshot_hash(
            event["state_snapshot"]
        )
    from opspilot.audit.domain.envelope import verify_chain

    events, head = read(pg, ids["workflow"])
    assert verify_chain(events, head.last_seq, head.last_hash)
    assert jobs.claim(uuid4()) is None
    before = rows(pg, ids)
    with pytest.raises(WorkerRejected):
        jobs.complete(claim, started, snapshot, uuid4().hex)
    assert rows(pg, ids) == before
    record_property(
        "result",
        json.dumps(
            {
                "job_id": str(claim.job_id),
                "fence_initial": 0,
                "fence_final": 1,
                "final": "NEEDS_OPERATOR",
                "evidence": str(eid),
                "hash": evidence["content_hash"],
                "events": 2,
            }
        ),
    )


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("fence", 0, "OWNERSHIP_LOST"),
        ("owner", None, "OWNERSHIP_LOST"),
        ("version", 1, "VERSION_CONFLICT"),
    ],
)
def test_stale_result_rejected_without_any_writes(store, field, value, code):
    pg, jobs = store
    ids, claim, started = start(store)
    if field == "version":
        started = replace(started, version=value)
    else:
        claim = replace(claim, **{field: value or uuid4() if field == "owner" else value})
    before = rows(pg, ids)
    with pytest.raises(WorkerRejected, match=code):
        jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    assert rows(pg, ids) == before


def test_heartbeat_uses_database_time_and_cannot_revive_expiry(store):
    pg, jobs = store
    ids, claim, started = start(store)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_until=clock_timestamp()+interval '5 seconds' WHERE id=:id"),
            {"id": claim.job_id},
        )
    jobs.renew(claim)
    with pg["engines"]["admin"].begin() as conn:
        remaining = conn.execute(
            text("SELECT extract(epoch FROM lease_until-clock_timestamp()) FROM jobs WHERE id=:id"),
            {"id": claim.job_id},
        ).scalar_one()
        assert 55 < remaining <= 60
        conn.execute(
            text("UPDATE jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id"),
            {"id": claim.job_id},
        )
    before = rows(pg, ids)
    for operation in (
        lambda: jobs.renew(claim),
        lambda: jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex),
    ):
        with pytest.raises(WorkerRejected, match="LEASE_EXPIRED"):
            operation()
    assert rows(pg, ids) == before and jobs.claim(uuid4()) is None


@pytest.mark.parametrize("definition", [2, 99])
def test_unknown_definition_is_held_without_running_v1(store, definition):
    pg, jobs = store
    ids = seed(pg, definition=definition)
    claim = jobs.claim(uuid4())
    assert jobs.start(claim, uuid4().hex) is None
    state = rows(pg, ids)
    assert state["workflow"]["state"] == "QUEUED" and state["workflow"]["version"] == 2
    assert state["workflow"]["definition_version"] == definition
    assert state["job"]["state"] == "DEAD" and state["job"]["fence"] == 2
    assert state["step"]["status"] == "PENDING" and state["evidence"] == []
    assert state["audit"][0]["event_type"] == "workflow.blocked"
    assert state["audit"][0]["payload"]["reason_code"] == "UNSUPPORTED_DEFINITION"


def test_deadline_guard_does_not_execute_snapshot(store):
    pg, jobs = store
    ids = seed(pg)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(text("UPDATE jobs SET state='DEAD' WHERE id=:id"), {"id": ids["job"]})
        # Expired fixture is inserted with its original deadline; immutable dates stay immutable.
        ids = {**ids, **{key: uuid4() for key in ("incident", "workflow", "step", "job")}}
        for statement in (
            "INSERT INTO incidents(id,creator_id,title,description) VALUES(:incident,:creator,'Expired','Synthetic')",
            "INSERT INTO workflows(id,incident_id,creator_id,created_at,deadline_at) VALUES(:workflow,:incident,:creator,clock_timestamp()-interval '20 minutes',clock_timestamp()-interval '1 minute')",
            "INSERT INTO workflow_steps(id,workflow_id,step_key) VALUES(:step,:workflow,'intake_snapshot')",
            "INSERT INTO jobs(id,workflow_id,step_id,kind) VALUES(:job,:workflow,:step,'intake_snapshot')",
        ):
            conn.execute(text(statement), ids)
    claim = jobs.claim(uuid4())
    assert jobs.start(claim, uuid4().hex) is None
    state = rows(pg, ids)
    assert state["workflow"]["state"] == "FAILED" and state["job"]["state"] == "DEAD"
    assert (
        state["evidence"] == []
        and state["audit"][0]["payload"]["reason_code"] == "DEADLINE_EXHAUSTED"
    )


@contextmanager
def process(pg, mode="drain", role="worker", cli=False):
    path = LOCAL / f"worker-process-{uuid4().hex}.dsn"
    path.write_text(dsn_for(role, pg["database"]), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    command = (
        [sys.executable, "-m", "opspilot.entrypoints.worker", "--dsn-file", str(path), "--drain"]
        if cli
        else [sys.executable, str(ROOT / "tests/integration/worker_process.py"), mode, str(path)]
    )
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    try:
        if not cli:
            assert process_line(child) == {"phase": "ready"}
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
        path.unlink(missing_ok=True)


def release(child):
    child.stdin.write("go\n")
    child.stdin.flush()


def phase(child, name):
    observed = []
    while True:
        item = process_line(child)
        observed.append(item)
        if item.get("phase") == name:
            return observed


@pytest.mark.parametrize("count", [1, 100])
def test_two_real_worker_processes_compete_without_loss(store, count, record_property):
    pg, jobs = store
    ids = [seed(pg)]
    for _ in range(count - 1):
        ids.append(seed(pg, creator=ids[0]["creator"]))
    with process(pg) as a, process(pg) as b:
        with ThreadPoolExecutor(max_workers=2) as pool:
            # stdin barrier: both independent OS processes are ready before dispatch.
            results = [pool.submit(child.communicate, "go\n", timeout=90) for child in (a, b)]
            logs = [
                [json.loads(line) for line in result.result()[0].splitlines()] for result in results
            ]
        assert a.returncode == b.returncode == 0
        completed = [item for log in logs for item in log if item.get("event") == "job.completed"]
        claimed = [item for log in logs for item in log if item.get("event") == "job.claimed"]
        assert len(completed) == len(claimed) == count
        assert len({item["job_id"] for item in claimed}) == count
        assert all(item["fence"] == 1 for item in claimed)
        for item in ids:
            state = rows(pg, item)
            assert (
                state["workflow"]["state"] == "NEEDS_OPERATOR" and state["workflow"]["version"] == 3
            )
            assert state["job"]["state"] == state["step"]["status"] == "DONE"
            assert (
                state["incident"]["status"] == "OPEN"
                and len(state["audit"]) == 2
                and len(state["evidence"]) == 1
            )
        record_property(
            "two_processes",
            json.dumps(
                {
                    "jobs": count,
                    "exit_codes": [a.returncode, b.returncode],
                    "per_worker": [
                        sum(i.get("event") == "job.completed" for i in log) for log in logs
                    ],
                    "claims": claimed,
                    "completed": completed,
                }
            ),
        )
    assert jobs.claim(uuid4()) is None


def test_skip_locked_and_claim_commits_without_workflow_lock(store):
    pg, jobs = store
    ids = seed(pg)
    with pg["engines"]["admin"].begin() as lock:
        lock.execute(
            text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"), {"id": ids["workflow"]}
        )
        # Holding workflow does not prevent the independent job-only claim from committing.
        with ThreadPoolExecutor(max_workers=1) as pool:
            claim = pool.submit(jobs.claim, uuid4()).result(timeout=3)
            assert claim.job_id == ids["job"]
    other = seed(pg, creator=ids["creator"])
    with pg["engines"]["admin"].begin() as lock:
        lock.execute(text("SELECT id FROM jobs WHERE id=:id FOR UPDATE"), {"id": other["job"]})
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(jobs.claim, uuid4()).result(timeout=3) is None


def cancel(pg, ids, version):
    return WorkflowAccess(lambda: PostgresAccessUow(pg["sessions"]["app"])).cancel(
        ids["creator"], ids["workflow"], WorkflowTag(ids["workflow"], version), uuid4().hex
    )


def operator(pg, ids):
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("INSERT INTO role_grants(principal_id,role) VALUES(:id,'operator')"),
            {"id": ids["creator"]},
        )


@pytest.mark.parametrize(
    "point,version",
    [("after_claim", 1), ("after_start", 2), ("before_result", 2), ("after_result", 3)],
)
def test_cancel_respects_real_process_boundaries(store, point, version, record_property):
    pg, _ = store
    ids = seed(pg)
    operator(pg, ids)
    with process(pg, point) as child:
        release(child)
        phase(child, point)
        answer = cancel(pg, ids, version)
        assert answer["state"] == "CANCELLED"
        before = rows(pg, ids)
        output, errors = child.communicate("go\n", timeout=20)
        assert child.returncode == 0 and not errors
    assert rows(pg, ids) == before
    assert len(before["evidence"]) == (1 if point == "after_result" else 0)
    assert before["job"]["state"] == ("DONE" if point == "after_result" else "DEAD")
    assert before["job"]["fence"] == (1 if point == "after_result" else 2)
    assert before["incident"]["status"] == "OPEN"
    record_property(
        "cancel_boundary",
        json.dumps(
            {
                "point": point,
                "version": before["workflow"]["version"],
                "fence": before["job"]["fence"],
                "evidence": len(before["evidence"]),
                "events": len(before["audit"]),
                "exit_code": child.returncode,
            }
        ),
    )


def test_cancel_before_claim_means_dead_job_not_executed(store):
    pg, jobs = store
    ids = seed(pg)
    operator(pg, ids)
    cancel(pg, ids, 1)
    before = rows(pg, ids)
    assert jobs.claim(uuid4()) is None and rows(pg, ids) == before


@pytest.mark.parametrize(
    "table,deferred,expected",
    [
        ("audit_events", False, "AUDIT_FAILED"),
        ("evidence", False, "POSTGRES_FAILED"),
        ("evidence", True, "COMMIT_FAILED"),
    ],
)
def test_real_database_fault_rolls_back_entire_result(store, table, deferred, expected):
    pg, jobs = store
    ids, claim, started = start(store)
    before = rows(pg, ids)
    with worker_failure(pg, table, deferred=deferred):
        with pytest.raises(WorkerRejected, match=expected):
            jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    assert rows(pg, ids) == before
    jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)


@contextmanager
def worker_failure(pg, table, deferred=False, operation="INSERT"):
    assert table in {"audit_events", "evidence", "jobs"} and operation in {"INSERT", "UPDATE"}
    with pg["engines"]["admin"].begin() as conn:
        conn.exec_driver_sql(
            "CREATE FUNCTION worker_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Controlled worker failure' USING ERRCODE='23514'; END $$"
        )
        statement = (
            f"CREATE CONSTRAINT TRIGGER worker_test_failure AFTER {operation} ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION worker_test_failure()"
            if deferred
            else f"CREATE TRIGGER worker_test_failure BEFORE {operation} ON {table} FOR EACH ROW EXECUTE FUNCTION worker_test_failure()"
        )
        conn.exec_driver_sql(statement)
    try:
        yield
    finally:
        with pg["engines"]["admin"].begin() as conn:
            conn.exec_driver_sql(f"DROP TRIGGER worker_test_failure ON {table}")
            conn.exec_driver_sql("DROP FUNCTION worker_test_failure()")


def observe(pg, query, params=None, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with pg["engines"]["admin"].connect() as conn:
            result = conn.execute(text(query), params or {}).scalar_one()
        if result:
            return
        threading.Event().wait(0.01)
    pytest.fail("PostgreSQL synchronization condition not observed")


def waiting(pg, query):
    observe(
        pg,
        "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE :query)",
        {"query": query},
    )


@pytest.mark.parametrize("winner", ["cancel", "result"])
def test_cancel_and_result_wait_on_real_workflow_lock(store, winner):
    pg, jobs = store
    ids, claim, started = start(store)
    operator(pg, ids)
    with ThreadPoolExecutor(max_workers=1) as pool:
        if winner == "cancel":
            with PostgresAccessUow(pg["sessions"]["app"]) as uow:
                uow.workflows.cancel(
                    ids["creator"], ids["workflow"], WorkflowTag(ids["workflow"], 2), uuid4().hex
                )
                pending = pool.submit(
                    jobs.complete, claim, started, started.incident.snapshot(), uuid4().hex
                )
                waiting(pg, "SELECT * FROM workflows%FOR UPDATE%")
                uow.commit()
            with pytest.raises(WorkerRejected, match="WORKFLOW_CANCELLED"):
                pending.result(timeout=10)
            final = rows(pg, ids)
            assert final["workflow"]["state"] == "CANCELLED" and final["workflow"]["version"] == 3
            assert (
                final["job"]["state"] == "DEAD"
                and len(final["evidence"]) == 0
                and len(final["audit"]) == 2
            )
        else:
            from opspilot.workflows.domain.access import VersionConflict

            with PostgresJobUow(pg["sessions"]["worker"]) as uow:
                uow.session.execute(
                    text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"),
                    {"id": ids["workflow"]},
                )
                pending = pool.submit(cancel, pg, ids, 2)
                waiting(pg, "SELECT id AS workflow_id%FOR UPDATE%")
                uow.jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
                uow.commit()
            with pytest.raises(VersionConflict):
                pending.result(timeout=10)
            final = rows(pg, ids)
            assert (
                final["workflow"]["state"] == "NEEDS_OPERATOR" and final["workflow"]["version"] == 3
            )
            assert (
                final["job"]["state"] == "DONE"
                and len(final["evidence"]) == 1
                and len(final["audit"]) == 2
            )


def test_expiry_while_waiting_for_audit_rolls_back_every_result_write(store):
    pg, jobs = store
    ids, claim, started = start(store)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_until=clock_timestamp()+interval '2 seconds' WHERE id=:id"),
            {"id": claim.job_id},
        )
    before = rows(pg, ids)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg["engines"]["admin"].begin() as lock:
            lock.execute(
                text("SELECT stream_id FROM audit_streams WHERE stream_id=:id FOR UPDATE"),
                {"id": claim.workflow_id},
            )
            pending = pool.submit(
                jobs.complete, claim, started, started.incident.snapshot(), uuid4().hex
            )
            waiting(pg, "SELECT audit_append_v2%")
            observe(
                pg,
                "SELECT lease_until<=clock_timestamp() FROM jobs WHERE id=:id",
                {"id": claim.job_id},
            )
        with pytest.raises(WorkerRejected, match="LEASE_EXPIRED"):
            pending.result(timeout=10)
    assert rows(pg, ids) == before


def test_new_generation_rejects_old_owner_and_commits_one_result(store, record_property):
    pg, jobs = store
    ids, old, started = start(store)
    # Fixture-only handoff proves fencing. Product reclaim policy remains T03-06.
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("UPDATE jobs SET state='READY',owner=NULL,lease_until=NULL WHERE id=:id"),
            {"id": old.job_id},
        )
    new = jobs.claim(uuid4())
    assert new.fence == old.fence + 1 and new.owner != old.owner
    before = rows(pg, ids)
    with pytest.raises(WorkerRejected, match="OWNERSHIP_LOST"):
        jobs.complete(old, started, started.incident.snapshot(), uuid4().hex)
    assert rows(pg, ids) == before
    current = jobs.start(new, uuid4().hex)
    jobs.complete(new, current, current.incident.snapshot(), uuid4().hex)
    final = rows(pg, ids)
    assert final["job"]["fence"] == 2 and len(final["evidence"]) == 1 and len(final["audit"]) == 2
    record_property(
        "generations",
        json.dumps(
            {
                "job_id": str(old.job_id),
                "old_fence": old.fence,
                "new_fence": new.fence,
                "committed_evidence": 1,
                "reclaim": "ADMIN_FIXTURE_ONLY",
            }
        ),
    )


@pytest.mark.parametrize(
    "corruption",
    [
        {"schema_version": True},
        {"definition_version": 2},
        {"title": "forbidden"},
        {"title_hash": "0" * 64},
    ],
)
def test_corrupted_snapshot_cannot_be_confirmed(store, corruption):
    pg, jobs = store
    ids, claim, started = start(store)
    before = rows(pg, ids)
    with pytest.raises(WorkerRejected, match="SNAPSHOT_INVALID"):
        jobs.complete(claim, started, {**started.incident.snapshot(), **corruption}, uuid4().hex)
    assert rows(pg, ids) == before


def test_duplicate_evidence_is_rejected_with_no_partial_result(store):
    pg, jobs = store
    ids, claim, started = start(store)
    from .test_workflow_persistence import evidence

    evidence(pg, ids)
    before = rows(pg, ids)
    with pytest.raises(WorkerRejected, match="POSTGRES_FAILED"):
        jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    assert rows(pg, ids) == before


def test_heartbeat_real_thread_renews_while_handler_is_paused(store):
    pg, _ = store
    ids = seed(pg)
    with process(pg, "after_start") as child:
        release(child)
        phase(child, "after_start")
        before = rows(pg, ids)["job"]["lease_until"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            observed = json.loads(pool.submit(child.stdout.readline).result(timeout=25))
        assert observed["event"] == "lease.status" and observed["code"] == "LEASE_RENEWED"
        after = rows(pg, ids)["job"]["lease_until"]
        assert after > before
        # The thread interval is checked separately. Only PG time decides lease validity;
        # do not assume host monotonic and Docker's DB wall clock advance identically.
        with pg["engines"]["admin"].connect() as conn:
            assert conn.execute(
                text("""SELECT lease_until>clock_timestamp()
                AND lease_until<=clock_timestamp()+interval '60 seconds'
                FROM jobs WHERE id=:id"""),
                {"id": ids["job"]},
            ).scalar_one()
        out, errors = child.communicate("go\n", timeout=15)
        assert child.returncode == 0 and not errors
    assert rows(pg, ids)["workflow"]["state"] == "NEEDS_OPERATOR"


def test_heartbeat_loss_after_cancel_prevents_process_result(store):
    pg, _ = store
    ids = seed(pg)
    operator(pg, ids)
    with process(pg, "after_start") as child:
        release(child)
        phase(child, "after_start")
        cancel(pg, ids, 2)
        before = rows(pg, ids)
        with ThreadPoolExecutor(max_workers=1) as pool:
            observed = json.loads(pool.submit(child.stdout.readline).result(timeout=25))
        assert observed["code"] == "OWNERSHIP_LOST"
        output, errors = child.communicate("go\n", timeout=15)
        assert child.returncode == 0 and not errors
        assert any(json.loads(line).get("code") == "OWNERSHIP_LOST" for line in output.splitlines())
    assert rows(pg, ids) == before and before["evidence"] == []


def test_no_workflow_or_job_lock_held_during_snapshot_calculation(store):
    pg, jobs = store
    ids, claim, started = start(store)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("SELECT id FROM workflows WHERE id=:id FOR UPDATE NOWAIT"), {"id": ids["workflow"]}
        )
        conn.execute(text("SELECT id FROM jobs WHERE id=:id FOR UPDATE NOWAIT"), {"id": ids["job"]})
        assert started.incident.snapshot()["incident_id"] == str(ids["incident"])
    jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)


def test_permanent_snapshot_error_is_audited_without_retry_or_evidence(store):
    pg, _ = store
    ids = seed(pg)
    with process(pg, "snapshot_failure") as child:
        output, errors = child.communicate("go\n", timeout=15)
        assert child.returncode == 0 and not errors
        assert any(
            json.loads(line).get("code") == "SNAPSHOT_FAILED" for line in output.splitlines()
        )
    final = rows(pg, ids)
    assert final["workflow"]["state"] == "NEEDS_OPERATOR" and final["workflow"]["version"] == 3
    assert final["workflow"]["reason_code"] == "PERMANENT_LOCAL_FAILURE"
    assert final["step"]["status"] == "FAILED" and final["job"]["state"] == "DEAD"
    assert final["job"]["fence"] == 2 and len(final["audit"]) == 2 and final["evidence"] == []


def test_permanent_failure_requires_ownership_and_rolls_back_if_audit_fails(store):
    pg, jobs = store
    ids, claim, started = start(store)
    before = rows(pg, ids)
    with worker_failure(pg, "audit_events"):
        with pytest.raises(WorkerRejected, match="AUDIT_FAILED"):
            jobs.fail(claim, started, uuid4().hex)
    assert rows(pg, ids) == before
    with pytest.raises(WorkerRejected, match="OWNERSHIP_LOST"):
        jobs.fail(replace(claim, fence=0), started, uuid4().hex)
    assert rows(pg, ids) == before


def test_cli_rejects_other_role_without_secret_or_sql_output(store):
    pg, _ = store
    with process(pg, role="app", cli=True) as child:
        output, errors = child.communicate(timeout=15)
        assert child.returncode == 1 and not errors
        assert json.loads(output)["code"] == "WORKER_ROLE_REQUIRED"
        assert "postgresql" not in output and "password" not in output.lower()


def test_real_claim_commit_failure_is_distinguished_and_leaves_ready_job(store):
    pg, _ = store
    ids = seed(pg)
    before = rows(pg, ids)
    with worker_failure(pg, "jobs", deferred=True, operation="UPDATE"):
        with process(pg, cli=True) as child:
            output, errors = child.communicate(timeout=15)
            assert child.returncode == 1 and not errors
            assert json.loads(output.splitlines()[-1])["code"] == "COMMIT_FAILED"
    assert rows(pg, ids) == before


@pytest.mark.parametrize(
    "point,finished", [("after_claim", False), ("before_result", False), ("after_result", True)]
)
def test_worker_kill_and_restart_retains_rows_without_speculative_reclaim(
    store, point, finished, record_property
):
    pg, _ = store
    ids = seed(pg)
    with process(pg, point) as child:
        release(child)
        phase(child, point)
        before = rows(pg, ids)
        child.kill()
        code = child.wait(timeout=10)
    with process(pg, cli=True) as restarted:
        output, errors = restarted.communicate(timeout=15)
        assert restarted.returncode == 0 and not errors
    assert rows(pg, ids) == before
    assert before["job"]["state"] == ("DONE" if finished else "LEASED")
    assert len(before["evidence"]) == (1 if finished else 0)
    record_property(
        "restart",
        json.dumps(
            {
                "point": point,
                "killed_exit_code": code,
                "restart_exit_code": 0,
                "state": before["job"]["state"],
                "fence": before["job"]["fence"],
                "reclaim": "T03-06_PENDING",
            }
        ),
    )
