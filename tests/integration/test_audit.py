"""TEST-02-AUDIT/MIGRATE: real PostgreSQL permissions, concurrency and rollback."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from opspilot.adapters.postgres.audit import PostgresAppender, envelope
from opspilot.adapters.postgres.database import PostgresUow, database_ready
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.adapters.postgres.models import EventRow, StreamRow
from opspilot.audit.domain.envelope import canonical_bytes, verify_chain
from opspilot.identity.application.provision import create_identity

pytestmark = pytest.mark.integration


def payload(aggregate=None):
    return {
        "reason_code": "CONCURRENCY_TEST",
        "aggregate_id": str(aggregate or uuid4()),
        "aggregate_version": 1,
        "evidence_ids": [],
    }


def append(pg, stream, body=None, role="app"):
    with PostgresUow(pg["sessions"][role]) as uow:
        result = PostgresAppender(uow.session).append(
            stream, "identity.provisioned", None, uuid4().hex, body or payload()
        )
        uow.commit()
    return result


def read_stream(pg, stream):
    with pg["sessions"]["app"]() as session:
        rows = session.scalars(
            select(EventRow).where(EventRow.stream_id == stream).order_by(EventRow.seq)
        ).all()
        head = session.get(StreamRow, stream)
        return [envelope(row, True) for row in rows], head.last_seq, head.last_hash


def test_empty_database_migrates_without_metadata_drift(pg):
    assert set(inspect(pg["engines"]["app"]).get_table_names()) == {
        "principals",
        "role_grants",
        "audit_streams",
        "audit_events",
        "alembic_version",
        "incidents",
        "workflows",
        "workflow_steps",
        "jobs",
        "api_idempotency",
        "evidence",
    }
    assert database_ready(pg["engines"]["app"])


def test_twenty_concurrent_appends_are_gapless_and_hash_verified(pg):
    stream = uuid4()
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: append(pg, stream), range(20)))
    assert sorted(row["seq"] for row in results) == list(range(1, 21))
    events, seq, digest = read_stream(pg, stream)
    assert verify_chain(events, seq, digest)
    assert len({row["event_id"] for row in results}) == 20


def test_principal_and_event_commit_atomically_and_duplicate_is_noop(pg):
    subject = uuid4().hex
    with PostgresUow(pg["sessions"]["provisioner"]) as uow:
        pid = create_identity(
            IdentityWriter(uow.session),
            PostgresAppender(uow.session),
            "https://test.invalid",
            subject,
            uuid4().hex,
        )
        uow.commit()
    with PostgresUow(pg["sessions"]["provisioner"]) as uow:
        assert (
            create_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                "https://test.invalid",
                subject,
                uuid4().hex,
            )
            == pid
        )
        uow.commit()
    events, seq, digest = read_stream(pg, pid)
    assert len(events) == 1 and verify_chain(events, seq, digest)
    with pg["sessions"]["app"]() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM role_grants WHERE principal_id=:id"), {"id": pid}
            ).scalar_one()
            == 0
        )


def test_appender_sql_failure_rolls_back_principal_and_stream(pg):
    subject, stream = uuid4().hex, uuid4()
    with pytest.raises(DBAPIError):
        with PostgresUow(pg["sessions"]["provisioner"]) as uow:
            pid, _ = IdentityWriter(uow.session).create("https://rollback.invalid", subject)
            # Valid principal INSERT then an actual SQL appender FK violation.
            PostgresAppender(uow.session).append(
                stream, "identity.provisioned", uuid4(), uuid4().hex, payload(pid)
            )
            uow.commit()
    with pg["sessions"]["app"]() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM principals WHERE subject=:sub"), {"sub": subject}
            ).scalar_one()
            == 0
        )
        assert session.get(StreamRow, stream) is None


def test_concurrent_same_principal_has_single_provision_event(pg):
    subject = uuid4().hex

    def create(_):
        with PostgresUow(pg["sessions"]["provisioner"]) as uow:
            pid = create_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                "https://concurrency.invalid",
                subject,
                uuid4().hex,
            )
            uow.commit()
        return pid

    with ThreadPoolExecutor(max_workers=5) as pool:
        ids = list(pool.map(create, range(10)))
    assert len(set(ids)) == 1
    assert len(read_stream(pg, ids[0])[0]) == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET event_type='identity.disabled'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events CASCADE",
        "CREATE TABLE forbidden(id int)",
        "UPDATE audit_streams SET last_seq=99",
        "UPDATE principals SET enabled=false",
        "INSERT INTO role_grants VALUES (gen_random_uuid(),'admin',1,NULL)",
        "SET ROLE opspilot_audit_owner",
        "CREATE SCHEMA forbidden",
    ],
)
def test_app_role_cannot_mutate_protected_state(pg, statement):
    with pytest.raises(DBAPIError):
        with pg["engines"]["app"].begin() as connection:
            connection.execute(text(statement))


def test_provisioner_cannot_edit_events_or_create_schema(pg):
    for statement in (
        "DELETE FROM audit_events",
        "UPDATE audit_streams SET last_seq=0",
        "CREATE TABLE forbidden(id int)",
    ):
        with pytest.raises(DBAPIError):
            with pg["engines"]["provisioner"].begin() as connection:
                connection.execute(text(statement))


def test_function_owner_is_nologin_fixed_path_and_no_schema_create(pg):
    with pg["engines"]["admin"].connect() as connection:
        row = connection.execute(
            text("""SELECT r.rolname,r.rolcanlogin,p.prosecdef,p.proconfig,
            has_schema_privilege(r.oid,'public','CREATE') AS can_create
            FROM pg_proc p JOIN pg_roles r ON p.proowner=r.oid WHERE p.proname='audit_append'""")
        ).one()
        assert row.rolname == "opspilot_audit_owner" and not row.rolcanlogin
        assert (
            row.prosecdef
            and row.proconfig == ["search_path=pg_catalog, public"]
            and not row.can_create
        )


def test_tamper_by_privileged_role_detected(pg):
    stream = uuid4()
    append(pg, stream)
    events, seq, digest = read_stream(pg, stream)
    assert verify_chain(events, seq, digest)
    with pg["engines"]["admin"].begin() as connection:
        connection.execute(
            text(
                "UPDATE audit_events SET payload=jsonb_set(payload,'{reason_code}','\"TAMPERED\"') WHERE stream_id=:id"
            ),
            {"id": stream},
        )
    events, seq, digest = read_stream(pg, stream)
    assert not verify_chain(events, seq, digest)


@pytest.mark.parametrize(
    "value",
    [
        {"é": "漢字😀", "a": '"\\/\n\t\b\f\r', "arr": [True, None, False, 0, -1]},
        {"nested": {"z": [], "a": [1, {"ä": 2}]}},
        {"z": 10**30, "control": "\x01\x1f\u2028\u007f"},
    ],
)
def test_sql_python_canonical_bytes_parity(pg, value):
    raw = json.dumps(value, ensure_ascii=False)
    with pg["engines"]["app"].connect() as connection:
        actual = connection.execute(
            text("SELECT audit_canonical(CAST(:v AS json))"), {"v": raw}
        ).scalar_one()
    assert actual.encode("utf-8") == canonical_bytes(value)


@pytest.mark.parametrize("raw", ['{"x":1.0}', '{"x":1e2}', '{"x":1,"x":2}', "[0.1]"])
def test_sql_rejects_noncanonical_json(pg, raw):
    with pytest.raises(DBAPIError):
        with pg["engines"]["app"].connect() as connection:
            connection.execute(text("SELECT audit_canonical(CAST(:v AS json))"), {"v": raw})


@pytest.mark.parametrize(
    "mutation",
    [
        {"aggregate_version": None},
        {"reason_code": None},
        {"aggregate_id": "invalid"},
        {"evidence_ids": "wrong"},
        {"extra": "secret"},
        {"aggregate_version": 1.5},
        {"evidence_ids": [None]},
    ],
)
def test_sql_appender_validates_envelope_before_persistence(pg, mutation):
    stream = uuid4()
    with pytest.raises(DBAPIError):
        with pg["engines"]["app"].begin() as connection:
            connection.execute(
                text("SELECT audit_append(:s,'identity.provisioned',NULL,:t,:p)"),
                {"s": stream, "t": uuid4().hex, "p": json.dumps({**payload(), **mutation})},
            )
    with pg["sessions"]["app"]() as session:
        assert session.get(StreamRow, stream) is None


def test_relational_integrity_rejects_invalid_grant(pg):
    with pytest.raises(IntegrityError):
        with pg["engines"]["provisioner"].begin() as connection:
            connection.execute(
                text("INSERT INTO role_grants VALUES (:id,'admin',1,NULL)"), {"id": uuid4()}
            )


def test_reconnect_preserves_committed_stream(pg):
    stream = uuid4()
    original = append(pg, stream)
    pg["engines"]["app"].dispose()
    events, seq, digest = read_stream(pg, stream)
    assert events[0]["event_id"] == original["event_id"] and verify_chain(events, seq, digest)


def test_lock_timeout_rolls_back_without_advancing_stream(pg):
    stream = uuid4()
    append(pg, stream)
    before = read_stream(pg, stream)
    with pg["engines"]["admin"].begin() as lock:
        lock.execute(
            text("SELECT * FROM audit_streams WHERE stream_id=:id FOR UPDATE"), {"id": stream}
        )
        with pytest.raises(DBAPIError):
            with PostgresUow(pg["sessions"]["app"]) as uow:
                uow.session.execute(text("SET LOCAL lock_timeout='50ms'"))
                PostgresAppender(uow.session).append(
                    stream, "identity.provisioned", None, uuid4().hex, payload()
                )
                uow.commit()
    assert read_stream(pg, stream) == before
