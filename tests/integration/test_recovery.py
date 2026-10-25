"""T03-06 recovery acceptance: real PostgreSQL, roles, processes and observable locks."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.database import make_engine
from opspilot.adapters.postgres.jobs import PostgresJobUow
from opspilot.audit.domain.envelope import verify_chain
from opspilot.workflows.application.jobs import Jobs
from opspilot.workflows.domain.access import VersionConflict
from opspilot.workflows.domain.jobs import WorkerRejected

from .commit_transport import commit_transport
from .conftest import LOCAL, ROOT, dsn_for
from .test_worker import cancel, observe, operator, phase, process, release, rows, start, waiting
from .test_worker import store as store
from .test_workflow_persistence import read, seed

pytestmark = pytest.mark.integration


def expire(pg, job):
    # Short fixtures for most races; a separate test waits the REAL 60 second lease.
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text(
                "UPDATE jobs SET lease_until=clock_timestamp()-interval '30 seconds' WHERE id=:id"
            ),
            {"id": job},
        )


def eligible(pg, job):
    # A test observation must survive the measured 5 s backward DB clock steps.
    # The product still enforces available_at exactly and polls when it is future.
    observe(
        pg,
        "SELECT available_at+interval '10 seconds'<=clock_timestamp() FROM jobs WHERE id=:id",
        {"id": job},
        40,
    )


def integrity(pg, ids):
    state = rows(pg, ids)
    events, head = read(pg, ids["workflow"])
    assert head and verify_chain(events, head.last_seq, head.last_hash)
    assert state["incident"]["status"] == "OPEN"
    assert len(state["evidence"]) <= 1
    assert state["job"]["attempts"] <= 3
    return state


@contextmanager
def child(pg, mode):
    path = LOCAL / f"recovery-{uuid4().hex}.dsn"
    path.write_text(dsn_for("worker", pg["database"]), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/integration/recovery_process.py"), mode, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    try:
        phase(proc, "ready")
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
        path.unlink(missing_ok=True)


def test_reclaim_invalidates_old_generation_and_heartbeat(store, record_property):
    pg, jobs = store
    ids, old, started = start(store)
    expire(pg, old.job_id)
    assert jobs.recover(uuid4().hex)
    recovered = integrity(pg, ids)
    assert recovered["workflow"]["state"] == "RETRY_WAIT"
    assert recovered["workflow"]["resume_state"] == "INVESTIGATING"
    assert recovered["job"]["fence"] == 2 and recovered["job"]["attempts"] == 1
    assert recovered["job"]["state"] == "READY"
    for operation in (
        lambda: jobs.renew(old),
        lambda: jobs.complete(old, started, started.incident.snapshot(), uuid4().hex),
    ):
        with pytest.raises(WorkerRejected):
            operation()
    assert not jobs.recover(uuid4().hex)
    eligible(pg, old.job_id)
    new = jobs.claim(uuid4())
    assert new.fence == 3 and new.owner != old.owner
    resumed = jobs.start(new, uuid4().hex)
    jobs.complete(new, resumed, resumed.incident.snapshot(), uuid4().hex)
    final = integrity(pg, ids)
    assert final["job"]["state"] == "DONE" and final["job"]["attempts"] == 2
    assert final["step"]["attempt_no"] == 2
    assert [e["payload"]["reason_code"] for e in final["audit"]] == [
        "LOCAL_STEP_STARTED",
        "TRANSIENT_LOCAL_FAILURE",
        "RETRY_READY",
        "LOCAL_SNAPSHOT_RECORDED",
    ]
    record_property(
        "reclaim",
        json.dumps(
            {
                "old_fence": 1,
                "revoked_fence": 2,
                "new_fence": 3,
                "attempts": 2,
                "evidence": 1,
                "events": 4,
            }
        ),
    )


def test_retry_schedule_survives_new_sessions_and_exhausts_at_three(store):
    pg, jobs = store
    ids, claim, started = start(store)
    for attempt in range(1, 4):
        before = rows(pg, ids)
        jobs.retry(claim, started, uuid4().hex)
        state = integrity(pg, ids)
        assert state["job"]["attempts"] == attempt
        assert state["job"]["active_spent_ms"] >= before["job"]["active_spent_ms"]
        if attempt == 3:
            assert (
                state["job"]["state"] == "DEAD"
                and state["workflow"]["reason_code"] == "RETRY_EXHAUSTED"
            )
            break
        assert state["workflow"]["state"] == "RETRY_WAIT"
        with pg["engines"]["admin"].connect() as conn:
            delay = conn.execute(
                text(
                    "SELECT extract(epoch FROM available_at-clock_timestamp()) FROM jobs WHERE id=:id"
                ),
                {"id": claim.job_id},
            ).scalar_one()
        assert -1 < delay <= min(30, 2**attempt)
        if delay > 0.1:
            assert jobs.claim(uuid4()) is None
        for engine in pg["engines"].values():
            engine.dispose()
        assert rows(pg, ids)["job"]["available_at"] == state["job"]["available_at"]
        eligible(pg, claim.job_id)
        claim = jobs.claim(uuid4())
        started = jobs.start(claim, uuid4().hex)
    assert jobs.claim(uuid4()) is None and not jobs.recover(uuid4().hex)
    assert state["workflow"]["state"] == "NEEDS_OPERATOR" and not state["evidence"]


@pytest.mark.parametrize(
    "point",
    [
        "before_claim_commit",
        "after_claim_commit",
        "before_start_commit",
        "after_start_commit",
        "snapshot",
        "before_evidence",
        "after_evidence",
        "after_audit",
        "before_result_commit",
        "after_result_commit",
    ],
)
def test_kill_points_recover_without_partial_effects(store, point, record_property):
    pg, jobs = store
    ids = seed(pg)
    with child(pg, point) as proc:
        release(proc)
        phase(proc, point)
        observed = rows(pg, ids)
        proc.kill()
        code = proc.wait(timeout=10)
    # SQL rollback may finish after OS exit; wait for the old backend to release locks.
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"), {"id": ids["workflow"]}
        )
        conn.execute(text("SELECT id FROM jobs WHERE id=:id FOR UPDATE"), {"id": ids["job"]})
    state = rows(pg, ids)
    if state["job"]["state"] == "LEASED":
        expire(pg, ids["job"])
        assert jobs.recover(uuid4().hex)
        eligible(pg, ids["job"])
    if point != "after_result_commit":
        claim = jobs.claim(uuid4())
        assert claim
        started = jobs.start(claim, uuid4().hex)
        jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    final = integrity(pg, ids)
    assert final["job"]["state"] == final["step"]["status"] == "DONE"
    assert len(final["evidence"]) == 1 and jobs.claim(uuid4()) is None
    record_property(
        "kill",
        json.dumps(
            {
                "point": point,
                "exit_code": code,
                "observed": {k: observed[k] for k in ("job", "workflow", "step")},
                "final": {k: final[k] for k in ("job", "workflow", "step")},
                "evidence_count": 1,
                "audit_events": len(final["audit"]),
            },
            default=str,
        ),
    )


def test_two_reclaim_processes_only_revoke_one_generation(store):
    pg, jobs = store
    ids, claim, _ = start(store)
    expire(pg, claim.job_id)
    with child(pg, "reclaim") as a, child(pg, "reclaim") as b:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(p.communicate, "go\n", timeout=15) for p in (a, b)]
            results = [json.loads(f.result()[0])["reclaimed"] for f in futures]
        assert sorted(results) == [False, True] and a.returncode == b.returncode == 0
    state = integrity(pg, ids)
    assert state["job"]["fence"] == 2 and state["job"]["attempts"] == 1
    assert len(state["audit"]) == 2


@pytest.mark.parametrize("winner", ["cancel", "recover", "retry", "heartbeat"])
def test_twenty_serialized_cancel_races(store, winner, record_property):
    pg, jobs = store
    for _iteration in range(5):
        ids, claim, started = start(store)
        operator(pg, ids)
        if winner in {"cancel", "recover"}:
            expire(pg, claim.job_id)
        with ThreadPoolExecutor(max_workers=1) as pool:
            if winner == "cancel":
                from opspilot.adapters.postgres.workflows import PostgresAccessUow
                from opspilot.workflows.domain.access import WorkflowTag

                with PostgresAccessUow(pg["sessions"]["app"]) as uow:
                    uow.workflows.cancel(
                        ids["creator"],
                        ids["workflow"],
                        WorkflowTag(ids["workflow"], 2),
                        uuid4().hex,
                    )
                    assert pool.submit(jobs.recover, uuid4().hex).result(timeout=3) is False
                    uow.commit()
            else:
                with PostgresJobUow(pg["sessions"]["worker"]) as uow:
                    if winner == "recover":
                        assert uow.jobs.recover(uuid4().hex)
                    elif winner == "retry":
                        uow.jobs.retry(claim, started, uuid4().hex)
                    else:
                        uow.jobs.renew(claim)
                    pending = pool.submit(cancel, pg, ids, 2)
                    waiting(pg, "SELECT id AS workflow_id%FOR UPDATE%")
                    uow.commit()
                if winner != "heartbeat":
                    with pytest.raises(VersionConflict):
                        pending.result(timeout=10)
                    cancel(pg, ids, 3)
                else:
                    pending.result(timeout=10)
        state = integrity(pg, ids)
        assert state["workflow"]["state"] == "CANCELLED" and state["job"]["state"] == "DEAD"
        assert state["job"]["owner"] is state["job"]["lease_until"] is None
        assert state["workflow"]["resume_state"] is None and not state["evidence"]
        assert not jobs.recover(uuid4().hex)
        with pytest.raises(WorkerRejected):
            jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    record_property("races", json.dumps({"winner": winner, "iterations": 5, "unsafe_effects": 0}))


def test_accounting_is_durable_monotonic_and_cancel_settles_cursor(store):
    pg, jobs = store
    ids, claim, started = start(store)
    initial = rows(pg, ids)
    for _ in range(3):
        jobs.renew(claim)
    renewed = rows(pg, ids)
    assert renewed["workflow"]["version"] == initial["workflow"]["version"] == 2
    assert renewed["job"]["active_spent_ms"] > initial["job"]["active_spent_ms"]
    jobs.retry(claim, started, uuid4().hex)
    settled = rows(pg, ids)
    assert settled["job"]["active_since"] is None
    assert not jobs.recover(uuid4().hex)
    assert rows(pg, ids)["job"]["active_spent_ms"] == settled["job"]["active_spent_ms"]
    operator(pg, ids)
    cancel(pg, ids, 3)
    assert rows(pg, ids)["job"]["active_spent_ms"] == settled["job"]["active_spent_ms"]


def test_accounting_cursor_cannot_regress_or_double_charge_after_clock_rewind(store):
    from opspilot.workflows.domain.jobs import Claim

    pg, jobs = store
    ids = seed(pg)
    owner = uuid4()
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(text("UPDATE jobs SET state='DEAD' WHERE id=:id"), {"id": ids["job"]})
        ids["job"] = uuid4()
        conn.execute(
            text("""INSERT INTO jobs(id,workflow_id,step_id,kind,state,owner,fence,attempts,
            active_since,active_spent_ms,lease_until) VALUES(:job,:workflow,:step,'intake_snapshot',
            'LEASED',:owner,1,1,clock_timestamp()+interval '30 seconds',1000,
            clock_timestamp()+interval '90 seconds')"""),
            {**ids, "owner": owner},
        )
    before = rows(pg, ids)
    claim = Claim(ids["job"], ids["workflow"], ids["step"], owner, 1, 1)
    jobs.renew(claim)
    jobs.renew(claim)
    after = rows(pg, ids)
    assert after["job"]["active_since"] == before["job"]["active_since"]
    assert after["job"]["active_spent_ms"] == 1000
    assert after["workflow"]["version"] == 1


@pytest.mark.parametrize(
    "role,sql",
    [
        ("worker", "SELECT * FROM audit_events"),
        ("worker", "UPDATE jobs SET active_spent_ms=0"),
        ("worker", "UPDATE jobs SET active_since=clock_timestamp()"),
        ("worker", "SELECT * FROM api_idempotency"),
        ("app", "SELECT worker_result_confirmed(gen_random_uuid(),2,gen_random_uuid())"),
    ],
)
def test_new_accounting_and_audit_confirmation_do_not_expand_table_permissions(store, role, sql):
    pg, _ = store
    with pytest.raises(DBAPIError) as caught, pg["engines"][role].begin() as conn:
        conn.execute(text(sql))
    assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("committed", [True, False])
def test_commit_transport_loss_reconciles_real_pg_transaction(store, committed, record_property):
    pg, jobs = store
    ids, claim, started = start(store)
    original = rows(pg, ids)
    with commit_transport(dsn_for("worker", pg["database"]), committed) as (dsn, armed, dropped):
        engine = make_engine(dsn)
        calls = 0

        def transactions():
            nonlocal calls
            calls += 1
            # The second UoW MUST use an independent connection after transport loss.
            return PostgresJobUow(sessionmaker(engine) if calls == 1 else pg["sessions"]["worker"])

        transport_jobs = Jobs(transactions)
        armed.set()
        try:
            if committed:
                evidence = transport_jobs.complete(
                    claim, started, started.incident.snapshot(), uuid4().hex
                )
                assert evidence == rows(pg, ids)["step"]["evidence_id"]
            else:
                with pytest.raises(WorkerRejected, match="COMMIT_UNCERTAIN"):
                    transport_jobs.complete(
                        claim, started, started.incident.snapshot(), uuid4().hex
                    )
            assert dropped.wait(5) and calls == 2
        finally:
            engine.dispose()
    final = integrity(pg, ids)
    assert len(final["evidence"]) == (1 if committed else 0)
    if not committed:
        assert final == original
        expire(pg, claim.job_id)
        assert jobs.recover(uuid4().hex)
        eligible(pg, claim.job_id)
        new = jobs.claim(uuid4())
        resumed = jobs.start(new, uuid4().hex)
        jobs.complete(new, resumed, resumed.incident.snapshot(), uuid4().hex)
        assert len(integrity(pg, ids)["evidence"]) == 1
    record_property(
        "commit_transport",
        json.dumps(
            {
                "committed_on_server": committed,
                "response_delivered": False,
                "connections": calls,
                "evidence_before_recovery": len(final["evidence"]),
            }
        ),
    )


def test_uncertain_commit_with_recheck_lock_timeout_stays_uncertain(store):
    pg, jobs = store
    ids, claim, started = start(store)
    with commit_transport(dsn_for("worker", pg["database"]), True) as (dsn, armed, dropped):
        engine = make_engine(dsn)
        calls = 0
        with pg["engines"]["admin"].begin() as lock:

            def transactions():
                nonlocal calls
                calls += 1
                if calls == 2:
                    lock.execute(
                        text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"),
                        {"id": ids["workflow"]},
                    )
                return PostgresJobUow(
                    sessionmaker(engine) if calls == 1 else pg["sessions"]["worker"]
                )

            armed.set()
            try:
                with pytest.raises(WorkerRejected, match="COMMIT_UNCERTAIN"):
                    Jobs(transactions).complete(
                        claim, started, started.incident.snapshot(), uuid4().hex
                    )
                assert dropped.wait(5) and calls == 2
            finally:
                engine.dispose()
    final = integrity(pg, ids)
    assert final["job"]["state"] == "DONE" and len(final["evidence"]) == 1
    assert jobs.confirmed(claim) == final["step"]["evidence_id"]


def aged_seed(pg):
    ids = seed(pg)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(text("UPDATE jobs SET state='DEAD' WHERE id=:id"), {"id": ids["job"]})
        ids = {**ids, **{key: uuid4() for key in ("incident", "workflow", "step", "job")}}
        for query in (
            "INSERT INTO incidents(id,creator_id,title,description) VALUES(:incident,:creator,'Aged','Synthetic')",
            "INSERT INTO workflows(id,incident_id,creator_id,created_at,deadline_at) VALUES(:workflow,:incident,:creator,clock_timestamp()-interval '290 seconds',clock_timestamp()+interval '10 seconds')",
            "INSERT INTO workflow_steps(id,workflow_id,step_key) VALUES(:step,:workflow,'intake_snapshot')",
            "INSERT INTO jobs(id,workflow_id,step_id,kind,available_at) VALUES(:job,:workflow,:step,'intake_snapshot',clock_timestamp()-interval '30 seconds')",
        ):
            conn.execute(text(query), ids)
    return ids


@pytest.mark.parametrize("target", ["QUEUED", "INVESTIGATING", "RETRY_WAIT"])
def test_deadline_expires_original_clock_even_when_retry_is_future(store, target):
    pg, jobs = store
    ids = aged_seed(pg)
    if target != "QUEUED":
        claim = jobs.claim(uuid4())
        started = jobs.start(claim, uuid4().hex)
        if target == "RETRY_WAIT":
            jobs.retry(claim, started, uuid4().hex)
            with pg["engines"]["admin"].begin() as conn:
                conn.execute(
                    text(
                        "UPDATE jobs SET available_at=clock_timestamp()+interval '30 seconds' WHERE id=:id"
                    ),
                    {"id": ids["job"]},
                )
    deadline = rows(pg, ids)["workflow"]["deadline_at"]
    observe(
        pg,
        "SELECT deadline_at+interval '10 seconds'<=clock_timestamp() FROM workflows WHERE id=:id",
        {"id": ids["workflow"]},
        timeout=60,
    )
    assert jobs.recover(uuid4().hex)
    final = integrity(pg, ids)
    assert final["workflow"]["deadline_at"] == deadline
    assert final["workflow"]["reason_code"] == final["step"]["error_code"] == "DEADLINE_EXHAUSTED"
    assert final["workflow"]["state"] == ("FAILED" if target == "QUEUED" else "NEEDS_OPERATOR")
    assert final["job"]["state"] == "DEAD" and jobs.claim(uuid4()) is None


@pytest.mark.parametrize("winner", ["cancel", "deadline"])
def test_cancel_vs_deadline_first_commit_decides_without_extra_versions(store, winner):
    from opspilot.adapters.postgres.workflows import PostgresAccessUow
    from opspilot.workflows.domain.access import WorkflowTag

    pg, jobs = store
    ids = aged_seed(pg)
    operator(pg, ids)
    observe(
        pg,
        "SELECT deadline_at+interval '10 seconds'<=clock_timestamp() FROM workflows WHERE id=:id",
        {"id": ids["workflow"]},
        timeout=60,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        if winner == "cancel":
            with PostgresAccessUow(pg["sessions"]["app"]) as uow:
                uow.workflows.cancel(
                    ids["creator"], ids["workflow"], WorkflowTag(ids["workflow"], 1), uuid4().hex
                )
                assert pool.submit(jobs.recover, uuid4().hex).result(timeout=3) is False
                uow.commit()
        else:
            with PostgresJobUow(pg["sessions"]["worker"]) as uow:
                assert uow.jobs.recover(uuid4().hex)
                pending = pool.submit(cancel, pg, ids, 1)
                waiting(pg, "SELECT id AS workflow_id%FOR UPDATE%")
                uow.commit()
            with pytest.raises(VersionConflict):
                pending.result(timeout=10)
    state = integrity(pg, ids)
    assert state["workflow"]["state"] == ("CANCELLED" if winner == "cancel" else "FAILED")
    assert state["workflow"]["version"] == 2 and len(state["audit"]) == 1
    assert state["job"]["state"] == "DEAD" and not state["evidence"]
    assert jobs.claim(uuid4()) is None and not jobs.recover(uuid4().hex)


def test_three_crashes_before_start_cannot_reset_attempts(store):
    pg, jobs = store
    ids = seed(pg)
    for attempt in range(1, 4):
        claim = jobs.claim(uuid4())
        assert rows(pg, ids)["job"]["attempts"] == attempt
        expire(pg, claim.job_id)
        assert jobs.recover(uuid4().hex)
    final = integrity(pg, ids)
    assert final["workflow"]["reason_code"] == "RETRY_EXHAUSTED"
    assert final["workflow"]["state"] == "NEEDS_OPERATOR"
    assert final["job"]["attempts"] == 3 and final["job"]["state"] == "DEAD"
    assert [e["payload"]["reason_code"] for e in final["audit"]] == [
        "LOCAL_STEP_STARTED",
        "RETRY_EXHAUSTED",
    ]


def test_unknown_definition_survives_recovery_restart_and_authorized_cancel(store):
    pg, jobs = store
    ids = seed(pg, definition=99)
    claim = jobs.claim(uuid4())
    expire(pg, claim.job_id)
    assert jobs.recover(uuid4().hex)
    held = integrity(pg, ids)
    for engine in pg["engines"].values():
        engine.dispose()
    assert not jobs.recover(uuid4().hex) and jobs.claim(uuid4()) is None
    assert rows(pg, ids) == held
    assert held["workflow"]["definition_version"] == 99
    assert held["workflow"]["state"] == "QUEUED" and held["workflow"]["version"] == 2
    operator(pg, ids)
    cancel(pg, ids, 2)
    final = integrity(pg, ids)
    assert final["workflow"]["state"] == "CANCELLED" and not final["evidence"]


def test_budget_exhaustion_has_durable_terminal_outcome_without_clock_reset(store):
    pg, jobs = store
    ids = seed(pg)
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(text("UPDATE jobs SET state='DEAD' WHERE id=:id"), {"id": ids["job"]})
        ids["job"] = uuid4()
        conn.execute(
            text("""INSERT INTO jobs(id,workflow_id,step_id,kind,active_spent_ms)
            VALUES(:job,:workflow,:step,'intake_snapshot',300000)"""),
            ids,
        )
    deadline = rows(pg, ids)["workflow"]["deadline_at"]
    assert jobs.recover(uuid4().hex)
    final = integrity(pg, ids)
    assert final["workflow"]["state"] == "FAILED"
    assert final["workflow"]["budget_spent_ms"] == final["job"]["active_spent_ms"] == 300000
    assert final["workflow"]["deadline_at"] == deadline
    assert final["workflow"]["reason_code"] == "DEADLINE_EXHAUSTED"
    assert final["job"]["state"] == "DEAD" and not final["evidence"]


def test_migration_0003_preserves_0002_rows_and_audit_functions(pg_factory):
    from unittest.mock import patch

    from alembic import command

    with pg_factory("0002_workflows") as pg:
        ids = seed(pg)
        with pg["engines"]["admin"].begin() as conn:
            conn.execute(
                text("""UPDATE jobs SET state='LEASED',owner=:owner,fence=1,attempts=1,
                lease_until=clock_timestamp()+interval '60 seconds' WHERE id=:id"""),
                {"id": ids["job"], "owner": uuid4()},
            )
            definition = conn.execute(
                text(
                    "SELECT pg_get_functiondef('audit_append_v2(uuid,text,uuid,text,text)'::regprocedure)"
                )
            ).scalar_one()
        before = rows(pg, ids)
        with patch.dict(os.environ, {"OPSPILOT_MIGRATION_DSN_FILE": str(pg["dsnfile"])}):
            command.upgrade(pg["config"], "head")
            command.check(pg["config"])
        after = rows(pg, ids)
        cursor = after["job"].pop("active_since")
        assert after["job"].pop("active_spent_ms") == 0 and before == after
        assert (after["job"]["lease_until"] - cursor).total_seconds() == 60
        with pg["engines"]["admin"].connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT pg_get_functiondef('audit_append_v2(uuid,text,uuid,text,text)'::regprocedure)"
                    )
                ).scalar_one()
                == definition
            )


def test_two_workers_die_real_leases_expire_then_100_jobs_recover(store, record_property):
    pg, jobs = store
    ids = [seed(pg)]
    for _ in range(99):
        ids.append(seed(pg, creator=ids[0]["creator"]))
    killed = []
    with child(pg, "after_start_commit") as a, child(pg, "after_start_commit") as b:
        release(a)
        release(b)
        phase(a, "after_start_commit")
        phase(b, "after_start_commit")
        for proc in (a, b):
            proc.kill()
            killed.append(proc.wait(timeout=10))
    with pg["engines"]["admin"].connect() as conn:
        lost = (
            conn.execute(text("SELECT id,lease_until,owner,fence FROM jobs WHERE state='LEASED'"))
            .mappings()
            .all()
        )
    assert len(lost) == 2 and all(j["fence"] == 1 for j in lost)
    # Contract lease remains 60 seconds; observer waits on PG time, never a blind sleep.
    observe(
        pg,
        "SELECT bool_and(lease_until+interval '10 seconds'<=clock_timestamp()) FROM jobs WHERE state='LEASED'",
        timeout=120,
    )
    with child(pg, "reclaim") as a, child(pg, "reclaim") as b:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(p.communicate, "go\n", timeout=15) for p in (a, b)]
            assert all(json.loads(f.result()[0])["reclaimed"] for f in futures)
    for job in lost:
        eligible(pg, job["id"])
    with process(pg) as a, process(pg) as b:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(p.communicate, "go\n", timeout=90) for p in (a, b)]
            logs = [[json.loads(line) for line in f.result()[0].splitlines()] for f in futures]
        assert a.returncode == b.returncode == 0
    counts = [sum(e.get("event") == "job.completed" for e in log) for log in logs]
    assert sum(counts) == 100
    for item in ids:
        state = integrity(pg, item)
        assert state["job"]["state"] == state["step"]["status"] == "DONE"
        assert len(state["evidence"]) == 1
        if item["job"] in {job["id"] for job in lost}:
            assert 59000 <= state["job"]["active_spent_ms"] <= 300000
            assert 59000 <= state["workflow"]["budget_spent_ms"] <= 300000
    assert jobs.claim(uuid4()) is None and not jobs.recover(uuid4().hex)
    record_property(
        "real_expiry_100",
        json.dumps(
            {
                "jobs": 100,
                "killed": killed,
                "lost": [dict(j) for j in lost],
                "per_worker": counts,
                "reclaimer_processes": 2,
                "completed_exit_codes": [a.returncode, b.returncode],
            },
            default=str,
        ),
    )


def test_worker_classified_transient_failure_schedules_durable_retry(store):
    pg, jobs = store
    ids = seed(pg)
    with pg["engines"]["admin"].begin() as conn:
        conn.exec_driver_sql("""CREATE SEQUENCE recovery_fail_once;
            CREATE FUNCTION recovery_fail_once() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF nextval('recovery_fail_once')=1 THEN
                RAISE EXCEPTION 'Test serialization failure' USING ERRCODE='40001';
            END IF; RETURN NEW; END $$;
            GRANT USAGE ON SEQUENCE recovery_fail_once TO opspilot_worker;
            CREATE TRIGGER recovery_fail_once BEFORE INSERT ON evidence
            FOR EACH ROW EXECUTE FUNCTION recovery_fail_once();""")
    with process(pg, cli=True) as proc:
        output, errors = proc.communicate(timeout=15)
        assert proc.returncode == 0 and not errors
        assert any(
            json.loads(line).get("code") == "POSTGRES_TRANSIENT" for line in output.splitlines()
        )
    state = rows(pg, ids)
    if state["job"]["state"] == "READY":
        assert state["workflow"]["state"] == "RETRY_WAIT"
        eligible(pg, ids["job"])
        with process(pg, cli=True) as proc:
            _, errors = proc.communicate(timeout=15)
            assert proc.returncode == 0 and not errors
    final = integrity(pg, ids)
    assert final["job"]["state"] == "DONE" and final["job"]["attempts"] == 2
    assert len(final["evidence"]) == 1
    assert [e["payload"]["reason_code"] for e in final["audit"]] == [
        "LOCAL_STEP_STARTED",
        "TRANSIENT_LOCAL_FAILURE",
        "RETRY_READY",
        "LOCAL_SNAPSHOT_RECORDED",
    ]


@pytest.mark.parametrize("table", ["evidence", "audit_events"])
def test_kill_during_blocked_pg_insert_rolls_back_then_recovers(store, table, record_property):
    pg, jobs = store
    ids = seed(pg)
    # The audit trigger must block the RESULT event, not LOCAL_STEP_STARTED.
    with pg["engines"]["admin"].begin() as conn:
        conn.exec_driver_sql("""CREATE FUNCTION recovery_insert_barrier() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF TG_TABLE_NAME='evidence' OR NEW.payload->>'reason_code'='LOCAL_SNAPSHOT_RECORDED' THEN
                PERFORM pg_advisory_xact_lock(306306);
            END IF; RETURN NEW; END $$;""")
        conn.exec_driver_sql(
            f"CREATE TRIGGER recovery_insert_barrier BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION recovery_insert_barrier()"
        )
    with pg["engines"]["admin"].connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(306306)"))
        try:
            with child(pg, "drain") as proc:
                release(proc)
                waiting(
                    pg,
                    "INSERT INTO evidence%" if table == "evidence" else "SELECT audit_append_v2%",
                )
                before = rows(pg, ids)
                assert before["job"]["state"] == "LEASED" and not before["evidence"]
                proc.kill()
                code = proc.wait(timeout=10)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(306306)"))
    with pg["engines"]["admin"].begin() as conn:
        conn.execute(
            text("SELECT id FROM workflows WHERE id=:id FOR UPDATE"), {"id": ids["workflow"]}
        )
        conn.exec_driver_sql(f"DROP TRIGGER recovery_insert_barrier ON {table}")
        conn.exec_driver_sql("DROP FUNCTION recovery_insert_barrier()")
    assert rows(pg, ids) == before
    expire(pg, ids["job"])
    assert jobs.recover(uuid4().hex)
    eligible(pg, ids["job"])
    claim = jobs.claim(uuid4())
    started = jobs.start(claim, uuid4().hex)
    jobs.complete(claim, started, started.incident.snapshot(), uuid4().hex)
    final = integrity(pg, ids)
    assert len(final["evidence"]) == 1 and final["job"]["state"] == "DONE"
    record_property(
        "blocked_insert_kill",
        json.dumps(
            {
                "table": table,
                "exit_code": code,
                "evidence_during_wait": 0,
                "evidence_after_recovery": 1,
                "old_fence": before["job"]["fence"],
                "new_fence": final["job"]["fence"],
            }
        ),
    )
