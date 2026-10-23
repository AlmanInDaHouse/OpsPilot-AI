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
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = "0002_workflows"

WORKFLOW_STATES = "'QUEUED','INVESTIGATING','PLAN_READY','AWAITING_APPROVAL','EXECUTING','VERIFYING','RETRY_WAIT','OUTCOME_UNKNOWN','NEEDS_OPERATOR','SUCCEEDED','FAILED','CANCELLED'"
WORKFLOW_REASONS = "'INTAKE_ACCEPTED','LOCAL_STEP_STARTED','LOCAL_SNAPSHOT_RECORDED','TRANSIENT_LOCAL_FAILURE','RETRY_READY','DEADLINE_EXHAUSTED','RETRY_EXHAUSTED','PERMANENT_LOCAL_FAILURE','UNSUPPORTED_DEFINITION','CANCELLED_BY_OPERATOR','CANCEL_REQUESTED'"
AUDIT_TYPES_V1 = "'identity.provisioned','identity.disabled','authorization.granted','authorization.revoked','authorization.denied'"
AUDIT_TYPES_V2 = (
    "'incident.created','workflow.transitioned','workflow.cancel_requested','workflow.blocked'"
)


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
        CheckConstraint("seq >= 1 AND schema_version IN (1,2)", name="ck_audit_version_seq"),
        CheckConstraint(
            "prev_hash ~ '^[0-9a-f]{64}$' AND hash ~ '^[0-9a-f]{64}$'", name="ck_audit_hash"
        ),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_audit_trace"),
        CheckConstraint(
            f"(schema_version = 1 AND event_type IN ({AUDIT_TYPES_V1})) OR (schema_version = 2 AND event_type IN ({AUDIT_TYPES_V2}))",
            name="ck_audit_type",
        ),
        CheckConstraint(
            "((schema_version = 1 OR event_type = 'incident.created') AND state_snapshot IS NULL) OR (schema_version = 2 AND event_type <> 'incident.created' AND state_snapshot IS NOT NULL AND jsonb_typeof(state_snapshot) = 'object')",
            name="ck_audit_snapshot",
        ),
        Index(
            "uq_audit_v2_version",
            "stream_id",
            text("(payload ->> 'aggregate_version')"),
            unique=True,
            postgresql_where=text("schema_version = 2"),
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
    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class IncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("id", "creator_id", name="uq_incident_creator"),
        CheckConstraint(
            "length(title) BETWEEN 1 AND 200 AND length(description) BETWEEN 1 AND 4000",
            name="ck_incident_text",
        ),
        CheckConstraint("status = 'OPEN' AND version = 1", name="ck_incident_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    creator_id: Mapped[UUID] = mapped_column(ForeignKey("principals.id"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), server_default=text("'OPEN'"))
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class WorkflowRow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "creator_id"],
            ["incidents.id", "incidents.creator_id"],
            name="fk_workflow_incident_creator",
        ),
        UniqueConstraint("id", "incident_id", "creator_id", name="uq_workflow_incident_creator"),
        CheckConstraint(f"state IN ({WORKFLOW_STATES})", name="ck_workflow_state"),
        CheckConstraint(f"reason_code IN ({WORKFLOW_REASONS})", name="ck_workflow_reason"),
        CheckConstraint("version >= 1 AND definition_version >= 1", name="ck_workflow_version"),
        CheckConstraint(
            "budget_spent_ms BETWEEN 0 AND 300000 AND deadline_at > created_at",
            name="ck_workflow_budget",
        ),
        CheckConstraint(
            "(state = 'RETRY_WAIT' AND resume_state IS NOT NULL AND resume_state IN ('INVESTIGATING','PLAN_READY','VERIFYING')) OR (state <> 'RETRY_WAIT' AND resume_state IS NULL)",
            name="ck_workflow_resume",
        ),
        CheckConstraint(
            "state <> 'CANCELLED' OR cancel_requested_at IS NOT NULL", name="ck_workflow_cancel"
        ),
        Index(
            "uq_workflow_active_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("state NOT IN ('SUCCEEDED','FAILED','CANCELLED')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    incident_id: Mapped[UUID] = mapped_column()
    creator_id: Mapped[UUID] = mapped_column()
    definition_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    state: Mapped[str] = mapped_column(String(32), server_default=text("'QUEUED'"))
    resume_state: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("statement_timestamp() + interval '300 seconds'"),
    )
    budget_spent_ms: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason_code: Mapped[str] = mapped_column(String(64), server_default=text("'INTAKE_ACCEPTED'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_key", "kind", name="uq_evidence_step_kind"),
        UniqueConstraint("id", "workflow_id", name="uq_evidence_workflow"),
        CheckConstraint(
            "kind = 'INCIDENT_SNAPSHOT_V1' AND step_key = 'intake_snapshot' AND collector_id = 'local-intake-v1' AND independence_role = 'INTAKE_SNAPSHOT'",
            name="ck_evidence_kind",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND length(content_hash) = 64", name="ck_evidence_hash"
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > observed_at", name="ck_evidence_expiry"
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_evidence_payload"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    step_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    collector_id: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    independence_role: Mapped[str] = mapped_column(String(32))


class WorkflowStepRow(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_key", "attempt_no", name="uq_step_attempt"),
        UniqueConstraint("id", "workflow_id", name="uq_step_workflow"),
        ForeignKeyConstraint(
            ["evidence_id", "workflow_id"],
            ["evidence.id", "evidence.workflow_id"],
            name="fk_step_evidence_workflow",
        ),
        CheckConstraint(
            "step_key = 'intake_snapshot' AND attempt_no BETWEEN 1 AND 3",
            name="ck_step_key_attempt",
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','DONE','FAILED','CANCELLED')", name="ck_step_status"
        ),
        CheckConstraint(
            "input_hash IS NULL OR (length(input_hash) = 64 AND input_hash ~ '^[0-9a-f]{64}$')",
            name="ck_step_hash",
        ),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('TRANSIENT_LOCAL_FAILURE','PERMANENT_LOCAL_FAILURE','DEADLINE_EXHAUSTED','RETRY_EXHAUSTED','UNSUPPORTED_DEFINITION')",
            name="ck_step_error",
        ),
        CheckConstraint(
            "status <> 'DONE' OR (evidence_id IS NOT NULL AND input_hash IS NOT NULL AND error_code IS NULL)",
            name="ck_step_done",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    step_key: Mapped[str] = mapped_column(String(64))
    attempt_no: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PENDING'"))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_id: Mapped[UUID | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(64))


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["step_id", "workflow_id"],
            ["workflow_steps.id", "workflow_steps.workflow_id"],
            name="fk_job_step_workflow",
        ),
        CheckConstraint(
            "kind = 'intake_snapshot' AND state IN ('READY','LEASED','DONE','DEAD')",
            name="ck_job_state_kind",
        ),
        CheckConstraint("fence >= 0 AND attempts BETWEEN 0 AND 3", name="ck_job_counters"),
        CheckConstraint(
            "(state = 'LEASED' AND owner IS NOT NULL AND lease_until IS NOT NULL AND fence >= 1) OR (state <> 'LEASED' AND owner IS NULL AND lease_until IS NULL)",
            name="ck_job_ownership",
        ),
        Index("ix_job_available", "state", "available_at"),
        Index(
            "uq_job_active_workflow",
            "workflow_id",
            "kind",
            unique=True,
            postgresql_where=text("state IN ('READY','LEASED')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    step_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), server_default=text("'READY'"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[UUID | None] = mapped_column()
    fence: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class IdempotencyRow(Base):
    __tablename__ = "api_idempotency"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_id", "incident_id", "principal_id"],
            ["workflows.id", "workflows.incident_id", "workflows.creator_id"],
            name="fk_idempotency_workflow_incident",
        ),
        CheckConstraint(
            "route = '/v1/incidents' AND response_status = 202", name="ck_idempotency_route_status"
        ),
        CheckConstraint(
            "length(request_hash) = 64 AND request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_idempotency_hash",
        ),
        CheckConstraint(
            "response_body = jsonb_build_object('incident_id',incident_id::text,'workflow_id',workflow_id::text)",
            name="ck_idempotency_response",
        ),
    )
    principal_id: Mapped[UUID] = mapped_column(ForeignKey("principals.id"), primary_key=True)
    route: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[UUID] = mapped_column(primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"))
    workflow_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
