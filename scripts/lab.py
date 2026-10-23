"""Isolated S02 lab lifecycle. Secret values never appear in command arguments/output."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.audit import PostgresAppender
from opspilot.adapters.postgres.database import PostgresUow, make_engine
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.identity.application.provision import change_identity, create_identity
from opspilot.identity.domain.principal import Role

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "artifacts/local"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/compose.yaml")]
ISSUER = "http://127.0.0.1:59080/realms/opspilot"


def private_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(value + "\n")
    if os.name != "nt":
        path.chmod(0o600)


def protect_windows_lab() -> None:
    """Replace inherited broad ACLs on this task-owned directory, without elevation."""
    target = LOCAL.resolve()
    if not target.is_relative_to(ROOT.resolve()) or target != ROOT.resolve() / "artifacts/local":
        raise ValueError("Private directory must remain inside this repository")
    # PowerShell single-quote escaping, not JSON or shell interpolation. This is
    # fixed local maintenance code and never receives credentials or HTTP input.
    literal = "'" + str(target).replace("'", "''") + "'"
    command = (
        "$labPath = "
        + literal
        + r"""
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$labAcl = Get-Acl -LiteralPath $labPath
$ownerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$allowedSids = @($ownerSid.Value, 'S-1-5-18', 'S-1-5-32-544')
$icacls = Join-Path $env:SystemRoot 'System32/icacls.exe'
$ownerGrant = '*' + $ownerSid.Value + ':(OI)(CI)F'
# icacls modifies DACL only. Set-Acl may try to persist SACL metadata and demand
# SeSecurityPrivilege on an already protected directory; no elevation is needed.
& $icacls $labPath '/grant:r' $ownerGrant '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant private directory owner access' }
& $icacls $labPath '/inheritance:r' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect private directory inheritance' }
foreach ($oldRule in $labAcl.Access) {
    $oldSid = $oldRule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if (-not $oldRule.IsInherited -and $oldRule.AccessControlType -eq 'Allow' -and $oldSid -notin $allowedSids) {
        & $icacls $labPath '/remove:g' ('*' + $oldSid) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cannot remove broad private directory access' }
    }
}
# File ACLs matter as well: Windows grants traverse bypass to normal users.
$items = @(Get-Item -LiteralPath $labPath) + @(Get-ChildItem -LiteralPath $labPath -File -Force)
foreach ($item in $items) {
    $effectiveAcl = Get-Acl -LiteralPath $item.FullName
    foreach ($entry in $effectiveAcl.Access) {
        $entrySid = $entry.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($entry.AccessControlType -eq 'Allow' -and $entrySid -notin $allowedSids) {
            throw 'Unexpected access on private lab data'
        }
    }
}
"""
    )
    subprocess.run(
        [
            shutil.which("pwsh") or "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def initialize() -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        protect_windows_lab()
    else:
        LOCAL.chmod(0o700)
    for name in (
        "pg_admin",
        "pg_migrator",
        "pg_app",
        "pg_provisioner",
        "pg_worker",
        "kc_admin",
        "kc_db",
    ):
        if not (LOCAL / name).exists():
            private_file(LOCAL / name, secrets.token_urlsafe(32))
        if os.name != "nt" and name in {"pg_admin", "kc_admin", "kc_db"}:
            # Parent 0700 protects the host; individual readonly secret mounts must
            # be readable by the non-root service UID on Linux as well as Desktop.
            (LOCAL / name).chmod(0o444)
    for role, filename in (
        ("opspilot_app", "app"),
        ("opspilot_migrator", "migration"),
        ("opspilot_provisioner", "provisioner"),
        ("opspilot_worker", "worker"),
        ("postgres", "admin"),
    ):
        secret_name = {
            "opspilot_app": "pg_app",
            "opspilot_migrator": "pg_migrator",
            "opspilot_provisioner": "pg_provisioner",
            "opspilot_worker": "pg_worker",
            "postgres": "pg_admin",
        }[role]
        password = (LOCAL / secret_name).read_text(encoding="utf-8").strip()
        for internal in (False, True):
            name = f"{filename}{'-internal' if internal else ''}.dsn"
            if not (LOCAL / name).exists():
                dsn = URL.create(
                    "postgresql+psycopg",
                    username=role,
                    password=password,
                    host="postgres" if internal else "127.0.0.1",
                    port=5432 if internal else 59432,
                    database="postgres" if role == "postgres" else "opspilot_lab",
                )
                private_file(LOCAL / name, dsn.render_as_string(hide_password=False))
            if os.name != "nt" and name == "app-internal.dsn":
                (LOCAL / name).chmod(0o444)
    print("Lab credential files prepared (existing files preserved).")


def connection(filename: str = "admin", database: str = "postgres") -> psycopg.Connection:
    dsn = make_url((LOCAL / f"{filename}.dsn").read_text(encoding="utf-8").strip())
    return psycopg.connect(
        host=dsn.host,
        port=dsn.port,
        user=dsn.username,
        password=dsn.password,
        dbname=database,
        autocommit=True,
        connect_timeout=3,
    )


def bootstrap() -> None:
    with connection() as conn:
        roles = [
            ("opspilot_migrator", "pg_migrator"),
            ("opspilot_app", "pg_app"),
            ("opspilot_provisioner", "pg_provisioner"),
            ("opspilot_worker", "pg_worker"),
            ("opspilot_keycloak", "kc_db"),
        ]
        for role, secret_file in roles:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
                    ).format(
                        sql.Identifier(role),
                        sql.Literal((LOCAL / secret_file).read_text(encoding="utf-8").strip()),
                    )
                )
        if not conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='opspilot_audit_owner'"
        ).fetchone():
            conn.execute(
                "CREATE ROLE opspilot_audit_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
        conn.execute("GRANT opspilot_audit_owner TO opspilot_migrator")
        # This dedicated Compose cluster is exclusively synthetic lab. Runtime
        # logins must not inherit PUBLIC CONNECT/TEMP on the default databases.
        for database in ("postgres", "template1"):
            conn.execute(
                sql.SQL("REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(database)
                )
            )
        for database, owner in (
            ("opspilot_lab", "opspilot_migrator"),
            ("opspilot_keycloak", "opspilot_keycloak"),
        ):
            if not conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (database,)
            ).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0"
                    ).format(sql.Identifier(database), sql.Identifier(owner))
                )
            conn.execute(
                sql.SQL("REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(database)
                )
            )
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database), sql.Identifier(owner)
                )
            )
        conn.execute(
            "GRANT CONNECT ON DATABASE opspilot_lab TO opspilot_app,opspilot_provisioner,opspilot_worker"
        )
    print("Dedicated lab roles and databases ready.")


def migrate() -> int:
    env = {**os.environ, "OPSPILOT_MIGRATION_DSN_FILE": str(LOCAL / "migration.dsn")}
    return subprocess.run(
        ["uv", "run", "--frozen", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=False
    ).returncode


def provision_idp() -> None:
    base = "http://127.0.0.1:59080"
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.post(
            f"{base}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": "lab-admin",
                "password": (LOCAL / "kc_admin").read_text(encoding="utf-8").strip(),
            },
        )
        response.raise_for_status()
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        accounts = []
        accounts_file = LOCAL / "accounts.json"
        if accounts_file.exists():
            accounts = json.loads(accounts_file.read_text(encoding="utf-8"))
        else:
            for name in ("operator", "auditor", "admin", "approver", "unmapped"):
                accounts.append(
                    {
                        "username": f"test-{name}",
                        "password": secrets.token_urlsafe(24),
                        "role": name,
                    }
                )
            private_file(accounts_file, json.dumps(accounts))
        engine = make_engine((LOCAL / "provisioner.dsn").read_text(encoding="utf-8").strip())
        try:
            for account in accounts:
                users_url = f"{base}/admin/realms/opspilot/users"
                found = client.get(
                    users_url,
                    headers=headers,
                    params={"username": account["username"], "exact": "true"},
                )
                found.raise_for_status()
                if not found.json():
                    result = client.post(
                        users_url,
                        headers=headers,
                        json={
                            "username": account["username"],
                            "enabled": True,
                            "emailVerified": True,
                            "firstName": "Synthetic",
                            "lastName": account["role"],
                            "email": f"{account['username']}@opspilot.invalid",
                            "credentials": [
                                {
                                    "type": "password",
                                    "value": account["password"],
                                    "temporary": False,
                                }
                            ],
                        },
                    )
                    result.raise_for_status()
                    found = client.get(
                        users_url,
                        headers=headers,
                        params={"username": account["username"], "exact": "true"},
                    )
                    found.raise_for_status()
                account["subject"] = found.json()[0]["id"]
                if account["role"] != "unmapped":
                    with PostgresUow(sessionmaker(engine)) as uow:
                        writer, audit = IdentityWriter(uow.session), PostgresAppender(uow.session)
                        pid = create_identity(
                            writer, audit, ISSUER, account["subject"], uuid4().hex
                        )
                        change_identity(
                            writer, audit, pid, "grant", Role(account["role"]), uuid4().hex
                        )
                        uow.commit()
                        account["principal_id"] = str(pid)
            # This ignored file is generated by this script and retains its original passwords.
            accounts_file.write_text(json.dumps(accounts) + "\n", encoding="utf-8")
        finally:
            engine.dispose()
    print("Synthetic Keycloak users and explicit local grants ready; PKCE client only.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "init",
            "postgres",
            "bootstrap",
            "migrate",
            "identity",
            "provision",
            "up",
            "stop",
            "config",
        ],
    )
    args = parser.parse_args()
    if args.action == "init":
        initialize()
    elif args.action == "bootstrap":
        bootstrap()
    elif args.action == "provision":
        provision_idp()
    elif args.action == "migrate":
        return migrate()
    else:
        command = {
            "postgres": ["up", "-d", "--build", "--wait", "postgres"],
            "identity": ["up", "-d", "--build", "--wait", "keycloak"],
            "up": ["up", "-d", "--build", "--wait", "api"],
            "stop": ["stop"],
            "config": ["config", "--quiet"],
        }[args.action]
        return subprocess.run([*COMPOSE, *command], cwd=ROOT, check=False).returncode
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(
            "Lab operation failed. No credentials or dependency details printed.", file=sys.stderr
        )
        raise SystemExit(1) from None
