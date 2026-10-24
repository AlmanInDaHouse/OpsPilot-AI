"""Production handler output checked against independent approved schemas."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from opspilot.workflows.domain.jobs import IntakeRecord

ROOT = Path(__file__).resolve().parents[2]


def test_handler_snapshot_exact_schema():
    schema = json.loads((ROOT / "contracts/incident-snapshot-v1.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    snapshot = IntakeRecord(uuid4(), uuid4(), 1, 1, "OPEN", "Synthetic", "$(no shell)").snapshot()
    validator.validate(snapshot)
    with pytest.raises(ValidationError):
        validator.validate({**snapshot, "title": "Never evidence"})
    with pytest.raises(ValidationError):
        validator.validate({**snapshot, "definition_version": 2})


def test_worker_timing_and_output_match_approved_step_contract():
    contract = json.loads((ROOT / "contracts/workflow-step-v1.json").read_text())
    assert (
        contract["lease_seconds"],
        contract["heartbeat_seconds"],
        contract["poll_seconds"],
        contract["poll_jitter_seconds"],
    ) == (60, 15, 2, 1)
    assert contract["transitions"][:2] == [
        {"from": "QUEUED", "to": "INVESTIGATING", "reason_code": "LOCAL_STEP_STARTED"},
        {"from": "INVESTIGATING", "to": "NEEDS_OPERATOR", "reason_code": "LOCAL_SNAPSHOT_RECORDED"},
    ]
