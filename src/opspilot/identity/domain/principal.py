"""Identity is external; authority comes only from fresh local grants."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from opspilot.shared.errors import Forbidden


class Role(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    ADMIN = "admin"


@dataclass(frozen=True)
class ExternalIdentity:
    issuer: str
    subject: str


@dataclass(frozen=True)
class Principal:
    id: UUID
    enabled: bool
    roles: frozenset[Role]

    def require_operator(self) -> None:
        if not self.enabled or Role.OPERATOR not in self.roles:
            raise Forbidden()

    def require_workflow_read(self) -> None:
        if not self.enabled or not self.roles.intersection({Role.OPERATOR, Role.AUDITOR}):
            raise Forbidden()

    def require_audit_read(self) -> None:
        if not self.enabled or not self.roles.intersection({Role.AUDITOR, Role.ADMIN}):
            raise Forbidden()
