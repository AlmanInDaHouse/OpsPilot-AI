"""Short explicit transactions. Snapshot calculation is outside the UoW."""

from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

from opspilot.shared.uow import UnitOfWork
from opspilot.workflows.domain.jobs import Claim, Started, WorkerRejected


class JobRepository(Protocol):
    def recover(self, trace: str) -> bool: ...

    def retry(self, claim: Claim, started: Started, trace: str) -> None: ...

    def confirmed(self, claim: Claim) -> UUID | None: ...

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

    def recover(self, trace: str) -> bool:
        with self.transactions() as uow:
            result = uow.jobs.recover(trace)
            uow.commit()
            return result

    def retry(self, claim: Claim, started: Started, trace: str) -> None:
        with self.transactions() as uow:
            uow.jobs.retry(claim, started, trace)
            uow.commit()

    def confirmed(self, claim: Claim) -> UUID | None:
        with self.transactions() as uow:
            return uow.jobs.confirmed(claim)

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
        try:
            with self.transactions() as uow:
                result = uow.jobs.complete(claim, started, snapshot, trace)
                uow.commit()
                return result
        except WorkerRejected as exc:
            if exc.code != "COMMIT_UNCERTAIN":
                raise
            try:
                confirmed = self.confirmed(claim)
            except WorkerRejected as recheck:
                # A failed read cannot turn an uncertain COMMIT into a retryable failure.
                raise WorkerRejected("COMMIT_UNCERTAIN") from recheck
            if confirmed is None:
                raise WorkerRejected("COMMIT_UNCERTAIN") from exc
            return confirmed
