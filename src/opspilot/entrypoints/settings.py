"""Validated configuration. Secret files, never credential defaults."""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_", extra="forbid", hide_input_in_errors=True
    )

    environment: Literal["lab", "production"]
    database_dsn_file: Path
    oidc_issuer: str
    oidc_audience: str = Field(min_length=1, max_length=200)
    oidc_jwks_url: str
    jwks_ttl_seconds: int = Field(default=300, ge=1, le=300)
    jwks_refresh_seconds: int = Field(default=30, ge=30, le=300)
    http_timeout_seconds: float = Field(default=2.0, gt=0, le=3)
    db_timeout_ms: int = Field(default=1000, ge=100, le=1000)

    @model_validator(mode="after")
    def secure_configuration(self) -> Self:
        for value in (self.oidc_issuer, self.oidc_jwks_url):
            url = urlsplit(value)
            if (
                url.scheme not in {"https", "http"}
                or not url.hostname
                or url.username
                or url.password
                or url.fragment
                or url.query
            ):
                raise ValueError("Invalid OIDC endpoint")
            if url.scheme == "http" and (
                self.environment != "lab"
                or url.hostname
                not in {"localhost", "127.0.0.1", "keycloak", "host.docker.internal"}
            ):
                raise ValueError("OIDC requires HTTPS outside the explicit lab network")
        if self.oidc_issuer.endswith("/"):
            raise ValueError("Issuer must match exactly without trailing slash")
        dsn = make_url(self.database_dsn.get_secret_value())
        if dsn.drivername != "postgresql+psycopg" or dsn.username != "opspilot_app":
            raise ValueError("Application requires PostgreSQL psycopg and restricted app role")
        if not dsn.password or not dsn.host or not dsn.database:
            raise ValueError("Incomplete database configuration")
        if self.environment == "production" and dsn.query.get("sslmode") != "verify-full":
            raise ValueError("Production DB requires certificate and hostname verification")
        return self

    @property
    def database_dsn(self) -> SecretStr:
        return SecretStr(self.database_dsn_file.read_text(encoding="utf-8").strip())
