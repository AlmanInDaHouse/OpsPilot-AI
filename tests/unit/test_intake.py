"""request-hash-v1 golden, strict values, roles and application failures."""

import hashlib
from contextlib import AbstractContextManager
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot.entrypoints.api.dto import CreateIncidentInput
from opspilot.identity.domain.principal import Principal, Role
from opspilot.incidents.application.create import CreateIncident
from opspilot.incidents.domain.intake import (
    IdempotencyConflict,
    IdempotencyRace,
    IncidentAccepted,
    IncidentInput,
    StoredAcceptance,
)
from opspilot.shared.errors import DependencyUnavailable, Forbidden


@pytest.mark.parametrize(
    "title,description",
    [
        ("", "d"),
        ("t" * 201, "d"),
        ("t", ""),
        ("t", "d" * 4001),
        ("\x00", "d"),
        ("t", "\ud800"),
        (123, "d"),
        ("t", None),
    ],
)
def test_invalid_input(title, description):
    with pytest.raises(ValueError):
        IncidentInput(title, description)
    with pytest.raises(ValidationError):
        CreateIncidentInput.model_validate({"title": title, "description": description})


def test_exact_unicode_lengths_no_trim_or_normalization():
    assert IncidentInput(" " * 200, "😀" * 4000).title == " " * 200
    assert IncidentInput("é", "d").request_hash() != IncidentInput("e\u0301", "d").request_hash()


@pytest.mark.parametrize(
    "extra",
    [
        "incident_id",
        "workflow_id",
        "creator_id",
        "status",
        "definition_version",
        "actor",
        "owner",
        "permissions",
    ],
)
def test_client_cannot_assign_server_fields(extra):
    with pytest.raises(ValidationError):
        CreateIncidentInput.model_validate({"title": "t", "description": "d", extra: "x"})


def test_canonical_bytes_golden():
    value = IncidentInput("VPN de prueba", "Laboratorio sintético")
    expected = '{"body":{"description":"Laboratorio sintético","title":"VPN de prueba"},"route":"/v1/incidents","schema_version":1}'.encode()
    assert value.canonical() == expected
    assert value.request_hash() == hashlib.sha256(expected).hexdigest()


@pytest.mark.parametrize("role", list(Role))
def test_only_explicit_operator_grants_intake(role):
    principal = Principal(uuid4(), True, frozenset({role}))
    if role == Role.OPERATOR:
        principal.require_operator()
    else:
        with pytest.raises(Forbidden):
            principal.require_operator()
    with pytest.raises(Forbidden):
        Principal(principal.id, False, frozenset({role})).require_operator()


def test_usecase_commit_before_return_and_race_rollback_before_replay():
    result, body = IncidentAccepted(uuid4(), uuid4()), IncidentInput("t", "d")
    sequence = []

    class Transaction(AbstractContextManager):
        incidents = None

        def __init__(self):
            self.incidents = self

        def __exit__(self, *args):
            sequence.append("rollback-close")

        def require_operator(self, pid):
            sequence.append("authorize")

        def find(self, pid, key):
            return (
                StoredAcceptance(body.request_hash(), result)
                if sequence.count("authorize") > 1
                else None
            )

        def create(self, pid, value):
            return result

        def audit(self, *args):
            sequence.append("audit")

        def remember(self, *args):
            raise IdempotencyRace()

        def commit(self):
            pytest.fail("Loser must never commit")

    assert CreateIncident(Transaction).execute(uuid4(), uuid4(), body, uuid4().hex) == result
    assert sequence == ["authorize", "audit", "rollback-close", "authorize", "rollback-close"]
    with pytest.raises(IdempotencyConflict):
        CreateIncident.replay(StoredAcceptance("different", result), body.request_hash())


def test_race_without_committed_record_fails_closed():
    class Transaction(AbstractContextManager):
        def __init__(self):
            self.incidents = self

        def __exit__(self, *args):
            return None

        def require_operator(self, pid):
            pass

        def find(self, *args):
            return None

        def create(self, *args):
            raise IdempotencyRace()

    with pytest.raises(DependencyUnavailable):
        CreateIncident(Transaction).execute(uuid4(), uuid4(), IncidentInput("t", "d"), uuid4().hex)
