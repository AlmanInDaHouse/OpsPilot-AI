"""Validated values and request-hash-v1, independent of HTTP and persistence."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

ROUTE = "/v1/incidents"


@dataclass(frozen=True)
class IncidentInput:
    title: str
    description: str

    def __post_init__(self) -> None:
        for value, maximum in ((self.title, 200), (self.description, 4000)):
            if not isinstance(value, str) or not 1 <= len(value) <= maximum:
                raise ValueError("Invalid incident text")
            if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise ValueError("Invalid Unicode")

    def canonical(self) -> bytes:
        return json.dumps(
            {
                "body": {"title": self.title, "description": self.description},
                "route": ROUTE,
                "schema_version": 1,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def request_hash(self) -> str:
        return hashlib.sha256(self.canonical()).hexdigest()


@dataclass(frozen=True)
class IncidentAccepted:
    incident_id: UUID
    workflow_id: UUID

    def body(self) -> dict[str, str]:
        return {"incident_id": str(self.incident_id), "workflow_id": str(self.workflow_id)}


@dataclass(frozen=True)
class StoredAcceptance:
    request_hash: str
    response: IncidentAccepted


class IdempotencyConflict(Exception):
    pass


class IdempotencyRace(Exception):
    """Only the scoped idempotency uniqueness constraint may produce this."""
