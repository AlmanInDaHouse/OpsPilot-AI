"""TEST-02-CONTRACT: validate real HTTP behavior against the independent canonical spec."""

import copy
import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from opspilot.audit.application.ports import EventPage
from opspilot.entrypoints.api.app import platform_api
from opspilot.identity.domain.principal import ExternalIdentity, Principal, Role
from opspilot.shared.errors import DependencyUnavailable, Unauthenticated

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "contracts/platform.openapi.json").read_text(encoding="utf-8"))
EVENT = json.loads((ROOT / "contracts/event-v1.schema.json").read_text(encoding="utf-8"))


def deref(value, document=None):
    document = CONTRACT if document is None else document
    if isinstance(value, dict):
        if "$ref" in value:
            reference = value["$ref"]
            if not reference.startswith("#/"):
                target = json.loads((ROOT / "contracts" / reference).read_text(encoding="utf-8"))
                return deref(target, target)
            target = document
            for key in reference[2:].split("/"):
                target = target[key]
            return deref(target, document)
        return {key: deref(child, document) for key, child in value.items()}
    if isinstance(value, list):
        return [deref(child, document) for child in value]
    return value


def assert_response(path, response):
    expected = deref(CONTRACT["paths"][path]["get"]["responses"][str(response.status_code)])
    Draft202012Validator(
        expected["content"]["application/json"]["schema"], format_checker=FormatChecker()
    ).validate(response.json())


@pytest.fixture
def platform():
    pid, stream = uuid4(), uuid4()
    state = {"ready": True, "roles": frozenset({Role.AUDITOR}), "exists": True, "db": True}

    class Verifier:
        def verify(self, token):
            if token != "test-valid":
                raise Unauthenticated()
            return ExternalIdentity("https://test.invalid", "subject")

        def ready(self):
            return state["ready"]

    class Principals:
        def find(self, identity):
            return Principal(pid, True, state["roles"]) if state["exists"] else None

    event = {
        "event_id": str(uuid4()),
        "schema_version": 1,
        "stream_id": str(stream),
        "seq": 1,
        "event_type": "identity.provisioned",
        "occurred_at": "2026-10-23T00:00:00.000001Z",
        "actor_id": None,
        "trace_id": uuid4().hex,
        "payload": {
            "reason_code": "LOCAL_PROVISION",
            "aggregate_id": str(pid),
            "aggregate_version": 1,
            "evidence_ids": [],
        },
    }

    class Audit:
        def list_events(self, stream_id, after_seq, limit):
            if state.get("crash"):
                raise RuntimeError("sensitive-exception-canary")
            return EventPage([event], 1) if after_seq == 0 else EventPage([], after_seq)

    def schema():
        if not state["db"]:
            raise DependencyUnavailable()

    app = platform_api(
        Verifier(), Principals(), Audit(), lambda: state["ready"] and state["db"], schema
    )
    with TestClient(app) as client:
        yield client, state, stream, app


def test_openapi_is_standard_valid():
    validate(deref(CONTRACT))
    Draft202012Validator.check_schema(EVENT)


def test_runtime_generated_contract_has_exact_routes_operations_errors_and_models(platform):
    _, _, _, app = platform
    generated = app.openapi()
    validate(generated)
    assert set(generated["paths"]) == set(CONTRACT["paths"]) | {"/v1/incidents"}
    for path, methods in CONTRACT["paths"].items():
        assert generated["paths"][path]["get"]["operationId"] == methods["get"]["operationId"]
        assert set(generated["paths"][path]["get"]["responses"]) == set(methods["get"]["responses"])
        if path.startswith("/v1/"):
            assert generated["paths"][path]["get"]["security"] == CONTRACT["security"]


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/v1/me", "/v1/audit-events"])
def test_success_http_contract(platform, path):
    client, _, stream, _ = platform
    response = client.get(
        path, params={"stream_id": stream}, headers={"Authorization": "Bearer test-valid"}
    )
    assert response.status_code == 200
    assert_response(path, response)


@pytest.mark.parametrize("authorization", [None, "Bearer bad", "Basic bad", "Bearer"])
def test_401_error_contract(platform, authorization):
    client, *_ = platform
    response = client.get(
        "/v1/me", headers={"Authorization": authorization} if authorization else {}
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert_response("/v1/me", response)


def test_forbidden_invalid_and_dependency_contracts(platform):
    client, state, stream, _ = platform
    headers = {"Authorization": "Bearer test-valid"}
    response = client.get("/v1/audit-events", params={"stream_id": "canary-input"}, headers=headers)
    assert response.status_code == 422 and "canary-input" not in response.text
    assert_response("/v1/audit-events", response)
    state["roles"] = frozenset({Role.OPERATOR})
    response = client.get("/v1/audit-events", params={"stream_id": stream}, headers=headers)
    assert response.status_code == 403
    assert_response("/v1/audit-events", response)
    state["db"] = False
    assert client.get("/health/live").status_code == 200
    for path in ("/health/ready", "/v1/me", "/v1/audit-events"):
        response = client.get(path, params={"stream_id": stream}, headers=headers)
        assert response.status_code == 503
        assert_response(path, response)


def test_server_request_ids_traceparent_and_logs_never_echo_tokens(platform, caplog):
    client, *_ = platform
    trace = uuid4().hex
    with caplog.at_level(logging.INFO, logger="opspilot.requests"):
        response = client.get(
            "/v1/me?token=secret-query-canary",
            headers={
                "Authorization": "Bearer secret-token-canary",
                "X-Request-ID": "untrusted-client-id",
                "traceparent": f"00-{trace}-1234567890abcdef-01",
            },
        )
    assert response.status_code == 401
    assert str(UUID(response.json()["request_id"])) == response.headers["X-Request-ID"]
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "opspilot.requests"
    ]
    assert records[-1]["trace_id"] == trace
    assert records[-1]["result"] == "UNAUTHENTICATED"
    assert "secret-token-canary" not in caplog.text and "secret-query-canary" not in caplog.text


def test_body_bytes_are_bounded(platform):
    client, *_ = platform
    response = client.request("GET", "/v1/me", content=b"x" * 16385)
    assert response.status_code == 422
    assert set(response.json()) == {"code", "request_id"}
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_unexpected_exception_is_redacted(platform, caplog):
    client, state, stream, _ = platform
    state["crash"] = True
    with caplog.at_level(logging.INFO, logger="opspilot.requests"):
        response = client.get(
            "/v1/audit-events",
            params={"stream_id": stream},
            headers={"Authorization": "Bearer test-valid"},
        )
    assert response.status_code == 503
    assert set(response.json()) == {"code", "request_id"}
    assert "sensitive-exception-canary" not in response.text + caplog.text


def test_event_schema_rejects_extra_payload_and_missing_mandatory_fields():
    validator = Draft202012Validator(EVENT, format_checker=FormatChecker())
    assert not validator.is_valid({"event_type": "identity.provisioned"})
    value = {
        "event_id": str(uuid4()),
        "stream_id": str(uuid4()),
        "seq": 1,
        "schema_version": 1,
        "event_type": "identity.provisioned",
        "occurred_at": "2026-10-23T00:00:00.000000Z",
        "actor_id": None,
        "trace_id": uuid4().hex,
        "payload": {
            "reason_code": "TEST",
            "aggregate_id": str(uuid4()),
            "aggregate_version": 1,
            "evidence_ids": [],
        },
    }
    validator.validate(value)
    invalid = copy.deepcopy(value)
    invalid["payload"]["secret"] = (
        "prohibited"  # pragma: allowlist secret (schema rejection fixture)
    )
    assert not validator.is_valid(invalid)
