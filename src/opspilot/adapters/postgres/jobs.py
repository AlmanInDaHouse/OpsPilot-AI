"""PG18 job store. Claim locks only job; all other writes lock workflow first."""

from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from opspilot.adapters.postgres.audit import PostgresWorkflowAppender
from opspilot.adapters.postgres.database import PostgresUow
from opspilot.workflows.application.jobs import JobRepository
from opspilot.workflows.domain.jobs import (
    Claim,
    IntakeRecord,
    Started,
    WorkerRejected,
    snapshot_bytes,
    snapshot_hash,
)


class PostgresJobs:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim(self, owner: UUID) -> Claim | None:
        row = (
            self.session.execute(
                text("""SELECT j.id,j.workflow_id,j.step_id,w.version FROM jobs j
                JOIN workflows w ON w.id=j.workflow_id
                WHERE j.state='READY' AND j.available_at<=clock_timestamp()
                  AND j.attempts<3 AND w.cancel_requested_at IS NULL
                  AND w.state IN ('QUEUED','INVESTIGATING')
                ORDER BY j.available_at,j.id LIMIT 1 FOR UPDATE OF j SKIP LOCKED""")
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        fence = self.session.execute(
            text("""UPDATE jobs SET state='LEASED',owner=:owner,fence=fence+1,
                attempts=attempts+1,lease_until=clock_timestamp()+interval '60 seconds'
                WHERE id=:id AND state='READY' RETURNING fence"""),
            {"id": row["id"], "owner": owner},
        ).scalar_one()
        return Claim(row["id"], row["workflow_id"], row["step_id"], owner, fence, row["version"])

    def _locked(self, claim: Claim, version: int | None = None) -> dict[str, Any]:
        w = dict(
            self.session.execute(
                text("SELECT * FROM workflows WHERE id=:id FOR UPDATE"),
                {"id": claim.workflow_id},
            )
            .mappings()
            .one()
        )
        j = (
            self.session.execute(
                text("SELECT * FROM jobs WHERE id=:id FOR UPDATE"), {"id": claim.job_id}
            )
            .mappings()
            .one()
        )
        if w["cancel_requested_at"] is not None or w["state"] == "CANCELLED":
            raise WorkerRejected("WORKFLOW_CANCELLED")
        if version is not None and w["version"] != version:
            raise WorkerRejected("VERSION_CONFLICT")
        if j["state"] != "LEASED" or j["owner"] != claim.owner or j["fence"] != claim.fence:
            raise WorkerRejected("OWNERSHIP_LOST")
        if (
            j["workflow_id"] != claim.workflow_id
            or j["step_id"] != claim.step_id
            or j["kind"] != "intake_snapshot"
        ):
            raise WorkerRejected("STEP_INCONSISTENT")
        self._live(claim)
        return w

    def _live(self, claim: Claim) -> None:
        if not self.session.execute(
            text("""SELECT lease_until>clock_timestamp() FROM jobs
                WHERE id=:id AND state='LEASED' AND owner=:owner AND fence=:fence"""),
            {"id": claim.job_id, "owner": claim.owner, "fence": claim.fence},
        ).scalar_one_or_none():
            raise WorkerRejected("LEASE_EXPIRED")

    def _within_deadline(self, w: dict[str, Any]) -> bool:
        return (
            bool(
                self.session.execute(
                    text("SELECT :deadline>clock_timestamp()"), {"deadline": w["deadline_at"]}
                ).scalar_one()
            )
            and w["budget_spent_ms"] < 300000
        )

    def _incident(self, w: dict[str, Any]) -> IntakeRecord:
        row = (
            self.session.execute(
                text("SELECT * FROM incidents WHERE id=:id AND creator_id=:creator"),
                {"id": w["incident_id"], "creator": w["creator_id"]},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["status"] != "OPEN" or row["version"] != 1:
            raise WorkerRejected("INCIDENT_INCONSISTENT")
        return IntakeRecord(
            row["id"],
            w["id"],
            row["version"],
            w["definition_version"],
            row["status"],
            row["title"],
            row["description"],
        )

    def _step(self, claim: Claim, status: str) -> None:
        row = self.session.execute(
            text("""SELECT status FROM workflow_steps WHERE id=:id
                AND workflow_id=:workflow AND step_key='intake_snapshot' FOR UPDATE"""),
            {"id": claim.step_id, "workflow": claim.workflow_id},
        ).scalar_one_or_none()
        if row != status:
            raise WorkerRejected("STEP_INCONSISTENT")

    def _transition(
        self,
        w: dict[str, Any],
        state: str,
        reason: str,
        trace: str,
        evidence: UUID | None = None,
        blocked: bool = False,
    ) -> int:
        row = self.session.execute(
            text("""UPDATE workflows SET state=:state,version=version+1,reason_code=:reason
                WHERE id=:id AND version=:version RETURNING version"""),
            {"id": w["id"], "version": w["version"], "state": state, "reason": reason},
        ).scalar_one_or_none()
        if row is None:
            raise WorkerRejected("VERSION_CONFLICT")
        snapshot = {
            "schema_version": 1,
            "workflow_id": str(w["id"]),
            "incident_id": str(w["incident_id"]),
            "definition_version": w["definition_version"],
            "state": state,
            "version": row,
            "reason_code": reason,
            "cancel_requested_at": None,
        }
        payload = {
            "reason_code": reason,
            "aggregate_id": str(w["id"]),
            "aggregate_version": row,
            "evidence_ids": [str(evidence)] if evidence else [],
            "snapshot_hash": snapshot_hash(snapshot),
        }
        if not blocked:
            payload["transition"] = {
                "from": w["state"],
                "to": state,
                "definition_version": w["definition_version"],
            }
        try:
            PostgresWorkflowAppender(self.session).append(
                w["id"],
                "workflow.blocked" if blocked else "workflow.transitioned",
                None,
                trace,
                payload,
            )
        except SQLAlchemyError as exc:
            raise WorkerRejected("AUDIT_FAILED") from exc
        return int(row)

    def _release(self, claim: Claim, state: str) -> None:
        # Last write, AFTER audit: a lease that expired while waiting for audit cannot commit.
        result = self.session.execute(
            text("""UPDATE jobs SET state=:state,owner=NULL,lease_until=NULL,
                fence=fence+:increment
                WHERE id=:id AND owner=:owner AND fence=:fence AND state='LEASED'
                  AND lease_until>clock_timestamp() RETURNING id"""),
            {
                "id": claim.job_id,
                "owner": claim.owner,
                "fence": claim.fence,
                "state": state,
                "increment": 1 if state == "DEAD" else 0,
            },
        ).scalar_one_or_none()
        if result is None:
            raise WorkerRejected("LEASE_EXPIRED")

    def start(self, claim: Claim, trace: str) -> Started | None:
        w = self._locked(claim, claim.version)
        if w["state"] not in {"QUEUED", "INVESTIGATING"}:
            raise WorkerRejected("WORKFLOW_INCOMPATIBLE")
        if w["definition_version"] != 1:
            self._transition(w, w["state"], "UNSUPPORTED_DEFINITION", trace, blocked=True)
            self._release(claim, "DEAD")
            return None
        if not self._within_deadline(w):
            self._transition(
                w,
                "FAILED" if w["state"] == "QUEUED" else "NEEDS_OPERATOR",
                "DEADLINE_EXHAUSTED",
                trace,
            )
            self._release(claim, "DEAD")
            return None
        incident = self._incident(w)
        self._step(claim, "PENDING" if w["state"] == "QUEUED" else "RUNNING")
        version = w["version"]
        if w["state"] == "QUEUED":
            self.session.execute(
                text("UPDATE workflow_steps SET status='RUNNING' WHERE id=:id"),
                {"id": claim.step_id},
            )
            version = self._transition(w, "INVESTIGATING", "LOCAL_STEP_STARTED", trace)
        self._live(claim)
        return Started(version, incident)

    def renew(self, claim: Claim) -> None:
        w = self._locked(claim)
        if w["definition_version"] != 1:
            raise WorkerRejected("UNSUPPORTED_DEFINITION")
        if w["state"] not in {"QUEUED", "INVESTIGATING"}:
            raise WorkerRejected("WORKFLOW_INCOMPATIBLE")
        if not self._within_deadline(w):
            raise WorkerRejected("DEADLINE_EXHAUSTED")
        result = self.session.execute(
            text("""UPDATE jobs SET lease_until=clock_timestamp()+interval '60 seconds'
                WHERE id=:id AND state='LEASED' AND owner=:owner AND fence=:fence
                  AND lease_until>clock_timestamp() RETURNING id"""),
            {"id": claim.job_id, "owner": claim.owner, "fence": claim.fence},
        ).scalar_one_or_none()
        if result is None:
            raise WorkerRejected("LEASE_EXPIRED")

    def fail(self, claim: Claim, started: Started, trace: str) -> None:
        w = self._locked(claim, started.version)
        if w["definition_version"] != 1 or w["state"] != "INVESTIGATING":
            raise WorkerRejected("WORKFLOW_INCOMPATIBLE")
        if not self._within_deadline(w):
            raise WorkerRejected("DEADLINE_EXHAUSTED")
        self._step(claim, "RUNNING")
        self.session.execute(
            text("""UPDATE workflow_steps SET status='FAILED',error_code='PERMANENT_LOCAL_FAILURE'
                WHERE id=:id"""),
            {"id": claim.step_id},
        )
        self._transition(w, "NEEDS_OPERATOR", "PERMANENT_LOCAL_FAILURE", trace)
        self._release(claim, "DEAD")

    def complete(
        self, claim: Claim, started: Started, snapshot: dict[str, Any], trace: str
    ) -> UUID:
        w = self._locked(claim, started.version)
        if w["definition_version"] != 1:
            raise WorkerRejected("UNSUPPORTED_DEFINITION")
        if w["state"] != "INVESTIGATING":
            raise WorkerRejected("WORKFLOW_INCOMPATIBLE")
        if not self._within_deadline(w):
            raise WorkerRejected("DEADLINE_EXHAUSTED")
        incident = self._incident(w)
        if incident != started.incident or snapshot_bytes(snapshot) != snapshot_bytes(
            incident.snapshot()
        ):
            raise WorkerRejected("SNAPSHOT_INVALID")
        self._step(claim, "RUNNING")
        evidence = uuid4()
        digest = snapshot_hash(snapshot)
        self.session.execute(
            text("""INSERT INTO evidence(id,workflow_id,step_key,kind,collector_id,source_ref,
                content_hash,payload,independence_role) VALUES(:id,:workflow,'intake_snapshot',
                'INCIDENT_SNAPSHOT_V1','local-intake-v1',:source,:hash,CAST(:payload AS jsonb),'INTAKE_SNAPSHOT')"""),
            {
                "id": evidence,
                "workflow": claim.workflow_id,
                "source": f"incident:{incident.incident_id}:v{incident.incident_version}",
                "hash": digest,
                "payload": snapshot_bytes(snapshot).decode("utf-8"),
            },
        )
        self.session.execute(
            text("""UPDATE workflow_steps SET status='DONE',input_hash=:hash,evidence_id=:evidence,
                error_code=NULL WHERE id=:id"""),
            {"id": claim.step_id, "hash": digest, "evidence": evidence},
        )
        self._transition(w, "NEEDS_OPERATOR", "LOCAL_SNAPSHOT_RECORDED", trace, evidence)
        if not self._within_deadline(w):
            raise WorkerRejected("DEADLINE_EXHAUSTED")
        self._release(claim, "DONE")
        return evidence


class PostgresJobUow(PostgresUow):
    jobs: JobRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.jobs = PostgresJobs(self.session)
        return self

    def commit(self) -> None:
        try:
            super().commit()
        except DBAPIError as exc:
            raise WorkerRejected(
                "COMMIT_UNCERTAIN" if exc.connection_invalidated else "COMMIT_FAILED"
            ) from exc

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)
        if isinstance(exc, SQLAlchemyError):
            code = getattr(getattr(exc, "orig", None), "sqlstate", None)
            raise WorkerRejected(
                "POSTGRES_TRANSIENT"
                if code in {"40001", "40P01", "55P03", "57014", "08006"}
                else "POSTGRES_FAILED"
            ) from exc
