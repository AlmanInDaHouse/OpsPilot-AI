"""Short explicit transactions. Snapshot calculation is outside the UoW."""

from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

from opspilot.shared.uow import UnitOfWork
from opspilot.workflows.domain.jobs import Claim, Started


class JobRepository(Protocol):
    def claim(self, owner: UUID) -> Claim | None: ...

    def start(self, claim: Claim, trace: str) -> Started | None: ...

    def renew(self, claim: Claim) -> None: ...

    def fail(self, claim: Claim, started: Started, trace: str) -> None: ...

    def complete(
        self, claim: Claim, started: Started, snapshot: dict[str, Any], trace: str
    ) -> UUID: ...


class JobUow(UnitOfWork, Protocol):
    jobs: JobRepository


class Jobs:
    def __init__(self, transactions: Callable[[], JobUow]) -> None:
        self.transactions = transactions

    def claim(self, owner: UUID) -> Claim | None:
        with self.transactions() as uow:
            result = uow.jobs.claim(owner)
            uow.commit()
            return result

    def fail(self, claim: Claim, started: Started, trace: str) -> None:
        with self.transactions() as uow:
            uow.jobs.fail(claim, started, trace)
            uow.commit()

    def start(self, claim: Claim, trace: str) -> Started | None:
        with self.transactions() as uow:
            result = uow.jobs.start(claim, trace)
            uow.commit()
            return result

    def renew(self, claim: Claim) -> None:
        with self.transactions() as uow:
            uow.jobs.renew(claim)
            uow.commit()

    def complete(
        self, claim: Claim, started: Started, snapshot: dict[str, Any], trace: str
    ) -> UUID:
        with self.transactions() as uow:
            result = uow.jobs.complete(claim, started, snapshot, trace)
            uow.commit()
            return result
