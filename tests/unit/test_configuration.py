"""Reject insecure configuration before constructing any external clients."""

import pytest
from pydantic import ValidationError

from opspilot.entrypoints.settings import Settings


def configuration(tmp_path, **changes):
    file = tmp_path / "credentials"
    file.write_text(
        "postgresql+psycopg://opspilot_app:unit-only-password@127.0.0.1:59432/opspilot_lab",  # pragma: allowlist secret (synthetic configuration)
        encoding="utf-8",
    )
    values = {
        "environment": "lab",
        "database_dsn_file": file,
        "oidc_issuer": "http://127.0.0.1:59080/realms/opspilot",
        "oidc_audience": "api",
        "oidc_jwks_url": "http://127.0.0.1:59080/realms/opspilot/certs",
        **changes,
    }
    return values


def test_lab_configuration_redacts_secret_repr(tmp_path):
    settings = Settings(**configuration(tmp_path))
    assert "unit-only-password" not in repr(settings)
    assert "unit-only-password" not in repr(settings.database_dsn)


@pytest.mark.parametrize(
    "changes",
    [
        {"environment": "production"},
        {"oidc_issuer": "http://attacker.invalid/realm"},
        {"oidc_issuer": "https://idp.invalid/realm/"},
        {"oidc_audience": ""},
        {"jwks_ttl_seconds": 301},
        {"jwks_refresh_seconds": 1},
        {"oidc_jwks_url": "file:///etc/secrets"},
        {
            "oidc_jwks_url": "https://user:password@idp.invalid/certs"  # pragma: allowlist secret (invalid URL fixture)
        },  # pragma: allowlist secret (invalid URL fixture)
        {"http_timeout_seconds": 0},
    ],
)
def test_insecure_settings_rejected(tmp_path, changes):
    with pytest.raises(ValidationError):
        Settings(**configuration(tmp_path, **changes))


def test_superuser_dsn_rejected(tmp_path):
    values = configuration(tmp_path)
    values["database_dsn_file"].write_text(
        "postgresql+psycopg://postgres:unit-only-password@localhost/opspilot_lab"  # pragma: allowlist secret (synthetic configuration)
    )
    with pytest.raises(ValidationError) as raised:
        Settings(**values)
    assert "unit-only-password" not in str(raised.value)


def test_production_requires_verified_database_tls(tmp_path):
    values = configuration(
        tmp_path,
        environment="production",
        oidc_issuer="https://idp.invalid/realm",
        oidc_jwks_url="https://idp.invalid/certs",
    )
    with pytest.raises(ValidationError):
        Settings(**values)
    values["database_dsn_file"].write_text(
        "postgresql+psycopg://opspilot_app:unit-only-password@db.invalid/opspilot?sslmode=verify-full"  # pragma: allowlist secret (synthetic configuration)
    )
    assert Settings(**values).environment == "production"
