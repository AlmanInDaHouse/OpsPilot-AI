from uuid import uuid4

import pytest

from opspilot.identity.application.authenticate import authenticate
from opspilot.identity.application.provision import change_identity, create_identity
from opspilot.identity.domain.principal import ExternalIdentity, Principal, Role
from opspilot.shared.errors import Forbidden


@pytest.mark.parametrize(
    "roles,allowed",
    [
        (frozenset(), False),
        (frozenset({Role.OPERATOR}), False),
        (frozenset({Role.APPROVER}), False),
        (frozenset({Role.AUDITOR}), True),
        (frozenset({Role.ADMIN}), True),
    ],
)
def test_explicit_audit_permission(roles, allowed):
    principal = Principal(uuid4(), True, roles)
    if allowed:
        principal.require_audit_read()
    else:
        with pytest.raises(Forbidden):
            principal.require_audit_read()


def test_disabled_auditor_denied():
    with pytest.raises(Forbidden):
        Principal(uuid4(), False, frozenset({Role.AUDITOR})).require_audit_read()


def test_unknown_identity_is_not_provisioned_implicitly():
    class Verifier:
        def verify(self, token):
            return ExternalIdentity("issuer", "subject")

    class Reader:
        def find(self, identity):
            return None

    with pytest.raises(Forbidden):
        authenticate("test-token", Verifier(), Reader())


def test_provisioning_audit_failure_propagates_and_has_no_implicit_roles():
    class Writer:
        def create(self, issuer, subject):
            return uuid4(), True

    class Audit:
        def append(self, *args):
            raise RuntimeError("test appender failure")

    with pytest.raises(RuntimeError):
        create_identity(Writer(), Audit(), "issuer", "subject", uuid4().hex)


def test_grant_requires_explicit_role_before_writer_called():
    with pytest.raises(ValueError):
        change_identity(None, None, uuid4(), "grant", None, uuid4().hex)
