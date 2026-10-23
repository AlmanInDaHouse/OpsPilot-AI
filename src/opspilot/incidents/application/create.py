"""One existing UoW owns every intake write, including the durable response."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from opspilot.incidents.domain.intake import (
    IdempotencyConflict,
    IdempotencyRace,
    IncidentAccepted,
    IncidentInput,
    StoredAcceptance,
)
from opspilot.shared.errors import DependencyUnavailable
from opspilot.shared.uow import UnitOfWork


class IntakeRepository(Protocol):
    def require_operator(self, principal_id: UUID) -> None: ...

    def find(self, principal_id: UUID, key: UUID) -> StoredAcceptance | None: ...

    def create(self, principal_id: UUID, body: IncidentInput) -> IncidentAccepted: ...

    def audit(self, principal_id: UUID, result: IncidentAccepted, trace_id: str) -> None: ...

    def remember(
        self, principal_id: UUID, key: UUID, request_hash: str, result: IncidentAccepted
    ) -> None: ...


class IntakeUow(UnitOfWork, Protocol):
    incidents: IntakeRepository


class CreateIncident:
    def __init__(self, transactions: Callable[[], IntakeUow]) -> None:
        self.transactions = transactions

    def execute(
        self, principal_id: UUID, key: UUID, body: IncidentInput, trace_id: str
    ) -> IncidentAccepted:
        digest = body.request_hash()
        try:
            with self.transactions() as uow:
                uow.incidents.require_operator(principal_id)
                stored = uow.incidents.find(principal_id, key)
                if stored is not None:
                    return self.replay(stored, digest)
                result = uow.incidents.create(principal_id, body)
                uow.incidents.audit(principal_id, result, trace_id)
                uow.incidents.remember(principal_id, key, digest, result)
                uow.commit()
                return result
        except IdempotencyRace:
            # __exit__ has rolled back ALL speculative writes. Never read an aborted session.
            with self.transactions() as uow:
                uow.incidents.require_operator(principal_id)
                stored = uow.incidents.find(principal_id, key)
                if stored is None:
                    raise DependencyUnavailable() from None
                return self.replay(stored, digest)

    @staticmethod
    def replay(stored: StoredAcceptance, digest: str) -> IncidentAccepted:
        if stored.request_hash != digest:
            raise IdempotencyConflict()
        return stored.response
