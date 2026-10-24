"""Closed values for the local intake step; no infrastructure or authority from text."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID


class WorkerRejected(Exception):
    """A closed diagnostic, safe to log without exception/SQL/input text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    workflow_id: UUID
    step_id: UUID
    owner: UUID
    fence: int
    version: int


@dataclass(frozen=True)
class IntakeRecord:
    incident_id: UUID
    workflow_id: UUID
    incident_version: int
    definition_version: int
    status: str
    title: str
    description: str

    def snapshot(self) -> dict[str, Any]:
        if self.definition_version != 1:
            raise WorkerRejected("UNSUPPORTED_DEFINITION")
        if self.status != "OPEN" or self.incident_version != 1:
            raise WorkerRejected("INCIDENT_INCONSISTENT")
        return {
            "schema_version": 1,
            "incident_id": str(self.incident_id),
            "incident_version": self.incident_version,
            "workflow_id": str(self.workflow_id),
            "definition_version": 1,
            "status": "OPEN",
            "title_hash": hashlib.sha256(self.title.encode("utf-8")).hexdigest(),
            "description_hash": hashlib.sha256(self.description.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class Started:
    version: int
    incident: IntakeRecord


def snapshot_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def snapshot_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(snapshot_bytes(value)).hexdigest()
