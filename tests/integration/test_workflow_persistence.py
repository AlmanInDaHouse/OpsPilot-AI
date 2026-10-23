"""AC03-08 plus T03-02 SQL/contract negatives. No worker or crash acceptance."""

import hashlib
import json
import os
from datetime import UTC
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from opspilot.adapters.postgres.audit import PostgresAppender, PostgresWorkflowAppender, envelope
from opspilot.adapters.postgres.database import PostgresUow, database_ready
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.adapters.postgres.models import EventRow, StreamRow
from opspilot.audit.domain.envelope import canonical_bytes, event_hash, verify_chain
from opspilot.entrypoints.api.dto import AuditPage
from opspilot.identity.application.provision import change_identity, create_identity
from opspilot.identity.domain.principal import Role

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
V2 = json.loads((ROOT / "contracts/workflow-events-v2.schema.json").read_text(encoding="utf-8"))
SNAPSHOT = json.loads(
    (ROOT / "contracts/workflow-snapshot-v1.schema.json").read_text(encoding="utf-8")
)
POLICY = json.loads((ROOT / "contracts/workflow-policy-v1.json").read_text(encoding="utf-8"))


def seed(pg, creator=None, definition=1, state="QUEUED"):
    if creator is None:
        with PostgresUow(pg["sessions"]["provisioner"]) as uow:
            creator = create_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                "https://persistence.invalid",
                uuid4().hex,
                uuid4().hex,
            )
            uow.commit()
    ids = {
        "incident": uuid4(),
        "workflow": uuid4(),
        "step": uuid4(),
        "job": uuid4(),
        "creator": creator,
    }
    with pg["engines"]["app"].begin() as conn:
        conn.execute(
            text(
                "INSERT INTO incidents(id,creator_id,title,description) VALUES(:incident,:creator,'Prueba','Laboratorio sintético')"
            ),
            ids,
        )
        conn.execute(
            text(
                "INSERT INTO workflows(id,incident_id,creator_id,definition_version,state) VALUES(:workflow,:incident,:creator,:definition,:state)"
            ),
            {**ids, "definition": definition, "state": state},
        )
        conn.execute(
            text(
                "INSERT INTO workflow_steps(id,workflow_id,step_key) VALUES(:step,:workflow,'intake_snapshot')"
            ),
            ids,
        )
        conn.execute(
            text(
                "INSERT INTO jobs(id,workflow_id,step_id,kind) VALUES(:job,:workflow,:step,'intake_snapshot')"
            ),
            ids,
        )
    return ids


def snapshot(session, wid):
    row = (
        session.execute(text("SELECT * FROM workflows WHERE id=:id"), {"id": wid}).mappings().one()
    )
    return {
        "schema_version": 1,
        "workflow_id": str(row["id"]),
        "incident_id": str(row["incident_id"]),
        "definition_version": row["definition_version"],
        "state": row["state"],
        "version": row["version"],
        "reason_code": row["reason_code"],
        "cancel_requested_at": row["cancel_requested_at"]
        .astimezone(UTC)
        .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if row["cancel_requested_at"]
        else None,
    }


def body_for(
    session,
    ids,
    source="QUEUED",
    reason="LOCAL_STEP_STARTED",
    evidence_ids=(),
    kind="workflow.transitioned",
):
    state = snapshot(session, ids["workflow"])
    body = {
        "reason_code": reason,
        "aggregate_id": str(ids["workflow"]),
        "aggregate_version": state["version"],
        "evidence_ids": list(evidence_ids),
        "snapshot_hash": hashlib.sha256(canonical_bytes(state)).hexdigest(),
    }
    if kind == "workflow.transitioned":
        body["transition"] = {
            "from": source,
            "to": state["state"],
            "definition_version": state["definition_version"],
        }
    return body


def transition(
    pg,
    ids,
    source="QUEUED",
    target="INVESTIGATING",
    reason="LOCAL_STEP_STARTED",
    evidence_ids=(),
    role="worker",
):
    with PostgresUow(pg["sessions"][role]) as uow:
        if role == "app":
            uow.session.execute(
                text(
                    "UPDATE workflows SET state=:state,version=version+1,reason_code=:reason,cancel_requested_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": ids["workflow"], "state": target, "reason": reason},
            )
        else:
            uow.session.execute(
                text(
                    "UPDATE workflows SET state=:state,version=version+1,reason_code=:reason,resume_state=CASE WHEN CAST(:state AS varchar(32))='RETRY_WAIT' THEN 'INVESTIGATING' ELSE NULL END WHERE id=:id"
                ),
                {"id": ids["workflow"], "state": target, "reason": reason},
            )
        payload = body_for(uow.session, ids, source, reason, evidence_ids)
        event = PostgresWorkflowAppender(uow.session).append(
            ids["workflow"],
            "workflow.transitioned",
            ids["creator"] if role == "app" else None,
            uuid4().hex,
            payload,
        )
        uow.commit()
    return event


def evidence(pg, ids, mutation=None):
    payload = {
        "schema_version": 1,
        "incident_id": str(ids["incident"]),
        "incident_version": 1,
        "workflow_id": str(ids["workflow"]),
        "definition_version": 1,
        "status": "OPEN",
        "title_hash": hashlib.sha256(b"Prueba").hexdigest(),
        "description_hash": hashlib.sha256("Laboratorio sintético".encode()).hexdigest(),
    }
    values = {
        "id": uuid4(),
        "workflow": ids["workflow"],
        "source": f"incident:{ids['incident']}:v1",
        "hash": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
        "payload": json.dumps(payload),
    }
    values.update(mutation or {})
    with pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text("""INSERT INTO evidence(id,workflow_id,step_key,kind,collector_id,source_ref,content_hash,payload,independence_role)
        VALUES(:id,:workflow,'intake_snapshot','INCIDENT_SNAPSHOT_V1','local-intake-v1',:source,:hash,CAST(:payload AS jsonb),'INTAKE_SNAPSHOT')"""),
            values,
        )
    return values["id"]


def read(pg, wid):
    with pg["sessions"]["app"]() as session:
        rows = session.scalars(
            select(EventRow).where(EventRow.stream_id == wid).order_by(EventRow.seq)
        ).all()
        head = session.get(StreamRow, wid)
        return [envelope(row, True) for row in rows], head


def test_n_minus_one_preserves_real_identity_grants_events_hash_and_appender(pg_factory):
    with pg_factory("0001_platform") as old:
        with PostgresUow(old["sessions"]["provisioner"]) as uow:
            pid = create_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                "https://n-minus-one.invalid",
                uuid4().hex,
                uuid4().hex,
            )
            change_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                pid,
                "grant",
                Role.OPERATOR,
                uuid4().hex,
            )
            uow.commit()
        with old["engines"]["admin"].connect() as conn:
            before = conn.execute(
                text(
                    "SELECT jsonb_agg(to_jsonb(e) ORDER BY seq) FROM audit_events e WHERE stream_id=:id"
                ),
                {"id": pid},
            ).scalar_one()
            grant_before = conn.execute(
                text("SELECT row_to_json(g) FROM role_grants g WHERE principal_id=:id"), {"id": pid}
            ).scalar_one()
            function_before = conn.execute(
                text(
                    "SELECT pg_get_functiondef('audit_append(uuid,text,uuid,text,text)'::regprocedure)"
                )
            ).scalar_one()
        assert not database_ready(old["engines"]["app"])
        with patch.dict(os.environ, {"OPSPILOT_MIGRATION_DSN_FILE": str(old["dsnfile"])}):
            command.upgrade(old["config"], "head")
            command.check(old["config"])
            command.upgrade(old["config"], "head")
        with old["engines"]["admin"].connect() as conn:
            after = conn.execute(
                text(
                    "SELECT jsonb_agg(to_jsonb(e) ORDER BY seq) FROM audit_events e WHERE stream_id=:id"
                ),
                {"id": pid},
            ).scalar_one()
            assert all(item.pop("state_snapshot") is None for item in after) and after == before
            assert (
                conn.execute(
                    text("SELECT row_to_json(g) FROM role_grants g WHERE principal_id=:id"),
                    {"id": pid},
                ).scalar_one()
                == grant_before
            )
            assert (
                conn.execute(
                    text(
                        "SELECT pg_get_functiondef('audit_append(uuid,text,uuid,text,text)'::regprocedure)"
                    )
                ).scalar_one()
                == function_before
            )
        rows, head = read(old, pid)
        assert verify_chain(rows, head.last_seq, head.last_hash)
        assert database_ready(old["engines"]["app"])
        with patch.dict(os.environ, {"OPSPILOT_MIGRATION_DSN_FILE": str(old["dsnfile"])}):
            with pytest.raises(RuntimeError, match="Destructive downgrade prohibited"):
                command.downgrade(old["config"], "0001_platform")
        assert database_ready(old["engines"]["app"])
        ids = seed(old, creator=pid)
        transition(old, ids)


def test_failed_migration_rolls_back_tables_checks_and_revision(pg_factory):
    with pg_factory("0001_platform") as old:
        with old["engines"]["admin"].begin() as conn:
            conn.exec_driver_sql("""CREATE FUNCTION force_migration_failure() RETURNS event_trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST migration rollback'; END $$;
            CREATE EVENT TRIGGER force_migration_failure ON ddl_command_start WHEN TAG IN ('CREATE FUNCTION') EXECUTE FUNCTION force_migration_failure();""")
        with patch.dict(os.environ, {"OPSPILOT_MIGRATION_DSN_FILE": str(old["dsnfile"])}):
            with pytest.raises(DBAPIError):
                command.upgrade(old["config"], "head")
        with old["engines"]["admin"].connect() as conn:
            assert (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0001_platform"
            )
        assert set(inspect(old["engines"]["admin"]).get_table_names()) == {
            "principals",
            "role_grants",
            "audit_events",
            "audit_streams",
            "alembic_version",
        }


def test_sql_v2_snapshot_hash_schema_and_mixed_chain(pg):
    ids = seed(pg)
    with PostgresUow(pg["sessions"]["app"]) as uow:
        PostgresAppender(uow.session).append(
            ids["workflow"],
            "identity.provisioned",
            None,
            uuid4().hex,
            {
                "reason_code": "HISTORICAL_V1",
                "aggregate_id": str(ids["creator"]),
                "aggregate_version": 1,
                "evidence_ids": [],
            },
        )
        uow.commit()
    result = transition(pg, ids)
    public = {key: value for key, value in result.items() if key not in {"hash", "prev_hash"}}
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(public)
    assert (
        event_hash({key: value for key, value in result.items() if key != "hash"}) == result["hash"]
    )
    rows, head = read(pg, ids["workflow"])
    assert [row["schema_version"] for row in rows] == [1, 2]
    assert verify_chain(rows, head.last_seq, head.last_hash)
    with pg["sessions"]["app"]() as session:
        stored = session.get(EventRow, result["event_id"])
        Draft202012Validator(SNAPSHOT, format_checker=FormatChecker()).validate(
            stored.state_snapshot
        )
        assert (
            hashlib.sha256(canonical_bytes(stored.state_snapshot)).hexdigest()
            == result["payload"]["snapshot_hash"]
        )
    page = AuditPage.model_validate(
        {
            "items": [
                {key: value for key, value in row.items() if key not in {"hash", "prev_hash"}}
                for row in rows
            ],
            "next_after_seq": head.last_seq,
        }
    )
    assert [item.schema_version for item in page.items] == [1, 2]
    assert "state_snapshot" not in page.model_dump_json()


def test_v2_created_and_local_snapshot_are_valid_durable_rows(pg):
    ids = seed(pg)
    with PostgresUow(pg["sessions"]["app"]) as uow:
        event = PostgresWorkflowAppender(uow.session).append(
            ids["incident"],
            "incident.created",
            ids["creator"],
            uuid4().hex,
            {
                "reason_code": "INTAKE_ACCEPTED",
                "aggregate_id": str(ids["incident"]),
                "aggregate_version": 1,
                "evidence_ids": [],
            },
        )
        uow.commit()
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(
        {key: value for key, value in event.items() if key not in {"prev_hash", "hash"}}
    )
    transition(pg, ids)
    eid = evidence(pg, ids)
    result = transition(
        pg, ids, "INVESTIGATING", "NEEDS_OPERATOR", "LOCAL_SNAPSHOT_RECORDED", [str(eid)]
    )
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(
        {key: value for key, value in result.items() if key not in {"prev_hash", "hash"}}
    )
    with pg["engines"]["app"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT status FROM incidents WHERE id=:id"), {"id": ids["incident"]}
            ).scalar_one()
            == "OPEN"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"snapshot_hash": "0" * 64},
        {"aggregate_version": 999},
        {"aggregate_version": None},
        {"evidence_ids": [None]},
        {"reason_code": "CANCELLED_BY_OPERATOR"},
        {"token": "rejected-fixture"},
        {"transition": {"from": "OUTCOME_UNKNOWN", "to": "INVESTIGATING", "definition_version": 1}},
        {"transition": {"from": "QUEUED", "to": "INVESTIGATING", "definition_version": 2}},
    ],
)
def test_v2_invalid_payload_rolls_back_state_and_stream(pg, mutation):
    ids = seed(pg)
    with pytest.raises(DBAPIError):
        with PostgresUow(pg["sessions"]["worker"]) as uow:
            uow.session.execute(
                text(
                    "UPDATE workflows SET state='INVESTIGATING',version=2,reason_code='LOCAL_STEP_STARTED' WHERE id=:id"
                ),
                {"id": ids["workflow"]},
            )
            body = {**body_for(uow.session, ids), **mutation}
            PostgresWorkflowAppender(uow.session).append(
                ids["workflow"], "workflow.transitioned", None, uuid4().hex, body
            )
            uow.commit()
    with pg["sessions"]["app"]() as session:
        assert snapshot(session, ids["workflow"])["state"] == "QUEUED"
        assert session.get(StreamRow, ids["workflow"]) is None


@pytest.mark.parametrize("raw", ['{"x":1.0}', '{"x":1e2}', '{"x":1,"x":2}', "[]", "null"])
def test_v2_raw_noncanonical_or_wrong_shape_is_rejected(pg, raw):
    with pytest.raises(DBAPIError):
        with pg["engines"]["worker"].begin() as conn:
            conn.execute(
                text("SELECT audit_append_v2(:id,'workflow.transitioned',NULL,:trace,:body)"),
                {"id": uuid4(), "trace": uuid4().hex, "body": raw},
            )


def test_unknown_definition_holds_state_and_can_be_cancelled(pg):
    ids = seed(pg, definition=42)
    with PostgresUow(pg["sessions"]["worker"]) as uow:
        uow.session.execute(
            text(
                "UPDATE workflows SET version=2,reason_code='UNSUPPORTED_DEFINITION' WHERE id=:id"
            ),
            {"id": ids["workflow"]},
        )
        uow.session.execute(
            text("UPDATE jobs SET state='DEAD',fence=fence+1 WHERE id=:id"), {"id": ids["job"]}
        )
        payload = body_for(
            uow.session, ids, reason="UNSUPPORTED_DEFINITION", kind="workflow.blocked"
        )
        event = PostgresWorkflowAppender(uow.session).append(
            ids["workflow"], "workflow.blocked", None, uuid4().hex, payload
        )
        uow.commit()
    assert event["payload"]["reason_code"] == "UNSUPPORTED_DEFINITION"
    transition(pg, ids, "QUEUED", "CANCELLED", "CANCELLED_BY_OPERATOR", role="app")


@pytest.mark.parametrize("state", ["EXECUTING", "VERIFYING", "OUTCOME_UNKNOWN"])
def test_deferred_cancel_records_intention_without_transition_or_retry(pg, state):
    # Only privileged synthetic fixtures can place the future states here;
    # T03-02 adds no executor capable of producing them.
    ids = seed(pg, state=state)
    with PostgresUow(pg["sessions"]["app"]) as uow:
        uow.session.execute(
            text(
                "UPDATE workflows SET version=2,reason_code='CANCEL_REQUESTED',cancel_requested_at=clock_timestamp() WHERE id=:id"
            ),
            {"id": ids["workflow"]},
        )
        payload = body_for(
            uow.session, ids, reason="CANCEL_REQUESTED", kind="workflow.cancel_requested"
        )
        result = PostgresWorkflowAppender(uow.session).append(
            ids["workflow"], "workflow.cancel_requested", ids["creator"], uuid4().hex, payload
        )
        uow.commit()
    public = {key: value for key, value in result.items() if key not in {"hash", "prev_hash"}}
    Draft202012Validator(V2, format_checker=FormatChecker()).validate(public)
    with pg["sessions"]["app"]() as session:
        assert snapshot(session, ids["workflow"])["state"] == state
    with pytest.raises(DBAPIError):
        with pg["engines"]["app"].begin() as conn:
            conn.execute(
                text("UPDATE workflows SET version=3,cancel_requested_at=NULL WHERE id=:id"),
                {"id": ids["workflow"]},
            )


def test_cancel_retry_wait_clears_resume_without_widening_api_grants(pg):
    ids = seed(pg)
    transition(pg, ids)
    transition(pg, ids, "INVESTIGATING", "RETRY_WAIT", "TRANSIENT_LOCAL_FAILURE")
    transition(pg, ids, "RETRY_WAIT", "CANCELLED", "CANCELLED_BY_OPERATOR", role="app")
    with pg["engines"]["app"].connect() as conn:
        row = conn.execute(
            text("SELECT state,resume_state FROM workflows WHERE id=:id"), {"id": ids["workflow"]}
        ).one()
        assert tuple(row) == ("CANCELLED", None)


def test_duplicate_v2_append_cannot_add_a_second_event_for_version(pg):
    ids = seed(pg)
    result = transition(pg, ids)
    with pytest.raises(DBAPIError):
        with PostgresUow(pg["sessions"]["worker"]) as uow:
            PostgresWorkflowAppender(uow.session).append(
                ids["workflow"], "workflow.transitioned", None, uuid4().hex, result["payload"]
            )
            uow.commit()
    rows, head = read(pg, ids["workflow"])
    assert len(rows) == head.last_seq == 1
    assert verify_chain(rows, head.last_seq, head.last_hash)


@pytest.mark.parametrize(
    "mutation",
    [
        {"hash": "0" * 64},
        {"source": "incident:wrong:v1"},
        {"payload": "{}"},
        {"payload": '{"title":"unredacted-fixture"}'},
    ],
)
def test_evidence_rejects_wrong_hash_shape_source_or_unredacted_text(pg, mutation):
    ids = seed(pg)
    transition(pg, ids)
    with pytest.raises(DBAPIError):
        evidence(pg, ids, mutation)


@pytest.mark.parametrize("use_other_workflow", [False, True])
def test_audit_cannot_refer_to_missing_or_other_workflow_evidence(pg, use_other_workflow):
    ids, other = seed(pg), seed(pg)
    transition(pg, ids)
    transition(pg, other)
    eid = evidence(pg, other) if use_other_workflow else uuid4()
    with pytest.raises(DBAPIError):
        transition(
            pg, ids, "INVESTIGATING", "NEEDS_OPERATOR", "LOCAL_SNAPSHOT_RECORDED", [str(eid)]
        )
    with pg["sessions"]["app"]() as session:
        assert snapshot(session, ids["workflow"])["state"] == "INVESTIGATING"


@pytest.mark.parametrize(
    "role,actor", [("app", None), ("worker", "creator"), ("provisioner", None)]
)
def test_worker_events_reject_wrong_login_or_actor(pg, role, actor):
    ids = seed(pg)
    # Test-only fixture advancement; no production API or worker exists yet.
    with pg["engines"]["worker"].begin() as conn:
        conn.execute(
            text(
                "UPDATE workflows SET version=2,state='INVESTIGATING',reason_code='LOCAL_STEP_STARTED' WHERE id=:id"
            ),
            {"id": ids["workflow"]},
        )
    with pytest.raises(DBAPIError):
        with PostgresUow(pg["sessions"][role]) as uow:
            # Provisioner is denied before reading workflows or calling v2.
            if role == "provisioner":
                uow.session.execute(
                    text("SELECT audit_append_v2(:id,'workflow.transitioned',NULL,:trace,'{}')"),
                    {"id": ids["workflow"], "trace": uuid4().hex},
                )
            else:
                body = body_for(uow.session, ids)
                PostgresWorkflowAppender(uow.session).append(
                    ids["workflow"],
                    "workflow.transitioned",
                    ids["creator"] if actor else None,
                    uuid4().hex,
                    body,
                )


def test_real_http_audit_reads_mixed_versions_without_private_state(api, pg, mapped, tokens):
    from tests.contract.test_api import assert_response

    ids = seed(pg, creator=mapped["operator"])
    with PostgresUow(pg["sessions"]["app"]) as uow:
        PostgresAppender(uow.session).append(
            ids["workflow"],
            "identity.provisioned",
            None,
            uuid4().hex,
            {
                "reason_code": "HISTORICAL_V1",
                "aggregate_id": str(ids["creator"]),
                "aggregate_version": 1,
                "evidence_ids": [],
            },
        )
        uow.commit()
    transition(pg, ids)
    response = api.get(
        "/v1/audit-events",
        params={"stream_id": str(ids["workflow"])},
        headers={"Authorization": "Bearer " + tokens["auditor"]["access_token"]},
    )
    assert response.status_code == 200
    assert_response("/v1/audit-events", response)
    assert [item["schema_version"] for item in response.json()["items"]] == [1, 2]
    assert not {"state_snapshot", "hash", "prev_hash", "owner", "lease_until"} & set(
        response.json()["items"][1]
    )
    assert response.headers["Cache-Control"] == "no-store"


def test_evidence_deduplication_and_cross_workflow_step_binding(pg):
    first, second = seed(pg), seed(pg)
    transition(pg, first)
    eid = evidence(pg, first)
    with pytest.raises(DBAPIError):
        evidence(pg, first)
    with pytest.raises(DBAPIError):
        with pg["engines"]["worker"].begin() as conn:
            conn.execute(
                text("UPDATE workflow_steps SET evidence_id=:eid WHERE id=:step"),
                {"eid": eid, "step": second["step"]},
            )


@pytest.mark.parametrize(
    "role,statement",
    [
        (role, statement)
        for role in ("app", "worker")
        for statement in (
            "CREATE TABLE forbidden_t03(id int)",
            "CREATE SCHEMA forbidden_t03",
            "CREATE TEMP TABLE forbidden_t03(id int)",
            "UPDATE audit_events SET payload='{}'::jsonb",
            "DELETE FROM audit_events",
            "TRUNCATE workflows CASCADE",
            "UPDATE evidence SET payload='{}'::jsonb",
            "DELETE FROM evidence",
            "DELETE FROM api_idempotency",
            "UPDATE principals SET enabled=false",
            "SET ROLE opspilot_audit_owner",
        )
    ]
    + [
        ("worker", statement)
        for statement in (
            "SELECT * FROM api_idempotency",
            "SELECT * FROM role_grants",
            "INSERT INTO incidents(id) VALUES(gen_random_uuid())",
            "UPDATE workflows SET deadline_at=clock_timestamp()",
            "SELECT audit_append(gen_random_uuid(),'identity.provisioned',NULL,repeat('0',32),'{}')",
        )
    ]
    + [("app", "UPDATE jobs SET attempts=0"), ("provisioner", "SELECT * FROM workflows")],
)
def test_actual_runtime_privileges_deny_forbidden_operations(pg, role, statement):
    with pytest.raises(DBAPIError):
        with pg["engines"][role].begin() as conn:
            conn.execute(text(statement))


def test_worker_flags_database_scope_function_ownership_and_exact_column_grants(pg):
    with pg["engines"]["admin"].connect() as conn:
        flags = conn.execute(
            text(
                "SELECT rolcanlogin,rolsuper,rolinherit,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='opspilot_worker'"
            )
        ).one()
        assert tuple(flags) == (True, False, False, False, False, False, False)
        for database in ("postgres", "template1", "opspilot_keycloak"):
            assert not conn.execute(
                text("SELECT has_database_privilege('opspilot_worker',:db,'CONNECT')"),
                {"db": database},
            ).scalar_one()
        assert not conn.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='opspilot_worker'))"
            )
        ).scalar_one()
        owner_evidence_columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges WHERE grantee='opspilot_audit_owner' AND table_name='evidence' AND privilege_type='SELECT'"
                )
            ).scalars()
        )
        assert owner_evidence_columns == {"id", "workflow_id"}
        for function in ("audit_append_v2", "evidence_insert_guard"):
            row = conn.execute(
                text(
                    "SELECT r.rolname,r.rolcanlogin,p.prosecdef,p.proconfig,has_schema_privilege(r.oid,'public','CREATE') FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.proname=:name"
                ),
                {"name": function},
            ).one()
            assert tuple(row) == (
                "opspilot_audit_owner",
                False,
                True,
                ["search_path=pg_catalog, public"],
                False,
            )
        for role, tables in POLICY["roles"].items():
            for table, permissions in tables.items():
                if table == "audit_append_v2":
                    continue
                actual = set(
                    conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.column_privileges WHERE grantee=:role AND table_name=:table AND privilege_type='UPDATE'"
                        ),
                        {"role": role, "table": table},
                    ).scalars()
                )
                expected = set()
                for permission in permissions:
                    if permission.startswith("UPDATE("):
                        expected.update(permission[7:-1].split(","))
                assert actual == expected


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE workflows SET state='EXECUTING',version=version+1 WHERE id=:id",
        "UPDATE workflows SET version=version WHERE id=:id",
        "UPDATE workflows SET state='RETRY_WAIT',version=version+1,resume_state='EXECUTING' WHERE id=:id",
        "UPDATE workflows SET version=version+1,budget_spent_ms=300001 WHERE id=:id",
    ],
)
def test_db_workflow_guards_reject_illegal_edges_cas_shape_and_budget(pg, statement):
    ids = seed(pg)
    with pytest.raises(DBAPIError):
        with pg["engines"]["worker"].begin() as conn:
            conn.execute(text(statement), {"id": ids["workflow"]})


@pytest.mark.parametrize("target", ["EXECUTING", "RETRY_WAIT"])
def test_unknown_outcome_cannot_be_dispatched_or_retried_in_db(pg, target):
    ids = seed(pg, state="OUTCOME_UNKNOWN")
    with pytest.raises(DBAPIError):
        with pg["engines"]["worker"].begin() as conn:
            conn.execute(
                text(
                    "UPDATE workflows SET state=:state,version=version+1,resume_state=CASE WHEN CAST(:state AS varchar(32))='RETRY_WAIT' THEN 'INVESTIGATING' ELSE NULL END WHERE id=:id"
                ),
                {"state": target, "id": ids["workflow"]},
            )


def test_active_workflow_job_and_idempotency_relational_invariants(pg):
    ids, other = seed(pg), seed(pg)
    statements = [
        ("INSERT INTO workflows(id,incident_id,creator_id) VALUES(:new,:incident,:creator)", ids),
        (
            "INSERT INTO jobs(id,workflow_id,step_id,kind) VALUES(:new,:workflow,:step,'intake_snapshot')",
            ids,
        ),
        (
            "INSERT INTO jobs(id,workflow_id,step_id,kind) VALUES(:new,:workflow,:step,'intake_snapshot')",
            {**ids, "step": other["step"]},
        ),
        (
            "INSERT INTO workflows(id,incident_id,creator_id) VALUES(:new,:incident,:creator)",
            {**ids, "creator": other["creator"]},
        ),
    ]
    for statement, values in statements:
        with pytest.raises(DBAPIError):
            with pg["engines"]["app"].begin() as conn:
                conn.execute(text(statement), {**values, "new": uuid4()})
    values = {
        **ids,
        "key": uuid4(),
        "hash": "0" * 64,
        "body": json.dumps(
            {"incident_id": str(ids["incident"]), "workflow_id": str(ids["workflow"])}
        ),
    }
    insert = text(
        "INSERT INTO api_idempotency(principal_id,route,key,request_hash,response_status,response_body,incident_id,workflow_id) VALUES(:creator,'/v1/incidents',:key,:hash,202,CAST(:body AS jsonb),:incident,:workflow)"
    )
    with pg["engines"]["app"].begin() as conn:
        conn.execute(insert, values)
    for mutation in (
        {},
        {"creator": other["creator"], "key": uuid4()},
        {"key": uuid4(), "body": "{}"},
        {"key": uuid4(), "workflow": other["workflow"]},
    ):
        with pytest.raises(DBAPIError):
            with pg["engines"]["app"].begin() as conn:
                conn.execute(insert, {**values, **mutation})
