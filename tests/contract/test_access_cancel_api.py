"""T03-04 wire conformance; these doubles do not prove PG/OIDC properties."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from opspilot.audit.application.ports import EventPage
from opspilot.entrypoints.api.app import platform_api
from opspilot.identity.domain.principal import ExternalIdentity, Principal, Role
from opspilot.shared.errors import DependencyUnavailable
from opspilot.workflows.domain.access import NotFound, TerminalWorkflow, VersionConflict

from .test_api import deref
from .test_intake_api import CONTRACT


@pytest.fixture
def access_api():
    pid, wid, iid = uuid4(), uuid4(), uuid4()
    state = {"roles": {Role.OPERATOR}, "failure": None, "calls": []}

    class Verifier:
        def verify(self, token):
            return ExternalIdentity("https://test.invalid", "subject")

    class Principals:
        def find(self, identity):
            return Principal(pid, True, frozenset(state["roles"]))

    class Audit:
        def list_events(self, *args):
            return EventPage([], 0)

    workflow = {
        "workflow_id": str(wid),
        "incident_id": str(iid),
        "state": "QUEUED",
        "version": 1,
        "definition_version": 1,
        "cancel_requested_at": None,
        "reason_code": "INTAKE_ACCEPTED",
        "evidence": [],
    }
    incident = {
        "workflow_id": str(wid),
        "incident_id": str(iid),
        "creator_id": str(pid),
        "title": "Prueba",
        "description": "Laboratorio",
        "status": "OPEN",
        "version": 1,
    }

    class Access:
        def read(self, principal, resource, kind):
            state["calls"].append(kind)
            if state["failure"]:
                raise state["failure"]()
            return incident if kind == "incident" else workflow

        def cancel(self, *args):
            state["calls"].append("cancel")
            if state["failure"]:
                raise state["failure"]()
            return {
                "workflow_id": str(wid),
                "state": "CANCELLED",
                "version": 2,
                "cancel_requested_at": "2026-10-23T12:00:00.123456Z",
            }

    app = platform_api(
        Verifier(), Principals(), Audit(), lambda: True, lambda: None, access=Access()
    )
    with TestClient(app) as client:
        yield client, state, iid, wid, app


def send(fixture, route, **kwargs):
    client, _, iid, wid, _ = fixture
    path = {
        "incident": f"/v1/incidents/{iid}",
        "workflow": f"/v1/workflows/{wid}",
        "cancel": f"/v1/workflows/{wid}/cancel",
    }[route]
    return client.request(
        "POST" if route == "cancel" else "GET",
        path,
        headers={"Authorization": "Bearer test", "If-Match": f'"wf-{wid}-v1"'},
        **kwargs,
    )


def test_all_domain_operations_generated_match_approved_wire(access_api):
    *_, app = access_api
    generated = app.openapi()
    validate(generated)
    for path, methods in CONTRACT["paths"].items():
        for method, operation in methods.items():
            actual = generated["paths"][path][method]
            assert actual["operationId"] == operation["operationId"]
            assert set(actual["responses"]) == set(operation["responses"])
            assert actual["security"] == CONTRACT["security"]
            assert [(p["in"], p["name"]) for p in actual["parameters"]] == [
                (p["in"], p["name"]) for p in deref(operation.get("parameters", []), CONTRACT)
            ]
            if method == "get" or path.endswith("/cancel"):
                assert "requestBody" not in actual
            for status, response in operation["responses"].items():
                expected = deref(response, CONTRACT)
                if "headers" in expected and "ETag" in expected["headers"]:
                    assert (
                        actual["responses"][status]["headers"]["ETag"]["schema"]
                        == expected["headers"]["ETag"]["schema"]
                    )


@pytest.mark.parametrize("route", ["incident", "workflow", "cancel"])
def test_exact_success_body_schema_and_headers(access_api, route):
    response = send(access_api, route)
    assert response.status_code == (202 if route == "cancel" else 200)
    schema = {"incident": "Incident", "workflow": "Workflow", "cancel": "CancelAccepted"}[route]
    Draft202012Validator(
        deref(CONTRACT["components"]["schemas"][schema], CONTRACT), format_checker=FormatChecker()
    ).validate(response.json())
    assert (
        response.headers["Cache-Control"] == "no-store"
        and response.headers["X-Content-Type-Options"] == "nosniff"
    )
    if route != "incident":
        assert response.headers["ETag"] == f'"wf-{access_api[3]}-v{response.json()["version"]}"'


@pytest.mark.parametrize(
    "failure,code,status",
    [
        (NotFound, "NOT_FOUND", 404),
        (VersionConflict, "VERSION_CONFLICT", 409),
        (TerminalWorkflow, "TERMINAL_WORKFLOW", 409),
        (DependencyUnavailable, "DEPENDENCY_UNAVAILABLE", 503),
    ],
)
def test_closed_errors_never_add_metadata_or_etag(access_api, failure, code, status):
    access_api[1]["failure"] = failure
    response = send(access_api, "cancel")
    assert response.status_code == status and response.json()["code"] == code
    assert set(response.json()) == {"code", "request_id"} and "ETag" not in response.headers


@pytest.mark.parametrize("route", ["incident", "workflow", "cancel"])
@pytest.mark.parametrize("role", [Role.ADMIN, Role.APPROVER])
def test_route_role_precedes_invalid_input(access_api, route, role):
    access_api[1]["roles"] = {role}
    response = send(access_api, route, content=b"{}", params={"extra": 1})
    assert response.status_code == 403 and not access_api[1]["calls"]
