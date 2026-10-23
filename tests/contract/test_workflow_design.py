"""T03-01 specification tests; these do NOT prove S03 runtime or durability."""

import copy
import hashlib
import itertools
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from pydantic import ValidationError

from opspilot.audit.domain.envelope import canonical_bytes
from opspilot.entrypoints.api.dto import WorkflowAuditEvent

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
IID = "10000000-0000-0000-0000-000000000001"
WID = "20000000-0000-0000-0000-000000000002"
PID = "30000000-0000-0000-0000-000000000003"
EID = "40000000-0000-0000-0000-000000000004"
STAMP = "2026-10-23T12:00:00.000001Z"


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


API = load("workflows.openapi.json")
EVENT = load("workflow-events-v2.schema.json")
STEP = load("workflow-step-v1.json")
POLICY = load("workflow-policy-v1.json")
GRAPH = load("workflow-v1.json")
STATES = GRAPH["states"]


def resolve(value, document):
    if isinstance(value, dict):
        if "$ref" in value:
            assert value["$ref"].startswith("#/"), "No network or hidden cross-file references"
            target = document
            for part in value["$ref"][2:].split("/"):
                target = target[part]
            return resolve(target, document)
        return {key: resolve(child, document) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve(child, document) for child in value]
    return value


def validator(schema, document=None):
    return Draft202012Validator(resolve(schema, document or schema), format_checker=FormatChecker())


def event(kind="workflow.transitioned", source="QUEUED", target="INVESTIGATING", reason=None):
    payload = {
        "reason_code": reason or "LOCAL_STEP_STARTED",
        "aggregate_id": WID,
        "aggregate_version": 2,
        "evidence_ids": [],
        "snapshot_hash": "0" * 64,
    }
    actor = None
    if kind == "incident.created":
        payload = {
            "reason_code": "INTAKE_ACCEPTED",
            "aggregate_id": IID,
            "aggregate_version": 1,
            "evidence_ids": [],
        }
        actor = PID
    elif kind == "workflow.transitioned":
        payload["transition"] = {"from": source, "to": target, "definition_version": 1}
        if reason == "LOCAL_SNAPSHOT_RECORDED":
            payload["evidence_ids"] = [EID]
        if reason == "CANCELLED_BY_OPERATOR":
            actor = PID
    elif kind == "workflow.cancel_requested":
        payload["reason_code"] = "CANCEL_REQUESTED"
        actor = PID
    elif kind == "workflow.blocked":
        payload["reason_code"] = "UNSUPPORTED_DEFINITION"
    return {
        "event_id": EID,
        "schema_version": 2,
        "stream_id": IID if kind == "incident.created" else WID,
        "seq": 1,
        "event_type": kind,
        "occurred_at": STAMP,
        "actor_id": actor,
        "trace_id": "0" * 31 + "1",
        "payload": payload,
    }


def test_openapi_and_all_schemas_are_standard_valid_and_local():
    validate(resolve(API, API))
    for name in (
        "workflow-events-v2.schema.json",
        "incident-snapshot-v1.schema.json",
        "workflow-snapshot-v1.schema.json",
    ):
        schema = load(name)
        Draft202012Validator.check_schema(schema)
        resolve(schema, schema)


def test_spec_operations_roles_and_state_vocabularies_agree():
    operations = {
        operation["operationId"]
        for methods in API["paths"].values()
        for operation in methods.values()
    }
    assert (
        operations
        == set(POLICY["routes"])
        == {
            "createIncident",
            "getIncident",
            "getWorkflow",
            "cancelWorkflow",
        }
    )
    assert API["security"] == [{"bearerAuth": []}]
    assert not POLICY["role_inheritance"] and POLICY["default"] == "DENY"
    for operation in POLICY["routes"].values():
        assert not {"admin", "approver"} & set(operation["roles"])
    for name in ("createIncident", "cancelWorkflow"):
        assert POLICY["routes"][name]["roles"] == ["operator"]
    assert API["components"]["schemas"]["State"]["enum"] == STATES
    assert load("workflow-snapshot-v1.schema.json")["properties"]["state"]["enum"] == STATES
    for field in ("from", "to"):
        assert (
            EVENT["$defs"]["transitioned"]["properties"]["transition"]["properties"][field]["enum"]
            == STATES
        )
    assert set(STEP["safe_cancel_states"]) | set(STEP["deferred_cancel_states"]) | set(
        GRAPH["terminal"]
    ) == set(STATES)


@pytest.mark.parametrize("edge", STEP["transitions"])
def test_every_local_step_edge_is_normative_and_accepted(edge):
    assert edge["to"] in GRAPH["transitions"][edge["from"]]
    assert edge["to"] not in {"PLAN_READY", "EXECUTING", "SUCCEEDED", "VERIFYING"}
    validator(EVENT).validate(
        event(source=edge["from"], target=edge["to"], reason=edge["reason_code"])
    )


@pytest.mark.parametrize("source", STATES)
@pytest.mark.parametrize("target", STATES)
def test_event_schema_only_allows_reviewed_s03_edges(source, target):
    reasons = {
        edge["reason_code"]
        for edge in STEP["transitions"]
        if (edge["from"], edge["to"]) == (source, target)
    }
    if source in STEP["safe_cancel_states"] and target == "CANCELLED":
        reasons.add("CANCELLED_BY_OPERATOR")
    accepted = set()
    for reason in API["components"]["schemas"]["Reason"]["enum"]:
        value = event(source=source, target=target, reason=reason)
        conforms = validator(EVENT).is_valid(value)
        try:
            WorkflowAuditEvent.model_validate(value)
            dto_valid = True
        except ValidationError:
            dto_valid = False
        assert dto_valid == conforms
        if conforms:
            accepted.add(reason)
    assert accepted == reasons


@pytest.mark.parametrize(
    "kind", ["incident.created", "workflow.cancel_requested", "workflow.blocked"]
)
def test_non_transition_event_examples_and_cross_type_payload_rejection(kind):
    value = event(kind)
    validator(EVENT).validate(value)
    for other in {"incident.created", "workflow.cancel_requested", "workflow.blocked"} - {kind}:
        invalid = copy.deepcopy(value)
        invalid["event_type"] = other
        assert not validator(EVENT).is_valid(invalid)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("event_type", "intent.dispatched"),
        ("event_type", "arbitrary.event"),
        ("seq", 0),
        ("actor_id", PID),
        ("trace_id", "not-a-trace"),
        ("occurred_at", "2026-10-23T12:00:00Z"),
        ("occurred_at", "2026-13-23T12:00:00.000001Z"),
        ("event_id", "bad-id"),
    ],
)
def test_event_envelope_negative_instances(field, value):
    invalid = event()
    invalid[field] = value
    assert not validator(EVENT).is_valid(invalid)


def test_event_payload_closed_missing_fields_wrong_versions_and_evidence():
    value = event()
    for field in value["payload"]:
        invalid = copy.deepcopy(value)
        del invalid["payload"][field]
        assert not validator(EVENT).is_valid(invalid)
    for extra in ("token", "owner", "lease_until", "title", "description", "shell"):
        invalid = copy.deepcopy(value)
        invalid["payload"][extra] = "rejected-fixture"
        assert not validator(EVENT).is_valid(invalid)
    value["payload"]["transition"]["definition_version"] = 2
    assert not validator(EVENT).is_valid(value)
    value = event(source="INVESTIGATING", target="NEEDS_OPERATOR", reason="LOCAL_SNAPSHOT_RECORDED")
    value["payload"]["evidence_ids"] = []
    assert not validator(EVENT).is_valid(value)
    value["payload"]["evidence_ids"] = [EID, EID]
    assert not validator(EVENT).is_valid(value)


def test_unknown_definition_is_hold_without_a_new_transition_or_handler_fallback():
    assert STEP["unknown_definition"] == "HOLD_CURRENT_STATE"
    state = {
        "schema_version": 1,
        "workflow_id": WID,
        "incident_id": IID,
        "definition_version": 42,
        "state": "QUEUED",
        "version": 2,
        "cancel_requested_at": None,
        "reason_code": "UNSUPPORTED_DEFINITION",
    }
    validator(load("workflow-snapshot-v1.schema.json")).validate(state)
    validator(EVENT).validate(event("workflow.blocked"))
    assert "NEEDS_OPERATOR" not in GRAPH["transitions"]["QUEUED"]
    cancelled = event(source="QUEUED", target="CANCELLED", reason="CANCELLED_BY_OPERATOR")
    cancelled["payload"]["transition"]["definition_version"] = 42
    validator(EVENT).validate(cancelled)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "a"},
        {"title": "", "description": "b"},
        {"title": "a", "description": ""},
        {"title": "a" * 201, "description": "b"},
        {"title": "a", "description": "b" * 4001},
        {"title": 1, "description": "b"},
        {"title": "a", "description": False},
        {"title": "a", "description": "b", "state": "SUCCEEDED"},
        {"title": "a", "description": "b", "creator_id": PID},
    ],
)
def test_intake_schema_negative_instances(body):
    assert not validator(API["components"]["schemas"]["CreateIncident"], API).is_valid(body)


@pytest.mark.parametrize("title,description", [("a", "b"), ("ñ" * 200, "界" * 4000)])
def test_intake_schema_valid_boundaries(title, description):
    validator(API["components"]["schemas"]["CreateIncident"], API).validate(
        {"title": title, "description": description}
    )


@pytest.mark.parametrize(
    "tag",
    [
        "1",
        '"1"',
        "*",
        f'W/"wf-{WID}-v1"',
        f'"wf-{WID}-v0"',
        f'"wf-{WID}-v01"',
        f'"wf-{WID}-v1", "wf-{WID}-v2"',
        f' "wf-{WID}-v1"',
        f'"wf-{WID}-v1"\n',
        '"wf-NOT-A-UUID-v1"',
    ],
)
def test_cas_tag_shape_rejects_ambiguous_or_weak_input(tag):
    assert not validator(API["components"]["schemas"]["WorkflowETag"], API).is_valid(tag)


@pytest.mark.parametrize("version", [1, 9223372036854775807])
def test_cas_tag_shape_accepts_valid_boundaries(version):
    validator(API["components"]["schemas"]["WorkflowETag"], API).validate(f'"wf-{WID}-v{version}"')


def test_every_http_status_has_a_valid_closed_response_example():
    workflow = {
        "workflow_id": WID,
        "incident_id": IID,
        "state": "QUEUED",
        "version": 1,
        "definition_version": 1,
        "cancel_requested_at": None,
        "reason_code": "INTAKE_ACCEPTED",
        "evidence": [],
    }
    incident = {
        "incident_id": IID,
        "workflow_id": WID,
        "creator_id": PID,
        "title": "VPN de prueba",
        "description": "Laboratorio sintético",
        "status": "OPEN",
        "version": 1,
    }
    codes = {
        "401": "UNAUTHENTICATED",
        "403": "FORBIDDEN",
        "404": "NOT_FOUND",
        "422": "INVALID_REQUEST",
        "503": "DEPENDENCY_UNAVAILABLE",
    }
    for path, methods in API["paths"].items():
        for operation in methods.values():
            for status, response in operation["responses"].items():
                resolved = resolve(response, API)
                schema = resolved["content"]["application/json"]["schema"]
                if status in codes:
                    value = {"code": codes[status], "request_id": EID}
                    for wrong in set(codes.values()) - {codes[status]}:
                        assert not validator(schema).is_valid({**value, "code": wrong})
                elif status == "409":
                    value = {
                        "code": "VERSION_CONFLICT"
                        if path.endswith("/cancel")
                        else "IDEMPOTENCY_CONFLICT",
                        "request_id": EID,
                    }
                elif path.endswith("/cancel"):
                    value = {
                        "workflow_id": WID,
                        "state": "CANCELLED",
                        "version": 2,
                        "cancel_requested_at": STAMP,
                    }
                    assert not validator(schema).is_valid({**value, "state": "QUEUED"})
                elif status == "202":
                    value = {"incident_id": IID, "workflow_id": WID}
                elif path.startswith("/v1/workflows/"):
                    value = workflow
                else:
                    value = incident
                validator(schema).validate(value)
                assert not validator(schema).is_valid({**value, "lease_owner": "private-fixture"})
                for required in schema.get("required", []):
                    invalid = {key: child for key, child in value.items() if key != required}
                    assert not validator(schema).is_valid(invalid)
                if path.startswith("/v1/workflows/") and status in {"200", "202"}:
                    header = resolve(resolved["headers"]["ETag"], API)
                    assert header["required"] is True
                    validator(header["schema"]).validate(f'"wf-{WID}-v{value["version"]}"')


@pytest.mark.parametrize("kind", ["incident.created", "workflow.cancel_requested"])
def test_operator_events_require_actor_and_cannot_be_forged_as_system(kind):
    value = event(kind)
    value["actor_id"] = None
    assert not validator(EVENT).is_valid(value)


def test_worker_permission_plan_preserves_audit_and_evidence_boundaries():
    grants = POLICY["roles"]["opspilot_worker"]
    assert not {"principals", "role_grants", "api_idempotency"} & set(grants)
    assert grants["incidents"] == ["SELECT"]
    assert grants["evidence"] == ["SELECT", "INSERT"]
    assert grants["audit_append_v2"] == ["EXECUTE"]
    for role in POLICY["roles"].values():
        assert not {"audit_events", "audit_streams"} & set(role)
        assert not any(
            permission in {"DELETE", "TRUNCATE", "ALL", "CREATE"}
            for permissions in role.values()
            for permission in permissions
        )


def test_golden_canonical_request_and_local_snapshot_bytes():
    golden = json.loads((ROOT / "tests/fixtures/workflow-hash-v1.json").read_text(encoding="utf-8"))
    for case in golden["cases"]:
        encoded = canonical_bytes(case["value"])
        assert encoded.decode("utf-8") == case["canonical_utf8"]
        assert hashlib.sha256(encoded).hexdigest() == case["hash"]
        if case["kind"] == "incident_snapshot":
            validator(load("incident-snapshot-v1.schema.json")).validate(case["value"])
    request = golden["cases"][0]["value"]
    snapshot = golden["cases"][1]["value"]
    for field in ("title", "description"):
        assert (
            snapshot[f"{field}_hash"]
            == hashlib.sha256(request["body"][field].encode("utf-8")).hexdigest()
        )
    reordered = dict(reversed(list(request.items())))
    reordered["body"] = dict(reversed(list(request["body"].items())))
    assert canonical_bytes(request) == canonical_bytes(reordered)
    changed = copy.deepcopy(request)
    changed["body"]["title"] += " "
    assert canonical_bytes(request) != canonical_bytes(changed)


def test_snapshot_rejects_free_text_extra_fields_and_fake_resolution():
    schema = load("incident-snapshot-v1.schema.json")
    value = {
        "schema_version": 1,
        "incident_id": IID,
        "incident_version": 1,
        "workflow_id": WID,
        "definition_version": 1,
        "status": "OPEN",
        "title_hash": "0" * 64,
        "description_hash": "1" * 64,
    }
    validator(schema).validate(value)
    for key in value:
        invalid = copy.deepcopy(value)
        del invalid[key]
        assert not validator(schema).is_valid(invalid)
    for key, child in itertools.chain(
        ((name, "free-text-fixture") for name in ("title", "description", "token", "reasoning")),
        (("status", "RESOLVED"), ("definition_version", 2), ("title_hash", "bad-hash")),
    ):
        invalid = {**value, key: child}
        assert not validator(schema).is_valid(invalid)
