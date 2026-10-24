"""Real PG18 and Keycloak fixtures. Missing services fail; no integration skips."""

import base64
import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.oidc.verifier import OidcVerifier
from opspilot.adapters.postgres.audit import PostgresAppender, PostgresAuditReader
from opspilot.adapters.postgres.database import (
    PostgresUow,
    database_ready,
    make_engine,
    require_database,
)
from opspilot.adapters.postgres.identity import IdentityWriter, PostgresPrincipals
from opspilot.adapters.postgres.incidents import PostgresIntakeUow
from opspilot.adapters.postgres.workflows import PostgresAccessUow
from opspilot.entrypoints.api.app import platform_api
from opspilot.identity.application.provision import change_identity, create_identity
from opspilot.identity.domain.principal import Role
from opspilot.incidents.application.create import CreateIncident
from opspilot.workflows.application.access import WorkflowAccess

ROOT = Path(__file__).resolve().parents[2]
LOCAL = Path(os.environ.get("OPSPILOT_LAB_DIR", ROOT / "artifacts/local"))
INTERNAL = os.environ.get("OPSPILOT_LAB_INTERNAL") == "1"
ISSUER = "http://127.0.0.1:59080/realms/opspilot"
IDP_BASE = "http://keycloak:8080" if INTERNAL else "http://127.0.0.1:59080"


def dsn_for(role, database=None):
    suffix = "-internal" if INTERNAL else ""
    path = LOCAL / f"{role}{suffix}.dsn"
    if not path.is_file():
        pytest.fail("Real lab not initialized: run scripts/dev.py infra; integration cannot skip")
    url = make_url(path.read_text(encoding="utf-8").strip())
    if database:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


def raw_connection(dsn, autocommit=True):
    url = make_url(dsn)
    return psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
        autocommit=autocommit,
        connect_timeout=3,
    )


@contextmanager
def postgres_database(revision="head"):
    database = "opspilot_test_" + uuid4().hex
    admin = raw_connection(dsn_for("admin"))
    assert int(admin.execute("SHOW server_version_num").fetchone()[0]) // 10000 == 18
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER opspilot_migrator TEMPLATE template0").format(
            sql.Identifier(database)
        )
    )
    admin.execute(
        sql.SQL("REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC").format(
            sql.Identifier(database)
        )
    )
    admin.execute(
        sql.SQL(
            "GRANT CONNECT ON DATABASE {} TO opspilot_app,opspilot_provisioner,opspilot_migrator,opspilot_worker"
        ).format(sql.Identifier(database))
    )
    dsnfile = LOCAL / f"{database}.dsn"
    dsnfile.write_text(dsn_for("migration", database), encoding="utf-8")
    if os.name != "nt":
        dsnfile.chmod(0o600)
    cfg = Config(str(ROOT / "alembic.ini"))
    engines = {}
    try:
        with patch.dict(os.environ, {"OPSPILOT_MIGRATION_DSN_FILE": str(dsnfile)}):
            command.upgrade(cfg, revision)
            if revision == "head":
                command.check(cfg)
        for role in ("app", "worker", "provisioner", "migration", "admin"):
            engines[role] = make_engine(dsn_for(role, database))
        yield {
            "database": database,
            "engines": engines,
            "config": cfg,
            "dsnfile": dsnfile,
            "sessions": {role: sessionmaker(engine) for role, engine in engines.items()},
        }
    finally:
        for engine in engines.values():
            engine.dispose()
        # Only this fixture's uniquely created database can be removed.
        assert database.startswith("opspilot_test_") and len(database) == 46
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        admin.close()
        dsnfile.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def pg():
    with postgres_database() as database:
        yield database


@pytest.fixture
def pg_factory():
    return postgres_database


@pytest.fixture(scope="session")
def accounts():
    path = LOCAL / "accounts.json"
    if not path.exists():
        pytest.fail("Real Keycloak users not provisioned; integration cannot skip")
    result = {row["role"]: row for row in json.loads(path.read_text(encoding="utf-8"))}
    assert all("subject" in row for row in result.values()), (
        "Run lab provision after IdP is healthy"
    )
    return result


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.action = None
        self.hidden = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values.get("action")
        if tag == "input" and values.get("type") == "hidden" and values.get("name"):
            self.hidden[values["name"]] = values.get("value", "")


def pkce_tokens(account, wrong_verifier=False):
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    redirect = "http://127.0.0.1:59081/callback"
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get(
            IDP_BASE + "/realms/opspilot/protocol/openid-connect/auth",
            params={
                "client_id": "opspilot-lab-pkce",
                "response_type": "code",
                "redirect_uri": redirect,
                "scope": "openid",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        response.raise_for_status()
        form = LoginForm()
        form.feed(response.text)
        assert form.action, "Keycloak did not offer the real login form"
        # Browsers allow Secure cookies on loopback HTTP. HTTPX does not implement
        # that localhost exception. This lab-only user agent mirrors it, on the
        # preconfigured local IdP origin, while retaining the actual PKCE exchange.
        for cookie in client.cookies.jar:
            cookie.secure = False
        action = urlsplit(form.action)
        assert action.scheme == "http" and action.netloc == "127.0.0.1:59080"
        login_url = IDP_BASE + urlunsplit(("", "", action.path, action.query, ""))
        response = client.post(
            login_url,
            data={
                **form.hidden,
                "username": account["username"],
                "password": account["password"],
                "credentialId": "",
            },
        )
        assert response.status_code == 302, "Keycloak login did not complete"
        location = urlsplit(response.headers["location"])
        assert urlunsplit((location.scheme, location.netloc, location.path, "", "")) == redirect
        query = parse_qs(location.query)
        assert query.get("state") == [state]
        assert "code" in query, "Keycloak authorization code missing"
        exchanged = client.post(
            IDP_BASE + "/realms/opspilot/protocol/openid-connect/token",
            data={
                "client_id": "opspilot-lab-pkce",
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": redirect,
                "code_verifier": "wrong-verifier-for-negative-test-0123456789abcdef"
                if wrong_verifier
                else verifier,
            },
        )
        if wrong_verifier:
            assert exchanged.status_code == 400
            return exchanged.json()
        exchanged.raise_for_status()
        return exchanged.json()


@pytest.fixture(scope="session")
def tokens(accounts):
    return {role: pkce_tokens(account) for role, account in accounts.items()}


@pytest.fixture(scope="session")
def mapped(pg, accounts):
    principals = {}
    for role, account in accounts.items():
        if role == "unmapped":
            continue
        with PostgresUow(pg["sessions"]["provisioner"]) as uow:
            writer, audit = IdentityWriter(uow.session), PostgresAppender(uow.session)
            pid = create_identity(writer, audit, ISSUER, account["subject"], uuid4().hex)
            change_identity(writer, audit, pid, "grant", Role(role), uuid4().hex)
            uow.commit()
        principals[role] = pid
    return principals


@pytest.fixture
def api(pg, mapped):
    with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as http:
        verifier = OidcVerifier(
            ISSUER,
            "opspilot-api",
            IDP_BASE + "/realms/opspilot/protocol/openid-connect/certs",
            http,
        )
        engine = pg["engines"]["app"]
        app = platform_api(
            verifier,
            PostgresPrincipals(pg["sessions"]["app"]),
            PostgresAuditReader(pg["sessions"]["app"]),
            lambda: database_ready(engine) and verifier.ready(),
            lambda: require_database(engine),
            intake=CreateIncident(lambda: PostgresIntakeUow(pg["sessions"]["app"])),
            access=WorkflowAccess(lambda: PostgresAccessUow(pg["sessions"]["app"])),
        )
        with TestClient(app) as client:
            yield client
