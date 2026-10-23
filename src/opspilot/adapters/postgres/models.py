"""Persistence mappings; schema changes are exclusively Alembic migrations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = "0001_platform"


class Base(DeclarativeBase):
    pass


class PrincipalRow(Base):
    __tablename__ = "principals"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_principal_external"),
        CheckConstraint(
            "length(issuer) BETWEEN 1 AND 2048 AND length(subject) BETWEEN 1 AND 255",
            name="ck_identity_lengths",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )


class GrantRow(Base):
    __tablename__ = "role_grants"
    __table_args__ = (
        CheckConstraint("role IN ('operator','approver','auditor','admin')", name="ck_role"),
        CheckConstraint("version >= 1", name="ck_grant_version"),
    )
    principal_id: Mapped[UUID] = mapped_column(ForeignKey("principals.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StreamRow(Base):
    __tablename__ = "audit_streams"
    __table_args__ = (
        CheckConstraint("last_seq >= 0 AND last_hash ~ '^[0-9a-f]{64}$'", name="ck_stream_head"),
    )
    stream_id: Mapped[UUID] = mapped_column(primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger)
    last_hash: Mapped[str] = mapped_column(String(64))


class EventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("stream_id", "seq", name="uq_audit_stream_seq"),
        CheckConstraint("seq >= 1 AND schema_version = 1", name="ck_audit_version_seq"),
        CheckConstraint(
            "prev_hash ~ '^[0-9a-f]{64}$' AND hash ~ '^[0-9a-f]{64}$'", name="ck_audit_hash"
        ),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_audit_trace"),
        CheckConstraint(
            "event_type IN ('identity.provisioned','identity.disabled','authorization.granted','authorization.revoked','authorization.denied')",
            name="ck_audit_type",
        ),
    )
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    stream_id: Mapped[UUID] = mapped_column(ForeignKey("audit_streams.stream_id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("principals.id"))
    trace_id: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
