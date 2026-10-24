"""Pure local snapshot decisions and process control, without fake durability claims."""

import hashlib
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from opspilot.audit.domain.envelope import canonical_bytes
from opspilot.entrypoints.worker import Heartbeat, emit, nonnegative
from opspilot.workflows.domain.jobs import (
    Claim,
    IntakeRecord,
    WorkerRejected,
    snapshot_bytes,
    snapshot_hash,
)


def record(title="VPN ñ", description="no ejecutar $(shell)\r\n"):
    return IntakeRecord(UUID(int=1), UUID(int=2), 1, 1, "OPEN", title, description)


def test_snapshot_golden_bytes_hashes_and_unicode_are_exact():
    value = record()
    snapshot = value.snapshot()
    title = hashlib.sha256(value.title.encode("utf-8")).hexdigest()
    description = hashlib.sha256(value.description.encode("utf-8")).hexdigest()
    golden = (
        '{"definition_version":1,"description_hash":"'
        + description
        + '","incident_id":"00000000-0000-0000-0000-000000000001","incident_version":1,"schema_version":1,"status":"OPEN","title_hash":"'
        + title
        + '","workflow_id":"00000000-0000-0000-0000-000000000002"}'
    ).encode()
    assert snapshot_bytes(snapshot) == golden == canonical_bytes(snapshot)
    assert snapshot_hash(snapshot) == hashlib.sha256(golden).hexdigest()
    assert record("VPN n\u0303").snapshot()["title_hash"] != snapshot["title_hash"]
    assert "shell" not in golden.decode() and "VPN" not in golden.decode()


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"definition_version": 2}, "UNSUPPORTED_DEFINITION"),
        ({"status": "RESOLVED"}, "INCIDENT_INCONSISTENT"),
        ({"incident_version": 2}, "INCIDENT_INCONSISTENT"),
    ],
)
def test_handler_rejects_unknown_or_inconsistent_record(changes, code):
    with pytest.raises(WorkerRejected, match=code):
        replace(record(), **changes).snapshot()


def test_structured_log_contains_only_explicit_fields(capsys):
    claim = Claim(uuid4(), uuid4(), uuid4(), uuid4(), 7, 2)
    emit("job.rejected", uuid4(), claim, code="OWNERSHIP_LOST")
    result = json.loads(capsys.readouterr().out)
    assert result["fence"] == 7 and result["code"] == "OWNERSHIP_LOST"
    assert "owner" not in result and "title" not in result and "description" not in result


def test_heartbeat_loss_is_not_swallowed_as_success():
    # Only loop control is fake here; PG lease behavior has separate real integration tests.
    class Once:
        def wait(self, interval):
            assert interval == 15
            return False

    class Broken:
        def renew(self, claim):
            raise WorkerRejected("LEASE_EXPIRED")

    diagnostic = []
    heartbeat = Heartbeat(
        Broken(), Claim(uuid4(), uuid4(), uuid4(), uuid4(), 1, 1), diagnostic.append
    )
    heartbeat.stop = Once()
    heartbeat._run()
    assert heartbeat.lost.is_set() and diagnostic == ["OWNERSHIP_LOST"]


def test_bounded_poll_count_validation():
    assert nonnegative("1") == 1 and nonnegative("0") == 0
    with pytest.raises(ValueError):
        nonnegative("invalid")
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        nonnegative("-1")
