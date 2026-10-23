"""TEST-02-AUTH/CONTRACT: PKCE access tokens from the real lab Keycloak."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from opspilot.adapters.postgres.audit import PostgresAppender
from opspilot.adapters.postgres.database import PostgresUow
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.identity.application.provision import change_identity
from opspilot.identity.domain.principal import Role

pytestmark = pytest.mark.integration


def authorization(tokens, role="operator"):
    return {"Authorization": "Bearer " + tokens[role]["access_token"]}


def test_real_pkce_token_maps_only_to_local_grants(api, tokens, mapped):
    for role, pid in mapped.items():
        response = api.get("/v1/me", headers=authorization(tokens, role))
        assert response.status_code == 200
        assert response.json() == {"principal_id": str(pid), "roles": [role]}


def test_real_id_token_cannot_authenticate_api(api, tokens):
    response = api.get(
        "/v1/me", headers={"Authorization": "Bearer " + tokens["operator"]["id_token"]}
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_no_credentials_401_and_unknown_real_subject_403(api, tokens):
    response = api.get("/v1/me")
    assert response.status_code == 401
    assert api.get("/v1/me", headers=authorization(tokens, "unmapped")).status_code == 403


def test_audit_permissions_and_pagination(api, tokens, mapped):
    stream = mapped["operator"]
    for role in ("operator", "approver"):
        assert (
            api.get(
                "/v1/audit-events",
                params={"stream_id": stream},
                headers=authorization(tokens, role),
            ).status_code
            == 403
        )
    for role in ("auditor", "admin"):
        first = api.get(
            "/v1/audit-events",
            params={"stream_id": stream, "limit": 1},
            headers=authorization(tokens, role),
        )
        assert first.status_code == 200
        assert len(first.json()["items"]) == 1 and first.json()["next_after_seq"] == 1
        second = api.get(
            "/v1/audit-events",
            params={"stream_id": stream, "after_seq": 1},
            headers=authorization(tokens, role),
        )
        assert [row["seq"] for row in second.json()["items"]] == [2]
        empty = api.get(
            "/v1/audit-events",
            params={"stream_id": stream, "after_seq": 2},
            headers=authorization(tokens, role),
        )
        assert empty.json() == {"items": [], "next_after_seq": 2}


def test_role_revoke_denies_next_request_and_restore_is_audited(api, pg, tokens, mapped):
    pid = mapped["auditor"]

    def change(action):
        with PostgresUow(pg["sessions"]["provisioner"]) as uow:
            change_identity(
                IdentityWriter(uow.session),
                PostgresAppender(uow.session),
                pid,
                action,
                Role.AUDITOR,
                uuid4().hex,
            )
            uow.commit()

    change("revoke")
    try:
        assert (
            api.get(
                "/v1/audit-events",
                params={"stream_id": pid},
                headers=authorization(tokens, "auditor"),
            ).status_code
            == 403
        )
        assert api.get("/v1/me", headers=authorization(tokens, "auditor")).json()["roles"] == []
    finally:
        change("grant")
    assert (
        api.get(
            "/v1/audit-events", params={"stream_id": pid}, headers=authorization(tokens, "auditor")
        ).status_code
        == 200
    )


def test_disable_denies_next_request_without_new_token(api, pg, tokens, mapped):
    pid = mapped["operator"]
    with PostgresUow(pg["sessions"]["provisioner"]) as uow:
        change_identity(
            IdentityWriter(uow.session),
            PostgresAppender(uow.session),
            pid,
            "disable",
            None,
            uuid4().hex,
        )
        uow.commit()
    try:
        assert api.get("/v1/me", headers=authorization(tokens)).status_code == 403
    finally:
        # Test-only privileged restore; product CLI deliberately has no implicit re-enable.
        with pg["engines"]["admin"].begin() as connection:
            connection.execute(text("UPDATE principals SET enabled=true WHERE id=:id"), {"id": pid})


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"stream_id": "not-a-uuid"},
        {"stream_id": str(uuid4()), "limit": 101},
        {"stream_id": str(uuid4()), "after_seq": -1},
    ],
)
def test_invalid_queries_redacted(api, tokens, query):
    response = api.get("/v1/audit-events", params=query, headers=authorization(tokens, "auditor"))
    assert response.status_code == 422
    assert set(response.json()) == {"code", "request_id"}


def test_ready_requires_real_schema_and_jwks(api):
    assert api.get("/health/live").json() == {"status": "ok"}
    assert api.get("/health/ready").status_code == 200


def test_schema_mismatch_fails_closed_and_liveness_survives(api, pg, tokens):
    with pg["engines"]["migration"].begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='test_invalid_schema'"))
    try:
        assert api.get("/health/live").status_code == 200
        assert api.get("/health/ready").status_code == 503
        assert api.get("/v1/me", headers=authorization(tokens)).status_code == 503
    finally:
        with pg["engines"]["migration"].begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='0001_platform'"))
