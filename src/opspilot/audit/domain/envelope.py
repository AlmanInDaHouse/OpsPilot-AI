"""audit-hash-v1: bytes shared by the SQL appender and offline verifier."""

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from opspilot.shared.errors import InvalidEvent

ZERO_HASH = "0" * 64
FIELDS = frozenset(
    {
        "event_id",
        "stream_id",
        "seq",
        "event_type",
        "schema_version",
        "occurred_at",
        "actor_id",
        "trace_id",
        "payload",
        "prev_hash",
    }
)


def canonical_bytes(value: object) -> bytes:
    def validate(item: object) -> None:
        if item is None or type(item) in (bool, int):
            return
        if isinstance(item, str):
            if "\x00" in item or any(0xD800 <= ord(ch) <= 0xDFFF for ch in item):
                raise InvalidEvent("Unsupported Unicode")
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for key, child in item.items():
                validate(key)
                validate(child)
            return
        raise InvalidEvent("Only JSON with integer numbers is supported")

    validate(value)
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def event_hash(envelope: dict[str, Any]) -> str:
    if set(envelope) != FIELDS or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", envelope["occurred_at"]
    ):
        raise InvalidEvent("Invalid envelope")
    return hashlib.sha256(canonical_bytes(envelope)).hexdigest()


def verify_chain(events: Iterable[dict[str, Any]], last_seq: int, last_hash: str) -> bool:
    seq, previous = 0, ZERO_HASH
    stream: str | None = None
    try:
        for row in events:
            digest = row["hash"]
            envelope = {key: value for key, value in row.items() if key != "hash"}
            if stream is None:
                stream = envelope["stream_id"]
            if (
                envelope["stream_id"] != stream
                or envelope["seq"] != seq + 1
                or envelope["prev_hash"] != previous
                or event_hash(envelope) != digest
            ):
                return False
            seq, previous = envelope["seq"], digest
        return (seq, previous) == (last_seq, last_hash)
    except (KeyError, TypeError, InvalidEvent):
        return False
