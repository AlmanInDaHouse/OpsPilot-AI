"""Pure authentication use case. Network verification precedes any DB transaction."""

from typing import Protocol

from opspilot.identity.domain.principal import ExternalIdentity, Principal
from opspilot.shared.errors import Forbidden


class TokenVerifier(Protocol):
    def verify(self, token: str) -> ExternalIdentity: ...

    def ready(self) -> bool: ...


class PrincipalReader(Protocol):
    def find(self, identity: ExternalIdentity) -> Principal | None: ...


def authenticate(token: str, verifier: TokenVerifier, principals: PrincipalReader) -> Principal:
    identity = verifier.verify(token)
    principal = principals.find(identity)
    if principal is None or not principal.enabled:
        raise Forbidden()
    return principal
