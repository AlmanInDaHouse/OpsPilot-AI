"""Strict transport schemas; entities and ORM models never cross HTTP boundaries."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from opspilot.identity.domain.principal import Role


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Health(DTO):
    status: Literal["ok"] = "ok"


class Error(DTO):
    code: Literal["UNAUTHENTICATED", "FORBIDDEN", "INVALID_REQUEST", "DEPENDENCY_UNAVAILABLE"]
    request_id: UUID


class Me(DTO):
    principal_id: UUID
    roles: list[Role]


class AuditPayload(DTO):
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    aggregate_id: UUID
    aggregate_version: int = Field(ge=0)
    evidence_ids: list[UUID] = Field(max_length=20)


class AuditEvent(DTO):
    event_id: UUID
    stream_id: UUID
    seq: int = Field(ge=1)
    event_type: Literal[
        "identity.provisioned",
        "identity.disabled",
        "authorization.granted",
        "authorization.revoked",
        "authorization.denied",
    ]
    schema_version: Literal[1]
    occurred_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    actor_id: UUID | None
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    payload: AuditPayload


class AuditPage(DTO):
    items: list[AuditEvent] = Field(max_length=100)
    next_after_seq: int = Field(ge=0)
