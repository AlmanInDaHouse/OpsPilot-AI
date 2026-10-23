"""PostgreSQL intake ports bound to the existing transaction implementation."""

from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from opspilot.adapters.postgres.audit import PostgresWorkflowAppender
from opspilot.adapters.postgres.database import PostgresUow
from opspilot.adapters.postgres.models import GrantRow, IdempotencyRow, PrincipalRow
from opspilot.audit.domain.envelope import canonical_bytes
from opspilot.incidents.application.create import IntakeRepository
from opspilot.incidents.domain.intake import (
    ROUTE,
    IdempotencyRace,
    IncidentAccepted,
    IncidentInput,
    StoredAcceptance,
)
from opspilot.shared.errors import DependencyUnavailable, Forbidden


class PostgresIncidents:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_operator(self, principal_id: UUID) -> None:
        allowed = self.session.execute(
            select(PrincipalRow.id)
            .join(GrantRow)
            .where(
                PrincipalRow.id == principal_id,
                PrincipalRow.enabled.is_(True),
                GrantRow.role == "operator",
                GrantRow.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if allowed is None:
            raise Forbidden()

    def find(self, principal_id: UUID, key: UUID) -> StoredAcceptance | None:
        row = self.session.get(IdempotencyRow, (principal_id, ROUTE, key))
        if row is None:
            return None
        return StoredAcceptance(
            row.request_hash,
            IncidentAccepted(
                UUID(row.response_body["incident_id"]), UUID(row.response_body["workflow_id"])
            ),
        )

    def create(self, principal_id: UUID, body: IncidentInput) -> IncidentAccepted:
        result = IncidentAccepted(uuid4(), uuid4())
        values = {
            "incident": result.incident_id,
            "workflow": result.workflow_id,
            "creator": principal_id,
            "title": body.title,
            "description": body.description,
            "step": uuid4(),
            "job": uuid4(),
        }
        # Explicit sequence respects immediate composite foreign keys and needs no ORM flush.
        for statement in (
            "INSERT INTO incidents(id,creator_id,title,description) VALUES(:incident,:creator,:title,:description)",
            "INSERT INTO workflows(id,incident_id,creator_id) VALUES(:workflow,:incident,:creator)",
            "INSERT INTO workflow_steps(id,workflow_id,step_key) VALUES(:step,:workflow,'intake_snapshot')",
            "INSERT INTO jobs(id,workflow_id,step_id,kind) VALUES(:job,:workflow,:step,'intake_snapshot')",
        ):
            self.session.execute(text(statement), values)
        return result

    def audit(self, principal_id: UUID, result: IncidentAccepted, trace_id: str) -> None:
        PostgresWorkflowAppender(self.session).append(
            result.incident_id,
            "incident.created",
            principal_id,
            trace_id,
            {
                "reason_code": "INTAKE_ACCEPTED",
                "aggregate_id": str(result.incident_id),
                "aggregate_version": 1,
                "evidence_ids": [],
            },
        )

    def remember(
        self, principal_id: UUID, key: UUID, request_hash: str, result: IncidentAccepted
    ) -> None:
        try:
            self.session.execute(
                text("""INSERT INTO api_idempotency
                (principal_id,route,key,request_hash,response_status,response_body,incident_id,workflow_id)
                VALUES(:principal,:route,:key,:hash,202,CAST(:body AS jsonb),:incident,:workflow)"""),
                {
                    "principal": principal_id,
                    "route": ROUTE,
                    "key": key,
                    "hash": request_hash,
                    "body": canonical_bytes(result.body()).decode("utf-8"),
                    "incident": result.incident_id,
                    "workflow": result.workflow_id,
                },
            )
        except IntegrityError as exc:
            original = exc.orig
            if (
                getattr(original, "sqlstate", None) == "23505"
                and getattr(getattr(original, "diag", None), "constraint_name", None)
                == "api_idempotency_pkey"
            ):
                raise IdempotencyRace() from exc
            raise


class PostgresIntakeUow(PostgresUow):
    """Bind intake ports, retaining PostgresUow's begin/commit/rollback/close."""

    incidents: IntakeRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.incidents = PostgresIncidents(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)
        if isinstance(exc, SQLAlchemyError):
            raise DependencyUnavailable() from exc
