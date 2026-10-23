"""HTTP intake conformance; test doubles do not substantiate SQL durability."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from opspilot.audit.application.ports import EventPage
from opspilot.entrypoints.api.app import platform_api
from opspilot.identity.domain.principal import ExternalIdentity, Principal, Role
from opspilot.incidents.domain.intake import IdempotencyConflict, IncidentAccepted
from opspilot.shared.errors import DependencyUnavailable, Unauthenticated

from .test_api import deref

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "contracts/workflows.openapi.json").read_text(encoding="utf-8"))


@pytest.fixture
def intake_api():
    state = {"role": Role.OPERATOR, "enabled": True, "calls": [], "failure": None}
    result = IncidentAccepted(uuid4(), uuid4())

    class Verifier:
        def verify(self, token):
            if token != "valid":
                raise Unauthenticated()
            return ExternalIdentity("https://test.invalid", "subject")

    class Principals:
        def find(self, identity):
            return Principal(uuid4(), state["enabled"], frozenset({state["role"]}))

    class Audit:
        def list_events(self, *args):
            return EventPage([], 0)

    class Intake:
        def execute(self, *args):
            state["calls"].append(args)
            if state["failure"]:
                raise state["failure"]()
            return result

    app = platform_api(
        Verifier(), Principals(), Audit(), lambda: True, lambda: None, intake=Intake()
    )
    with TestClient(app) as client:
        yield client, state, result, app


def post(client, **kwargs):
    headers = {
        "Authorization": "Bearer valid",
        "Idempotency-Key": str(uuid4()),
        "Content-Type": "application/json",
    }
    headers.update(kwargs.pop("headers", {}))
    return client.post("/v1/incidents", headers=headers, **kwargs)


def conform(response):
    spec = deref(
        CONTRACT["paths"]["/v1/incidents"]["post"]["responses"][str(response.status_code)], CONTRACT
    )
    Draft202012Validator(
        spec["content"]["application/json"]["schema"], format_checker=FormatChecker()
    ).validate(response.json())
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_post_openapi_and_response(intake_api):
    client, state, result, app = intake_api
    generated = app.openapi()
    validate(generated)
    actual = generated["paths"]["/v1/incidents"]["post"]
    expected = CONTRACT["paths"]["/v1/incidents"]["post"]
    assert actual["operationId"] == expected["operationId"]
    assert set(actual["responses"]) == set(expected["responses"])
    assert actual["parameters"] == expected["parameters"]
    assert actual["security"] == CONTRACT["security"]
    response = post(client, json={"title": "VPN", "description": "Prueba"})
    assert response.status_code == 202 and response.json() == result.body()
    conform(response)
    assert len(state["calls"]) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"null",
        b"{",
        b'\xef\xbb\xbf{"title":"t","description":"d"}',
        b'{"title":"t","title":"u","description":"d"}',
        b'{"title":"t","description":"d","extra":1}',
        b'{"title":1,"description":"d"}',
        b'{"title":"","description":"d"}',
        b'{"title":"t","description":""}',
        b'{"title":NaN,"description":"d"}',
        b'{"title":Infinity,"description":"d"}',
        b'{"title":"\\ud800","description":"d"}',
        b'{"title":"t","description":"\\u0000"}',
        b'{"title":"\xff","description":"d"}',
        b"[" * 1200,
    ],
)
def test_rejects_ambiguous_or_invalid_json(intake_api, raw):
    client, state, *_ = intake_api
    response = post(client, content=raw)
    assert response.status_code == 422
    conform(response)
    assert not state["calls"]


@pytest.mark.parametrize(
    "header,value",
    [
        ("Content-Type", "text/plain"),
        ("Content-Type", "application/json; charset=latin1"),
        ("Idempotency-Key", ""),
        ("Idempotency-Key", uuid4().hex),
        ("Idempotency-Key", "{" + str(uuid4()) + "}"),
    ],
)
def test_invalid_headers(intake_api, header, value):
    response = post(intake_api[0], headers={header: value}, json={"title": "t", "description": "d"})
    assert response.status_code == 422
    conform(response)


@pytest.mark.parametrize("header", ["Authorization", "Idempotency-Key", "If-Match"])
def test_duplicate_headers_precede_auth(intake_api, header):
    response = intake_api[0].post(
        "/v1/incidents", headers=[(header, "a"), (header, "b")], content=b"invalid"
    )
    assert response.status_code == 422
    conform(response)


def test_auth_before_input_and_error_codes(intake_api):
    client, state, *_ = intake_api
    response = client.post("/v1/incidents", content=b"invalid")
    assert response.status_code == 401
    conform(response)
    for role in (Role.ADMIN, Role.AUDITOR, Role.APPROVER):
        state["role"] = role
        response = post(client, content=b"invalid")
        assert response.status_code == 403
        conform(response)
    state["role"] = Role.OPERATOR
    for failure, code in [(IdempotencyConflict, 409), (DependencyUnavailable, 503)]:
        state["failure"] = failure
        response = post(client, json={"title": "t", "description": "d"})
        assert response.status_code == code
        conform(response)


def test_query_limit_and_uppercase_key(intake_api):
    client, state, *_ = intake_api
    key = uuid4()
    response = post(
        client,
        headers={
            "Idempotency-Key": str(key).upper(),
            "Content-Type": 'application/json; charset="UTF-8"',
        },
        json={"title": "😀", "description": " d "},
    )
    assert response.status_code == 202 and state["calls"][-1][1] == key
    assert (
        client.post("/v1/incidents?x=1", headers={"Authorization": "Bearer valid"}).status_code
        == 422
    )
    assert post(client, content=b"x" * 16385).status_code == 422
