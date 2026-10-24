"""One PG transaction: workflow lock, ordered jobs, then existing v2 appender."""

import hashlib
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opspilot.adapters.postgres.audit import PostgresWorkflowAppender
from opspilot.adapters.postgres.database import PostgresUow
from opspilot.audit.domain.envelope import canonical_bytes
from opspilot.shared.errors import DependencyUnavailable, Forbidden
from opspilot.workflows.application.access import AccessRepository
from opspilot.workflows.domain.access import (
    AMBIGUOUS_STATES,
    SAFE_STATES,
    NotFound,
    TerminalWorkflow,
    VersionConflict,
    WorkflowTag,
)


def timestamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if value else None


class PostgresWorkflows:
    def __init__(self, session: Session) -> None:
        self.session = session

    def authorize(self, principal: UUID, cancel: bool = False) -> bool:
        roles = set(
            self.session.execute(
                text("""SELECT g.role FROM principals p
            JOIN role_grants g ON g.principal_id=p.id
            WHERE p.id=:principal AND p.enabled AND g.revoked_at IS NULL"""),
                {"principal": principal},
            ).scalars()
        )
        if not roles.intersection({"operator"} if cancel else {"operator", "auditor"}):
            raise Forbidden()
        return not cancel and "auditor" in roles

    def read(
        self, principal: UUID, resource: UUID, kind: Literal["incident", "workflow"]
    ) -> dict[str, Any]:
        self.authorize(principal)
        values = {"resource": resource, "principal": principal}
        # Re-evaluate grants with the resource snapshot, including revocation between statements.
        # Each projection (including evidence) comes from ONE statement snapshot.
        if kind == "incident":
            statement = """SELECT i.id AS incident_id,w.id AS workflow_id,i.creator_id,
                i.title,i.description,i.status,i.version FROM incidents i
                JOIN workflows w ON w.incident_id=i.id
                WHERE i.id=:resource AND EXISTS (
                    SELECT 1 FROM principals p JOIN role_grants g ON g.principal_id=p.id
                    WHERE p.id=:principal AND p.enabled AND g.revoked_at IS NULL
                    AND (g.role='auditor' OR (g.role='operator' AND w.creator_id=:principal)))
                ORDER BY w.created_at DESC,w.id DESC LIMIT 1"""
        else:
            statement = """SELECT w.id AS workflow_id,w.incident_id,w.state,w.version,
                w.definition_version,w.cancel_requested_at,w.reason_code,
                COALESCE((SELECT jsonb_agg(jsonb_build_object(
                    'evidence_id',e.id,'kind',e.kind,'content_hash',e.content_hash,
                    'observed_at',to_char(e.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                    'collector_id',e.collector_id,'source_ref',e.source_ref,
                    'independence_role',e.independence_role) ORDER BY e.id)
                    FROM evidence e WHERE e.workflow_id=w.id),'[]'::jsonb) AS evidence
                FROM workflows w WHERE w.id=:resource AND EXISTS (
                    SELECT 1 FROM principals p JOIN role_grants g ON g.principal_id=p.id
                    WHERE p.id=:principal AND p.enabled AND g.revoked_at IS NULL
                    AND (g.role='auditor' OR (g.role='operator' AND w.creator_id=:principal)))"""
        row = self.session.execute(text(statement), values).mappings().one_or_none()
        if row is None:
            raise NotFound()
        result = dict(row)
        if kind == "workflow":
            result["cancel_requested_at"] = timestamp(row["cancel_requested_at"])
        return result

    def cancel(
        self, principal: UUID, resource: UUID, tag: WorkflowTag, trace: str
    ) -> dict[str, Any]:
        self.authorize(principal, cancel=True)
        row = (
            self.session.execute(
                text("""SELECT id AS workflow_id,incident_id,state,version,
            definition_version,cancel_requested_at,reason_code FROM workflows
            WHERE id=:id AND creator_id=:principal FOR UPDATE"""),
                {"id": resource, "principal": principal},
            )
            .mappings()
            .one_or_none()
        )
        # Revalidate after potentially waiting on another transaction's row lock.
        self.authorize(principal, cancel=True)
        if row is None:
            raise NotFound()
        if tag.workflow_id != resource or tag.version != row["version"]:
            raise VersionConflict()
        state = row["state"]
        if state in {"SUCCEEDED", "FAILED"}:
            raise TerminalWorkflow()
        if state == "CANCELLED" or (state in AMBIGUOUS_STATES and row["cancel_requested_at"]):
            return self.acceptance(dict(row))
        if state not in SAFE_STATES | AMBIGUOUS_STATES:
            raise DependencyUnavailable()
        immediate = state in SAFE_STATES
        # Version remains in the UPDATE predicate as well as the locked comparison.
        updated = (
            self.session.execute(
                text("""UPDATE workflows SET state=:state,
            version=version+1,cancel_requested_at=COALESCE(cancel_requested_at,clock_timestamp()),
            reason_code=:reason WHERE id=:id AND version=:version
            RETURNING id AS workflow_id,incident_id,state,version,definition_version,
                cancel_requested_at,reason_code"""),
                {
                    "id": resource,
                    "version": tag.version,
                    "state": "CANCELLED" if immediate else state,
                    "reason": "CANCELLED_BY_OPERATOR" if immediate else "CANCEL_REQUESTED",
                },
            )
            .mappings()
            .one()
        )
        # Lock even completed jobs in stable order; only pending ownership is invalidated.
        self.session.execute(
            text("SELECT id FROM jobs WHERE workflow_id=:id ORDER BY id FOR UPDATE"),
            {"id": resource},
        ).all()
        self.session.execute(
            text("""UPDATE jobs SET state='DEAD',owner=NULL,lease_until=NULL,
            fence=fence+1 WHERE workflow_id=:id AND state IN ('READY','LEASED')"""),
            {"id": resource},
        )
        snapshot = {
            "schema_version": 1,
            **{key: str(updated[key]) for key in ("workflow_id", "incident_id")},
            **{
                key: updated[key]
                for key in ("state", "version", "definition_version", "reason_code")
            },
            "cancel_requested_at": timestamp(updated["cancel_requested_at"]),
        }
        payload = {
            "reason_code": updated["reason_code"],
            "aggregate_id": str(resource),
            "aggregate_version": updated["version"],
            "evidence_ids": [],
            "snapshot_hash": hashlib.sha256(canonical_bytes(snapshot)).hexdigest(),
        }
        if immediate:
            payload["transition"] = {
                "from": state,
                "to": "CANCELLED",
                "definition_version": updated["definition_version"],
            }
        PostgresWorkflowAppender(self.session).append(
            resource,
            "workflow.transitioned" if immediate else "workflow.cancel_requested",
            principal,
            trace,
            payload,
        )
        return self.acceptance(dict(updated))

    @staticmethod
    def acceptance(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "workflow_id": row["workflow_id"],
            "state": row["state"],
            "version": row["version"],
            "cancel_requested_at": timestamp(row["cancel_requested_at"]),
        }


class PostgresAccessUow(PostgresUow):
    workflows: AccessRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.workflows = PostgresWorkflows(self.session)
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
