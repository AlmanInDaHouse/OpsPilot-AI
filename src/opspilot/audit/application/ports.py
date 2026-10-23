"""Persistence ports used by the API and transactional identity provisioning."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class EventPage:
    items: list[dict[str, Any]]
    next_after_seq: int


class AuditReader(Protocol):
    def list_events(self, stream_id: UUID, after_seq: int, limit: int) -> EventPage: ...


class AuditAppender(Protocol):
    def append(
        self,
        stream_id: UUID,
        event_type: str,
        actor_id: UUID | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...
