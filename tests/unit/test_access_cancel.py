"""Strict version grammar and closed state classification, no SQL durability claims."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from opspilot.workflows.domain.access import AMBIGUOUS_STATES, MAX_VERSION, SAFE_STATES, WorkflowTag


@pytest.mark.parametrize("version", [1, 3, MAX_VERSION])
def test_strong_tag_roundtrip(version):
    tag = WorkflowTag(uuid4(), version)
    assert WorkflowTag.parse(tag.wire()) == tag


@pytest.mark.parametrize(
    "value",
    [
        "",
        "*",
        'W/"wf-{id}-v1"',
        '"wf-{id}-v0"',
        '"wf-{id}-v01"',
        '"wf-{id}-v-1"',
        '"wf-{id}-v+1"',
        '"wf-{id}-v1.0"',
        '"wf-{id}-v1" ',
        ' "wf-{id}-v1"',
        '"wf-{id}-v1"\n',
        '"wf-{id}-v1", "wf-{id}-v2"',
        '"wf-{id}-v9223372036854775808"',
        '"wf-{id}-v99999999999999999999"',
        "wf-{id}-v1",
        '"wf-FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF-v1"',
    ],
)
def test_strict_match_rejects(value):
    with pytest.raises(ValueError):
        WorkflowTag.parse(value.replace("{id}", str(uuid4())))


def test_cancellation_edges_exactly_match_normative_graph():
    graph = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/workflow-v1.json").read_text()
    )
    assert SAFE_STATES == {
        state for state, targets in graph["transitions"].items() if "CANCELLED" in targets
    }
    assert not SAFE_STATES.intersection(AMBIGUOUS_STATES)
