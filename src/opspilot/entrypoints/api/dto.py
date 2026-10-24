"""Strict transport schemas; entities and ORM models never cross HTTP boundaries."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opspilot.identity.domain.principal import Role
from opspilot.incidents.domain.intake import IncidentInput


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


class CreateIncidentInput(DTO):
    title: str = Field(strict=True, min_length=1, max_length=200)
    description: str = Field(strict=True, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def valid_unicode(self) -> Self:
        IncidentInput(self.title, self.description)
        return self


class IncidentAcceptedDTO(DTO):
    incident_id: UUID
    workflow_id: UUID


class IncidentDTO(IncidentAcceptedDTO):
    creator_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    status: Literal["OPEN"]
    version: int = Field(ge=1, le=9223372036854775807)


class ResourceError(DTO):
    code: Literal[
        "UNAUTHENTICATED", "FORBIDDEN", "NOT_FOUND", "INVALID_REQUEST", "DEPENDENCY_UNAVAILABLE"
    ]
    request_id: UUID


class CancelConflict(DTO):
    code: Literal["VERSION_CONFLICT", "TERMINAL_WORKFLOW"]
    request_id: UUID


class IntakeConflict(DTO):
    code: Literal["IDEMPOTENCY_CONFLICT"]
    request_id: UUID


class AuditPayload(DTO):
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    aggregate_id: UUID
    aggregate_version: int = Field(ge=0)
    evidence_ids: list[UUID] = Field(max_length=20)


class AuditEnvelope(DTO):
    event_id: UUID
    stream_id: UUID
    seq: int = Field(ge=1)
    occurred_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    actor_id: UUID | None
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")

    @field_validator("occurred_at")
    @classmethod
    def valid_timestamp(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return value


class AuditEvent(AuditEnvelope):
    event_type: Literal[
        "identity.provisioned",
        "identity.disabled",
        "authorization.granted",
        "authorization.revoked",
        "authorization.denied",
    ]
    schema_version: Literal[1]
    payload: AuditPayload


WorkflowState = Literal[
    "QUEUED",
    "INVESTIGATING",
    "PLAN_READY",
    "AWAITING_APPROVAL",
    "EXECUTING",
    "VERIFYING",
    "RETRY_WAIT",
    "OUTCOME_UNKNOWN",
    "NEEDS_OPERATOR",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
]


class EvidenceRef(DTO):
    evidence_id: UUID
    kind: Literal["INCIDENT_SNAPSHOT_V1"]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    collector_id: Literal["local-intake-v1"]
    source_ref: str = Field(
        pattern=r"^incident:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}:v[1-9][0-9]{0,18}$"
    )
    independence_role: Literal["INTAKE_SNAPSHOT"]


class WorkflowDTO(DTO):
    workflow_id: UUID
    incident_id: UUID
    state: WorkflowState
    version: int = Field(ge=1, le=9223372036854775807)
    definition_version: int = Field(ge=1)
    cancel_requested_at: datetime | None
    reason_code: Literal[
        "INTAKE_ACCEPTED",
        "LOCAL_STEP_STARTED",
        "LOCAL_SNAPSHOT_RECORDED",
        "TRANSIENT_LOCAL_FAILURE",
        "RETRY_READY",
        "DEADLINE_EXHAUSTED",
        "RETRY_EXHAUSTED",
        "PERMANENT_LOCAL_FAILURE",
        "UNSUPPORTED_DEFINITION",
        "CANCELLED_BY_OPERATOR",
        "CANCEL_REQUESTED",
    ]
    evidence: list[EvidenceRef] = Field(max_length=1)


class CancelAcceptedDTO(DTO):
    workflow_id: UUID
    state: Literal["CANCELLED", "EXECUTING", "VERIFYING", "OUTCOME_UNKNOWN"]
    version: int = Field(ge=1, le=9223372036854775807)
    cancel_requested_at: datetime


class WorkflowTransition(DTO):
    from_: WorkflowState = Field(alias="from")
    to: WorkflowState
    definition_version: int = Field(ge=1)


class IncidentCreatedPayload(DTO):
    reason_code: Literal["INTAKE_ACCEPTED"]
    aggregate_id: UUID
    aggregate_version: Literal[1]
    evidence_ids: list[UUID] = Field(max_length=0)


class WorkflowTransitionPayload(DTO):
    reason_code: Literal[
        "LOCAL_STEP_STARTED",
        "LOCAL_SNAPSHOT_RECORDED",
        "TRANSIENT_LOCAL_FAILURE",
        "RETRY_READY",
        "DEADLINE_EXHAUSTED",
        "RETRY_EXHAUSTED",
        "PERMANENT_LOCAL_FAILURE",
        "CANCELLED_BY_OPERATOR",
    ]
    aggregate_id: UUID
    aggregate_version: int = Field(ge=2, le=9223372036854775807)
    evidence_ids: list[UUID] = Field(max_length=1)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)
    transition: WorkflowTransition

    @model_validator(mode="after")
    def checked_edge(self) -> Self:
        source, target = self.transition.from_, self.transition.to
        edges = {
            "LOCAL_STEP_STARTED": {("QUEUED", "INVESTIGATING")},
            "LOCAL_SNAPSHOT_RECORDED": {("INVESTIGATING", "NEEDS_OPERATOR")},
            "TRANSIENT_LOCAL_FAILURE": {("INVESTIGATING", "RETRY_WAIT")},
            "RETRY_READY": {("RETRY_WAIT", "INVESTIGATING")},
            "DEADLINE_EXHAUSTED": {
                ("QUEUED", "FAILED"),
                ("INVESTIGATING", "NEEDS_OPERATOR"),
                ("RETRY_WAIT", "NEEDS_OPERATOR"),
            },
            "RETRY_EXHAUSTED": {("INVESTIGATING", "NEEDS_OPERATOR")},
            "PERMANENT_LOCAL_FAILURE": {("INVESTIGATING", "NEEDS_OPERATOR")},
            "CANCELLED_BY_OPERATOR": {
                (state, "CANCELLED")
                for state in (
                    "QUEUED",
                    "INVESTIGATING",
                    "PLAN_READY",
                    "AWAITING_APPROVAL",
                    "RETRY_WAIT",
                    "NEEDS_OPERATOR",
                )
            },
        }
        if (source, target) not in edges[self.reason_code]:
            raise ValueError("Invalid workflow edge")
        if self.reason_code != "CANCELLED_BY_OPERATOR" and self.transition.definition_version != 1:
            raise ValueError("Unknown definition")
        if len(self.evidence_ids) != (1 if self.reason_code == "LOCAL_SNAPSHOT_RECORDED" else 0):
            raise ValueError("Invalid evidence references")
        return self


class WorkflowStatePayload(DTO):
    reason_code: Literal["CANCEL_REQUESTED", "UNSUPPORTED_DEFINITION"]
    aggregate_id: UUID
    aggregate_version: int = Field(ge=2, le=9223372036854775807)
    evidence_ids: list[UUID] = Field(max_length=0)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)


class WorkflowAuditEvent(AuditEnvelope):
    schema_version: Literal[2]
    event_type: Literal[
        "incident.created", "workflow.transitioned", "workflow.cancel_requested", "workflow.blocked"
    ]
    payload: IncidentCreatedPayload | WorkflowTransitionPayload | WorkflowStatePayload

    @model_validator(mode="after")
    def checked_family(self) -> Self:
        reason = self.payload.reason_code
        expected = (
            "incident.created"
            if reason == "INTAKE_ACCEPTED"
            else "workflow.cancel_requested"
            if reason == "CANCEL_REQUESTED"
            else "workflow.blocked"
            if reason == "UNSUPPORTED_DEFINITION"
            else "workflow.transitioned"
        )
        operator = reason in {"INTAKE_ACCEPTED", "CANCEL_REQUESTED", "CANCELLED_BY_OPERATOR"}
        if self.event_type != expected or operator != (self.actor_id is not None):
            raise ValueError("Invalid event family or actor")
        return self


class AuditPage(DTO):
    items: list[
        Annotated[AuditEvent | WorkflowAuditEvent, Field(discriminator="schema_version")]
    ] = Field(max_length=100)
    next_after_seq: int = Field(ge=0)
