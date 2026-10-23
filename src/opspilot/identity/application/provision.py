"""Local privileged operations; identity change and audit share the caller's UoW."""

from typing import Any, Protocol
from uuid import UUID

from opspilot.identity.domain.principal import Role


class IdentityChanges(Protocol):
    def create(self, issuer: str, subject: str) -> tuple[UUID, bool]: ...

    def change(self, principal_id: UUID, action: str, role: Role | None) -> int | None: ...


class IdentityAudit(Protocol):
    def append(
        self,
        stream_id: UUID,
        event_type: str,
        actor_id: UUID | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


def record(
    audit: IdentityAudit,
    principal_id: UUID,
    event_type: str,
    reason: str,
    version: int,
    trace_id: str,
) -> None:
    audit.append(
        principal_id,
        event_type,
        None,
        trace_id,
        {
            "reason_code": reason,
            "aggregate_id": str(principal_id),
            "aggregate_version": version,
            "evidence_ids": [],
        },
    )


def create_identity(
    identities: IdentityChanges, audit: IdentityAudit, issuer: str, subject: str, trace_id: str
) -> UUID:
    if not 1 <= len(issuer) <= 2048 or not 1 <= len(subject) <= 255:
        raise ValueError("Invalid identity")
    principal_id, created = identities.create(issuer, subject)
    if created:
        record(audit, principal_id, "identity.provisioned", "LOCAL_PROVISION", 1, trace_id)
    return principal_id


def change_identity(
    identities: IdentityChanges,
    audit: IdentityAudit,
    principal_id: UUID,
    action: str,
    role: Role | None,
    trace_id: str,
) -> None:
    if action not in {"disable", "grant", "revoke"} or (action != "disable" and role is None):
        raise ValueError("Invalid provision operation")
    version = identities.change(principal_id, action, role)
    if version is not None:
        kind = {
            "disable": "identity.disabled",
            "grant": "authorization.granted",
            "revoke": "authorization.revoked",
        }[action]
        reason = "LOCAL_DISABLE" if role is None else f"ROLE_{role.value.upper()}_{action.upper()}"
        record(audit, principal_id, kind, reason, version, trace_id)
