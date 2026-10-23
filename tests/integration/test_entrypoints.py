"""Exercise actual composition and privileged CLI against the real services."""

import os
import sys
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from opspilot.entrypoints.api.app import create_app
from opspilot.entrypoints.provision import main as provision

pytestmark = pytest.mark.integration


def test_real_composition_root_validates_configuration_and_closes_resources(
    pg, tokens, tmp_path, monkeypatch
):
    dsnfile = tmp_path / "app.dsn"
    dsnfile.write_text(pg["engines"]["app"].url.render_as_string(hide_password=False))
    issuer = "http://127.0.0.1:59080/realms/opspilot"
    base = (
        "http://keycloak:8080"
        if os.environ.get("OPSPILOT_LAB_INTERNAL") == "1"
        else "http://127.0.0.1:59080"
    )
    for name, value in {
        "ENVIRONMENT": "lab",
        "DATABASE_DSN_FILE": str(dsnfile),
        "OIDC_ISSUER": issuer,
        "OIDC_AUDIENCE": "opspilot-api",
        "OIDC_JWKS_URL": base + "/realms/opspilot/protocol/openid-connect/certs",
    }.items():
        monkeypatch.setenv("OPSPILOT_" + name, value)
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").status_code == 200
        # unmapped real identity stays denied through the complete composition root.
        assert (
            client.get(
                "/v1/me", headers={"Authorization": "Bearer " + tokens["unmapped"]["access_token"]}
            ).status_code
            == 403
        )


def test_actual_cli_create_grant_revoke_disable_commits_audit(pg, tmp_path, monkeypatch, capsys):
    file = tmp_path / "provisioner.dsn"
    file.write_text(pg["engines"]["provisioner"].url.render_as_string(hide_password=False))
    subject = uuid4().hex
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "provision",
            "create",
            "--dsn-file",
            str(file),
            "--issuer",
            "https://cli.invalid",
            "--subject",
            subject,
        ],
    )
    assert provision() == 0
    principal_id = UUID(capsys.readouterr().out.strip())
    for action in ("grant", "revoke", "disable"):
        args = ["provision", action, "--dsn-file", str(file), "--principal-id", str(principal_id)]
        if action != "disable":
            args += ["--role", "operator"]
        monkeypatch.setattr(sys, "argv", args)
        assert provision() == 0
        capsys.readouterr()
    with pg["engines"]["app"].connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit_events WHERE stream_id=:id"), {"id": principal_id}
            ).scalar_one()
            == 4
        )
        assert not connection.execute(
            text("SELECT enabled FROM principals WHERE id=:id"), {"id": principal_id}
        ).scalar_one()
