"""Authorized snapshots and cancellation share the established transaction port."""

from collections.abc import Callable
from typing import Any, Literal, Protocol
from uuid import UUID

from opspilot.shared.uow import UnitOfWork
from opspilot.workflows.domain.access import WorkflowTag


class AccessRepository(Protocol):
    def read(
        self, principal: UUID, resource: UUID, kind: Literal["incident", "workflow"]
    ) -> dict[str, Any]: ...

    def cancel(
        self, principal: UUID, resource: UUID, tag: WorkflowTag, trace: str
    ) -> dict[str, Any]: ...


class AccessUow(UnitOfWork, Protocol):
    workflows: AccessRepository


class WorkflowAccess:
    def __init__(self, transactions: Callable[[], AccessUow]) -> None:
        self.transactions = transactions

    def read(
        self, principal: UUID, resource: UUID, kind: Literal["incident", "workflow"]
    ) -> dict[str, Any]:
        with self.transactions() as uow:
            return uow.workflows.read(principal, resource, kind)

    def cancel(
        self, principal: UUID, resource: UUID, tag: WorkflowTag, trace: str
    ) -> dict[str, Any]:
        with self.transactions() as uow:
            result = uow.workflows.cancel(principal, resource, tag, trace)
            uow.commit()
            return result
