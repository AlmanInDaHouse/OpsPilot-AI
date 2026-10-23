from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from opspilot.adapters.postgres.models import EventRow
from opspilot.audit.application.ports import EventPage
from opspilot.audit.domain.envelope import canonical_bytes
from opspilot.shared.errors import DependencyUnavailable


class PostgresAppender:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        stream_id: UUID,
        event_type: str,
        actor_id: UUID | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result: dict[str, Any] = self.session.execute(
            text("SELECT audit_append(:stream,:type,:actor,:trace,:payload)"),
            {
                "stream": stream_id,
                "type": event_type,
                "actor": actor_id,
                "trace": trace_id,
                "payload": canonical_bytes(payload).decode("utf-8"),
            },
        ).scalar_one()
        return result


class PostgresWorkflowAppender:
    """V2 is explicit: it never expands or falls back to the S02 appender."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        stream_id: UUID,
        event_type: str,
        actor_id: UUID | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result: dict[str, Any] = self.session.execute(
            text("SELECT audit_append_v2(:stream,:type,:actor,:trace,:payload)"),
            {
                "stream": stream_id,
                "type": event_type,
                "actor": actor_id,
                "trace": trace_id,
                "payload": canonical_bytes(payload).decode("utf-8"),
            },
        ).scalar_one()
        return result


def envelope(row: EventRow, include_hash: bool = False) -> dict[str, Any]:
    item = {
        "event_id": str(row.event_id),
        "stream_id": str(row.stream_id),
        "seq": row.seq,
        "event_type": row.event_type,
        "schema_version": row.schema_version,
        "occurred_at": row.occurred_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "trace_id": row.trace_id,
        "payload": row.payload,
    }
    if include_hash:
        item.update(prev_hash=row.prev_hash, hash=row.hash)
    return item


class PostgresAuditReader:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def list_events(self, stream_id: UUID, after_seq: int, limit: int) -> EventPage:
        try:
            with self.sessions() as session:
                rows = session.scalars(
                    select(EventRow)
                    .where(EventRow.stream_id == stream_id, EventRow.seq > after_seq)
                    .order_by(EventRow.seq)
                    .limit(limit)
                ).all()
                return EventPage(
                    [envelope(row) for row in rows], rows[-1].seq if rows else after_seq
                )
        except SQLAlchemyError as exc:
            raise DependencyUnavailable() from exc
