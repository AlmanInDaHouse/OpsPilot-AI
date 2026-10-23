import hashlib

import pytest

from opspilot.audit.domain.envelope import canonical_bytes, verify_chain
from opspilot.shared.errors import InvalidEvent


def test_golden_utf8_bytes():
    value = {"z": [None, True, False, 12, -3], "é": "漢字😀", "a": 'line\n\t"\\/\b\f\r'}
    expected = b'{"a":"line\\n\\t\\"\\\\/\\b\\f\\r","z":[null,true,false,12,-3],"\xc3\xa9":"\xe6\xbc\xa2\xe5\xad\x97\xf0\x9f\x98\x80"}'
    assert canonical_bytes(value) == expected
    assert (
        hashlib.sha256(canonical_bytes(value)).hexdigest() == hashlib.sha256(expected).hexdigest()
    )


@pytest.mark.parametrize(
    "value", [1.0, float("nan"), {1: "value"}, (1, 2), "\x00", "\ud800", {"x": [0.1]}]
)
def test_noncanonical_values_rejected(value):
    with pytest.raises(InvalidEvent):
        canonical_bytes(value)


def test_empty_stream_anchor_checked():
    assert verify_chain([], 0, "0" * 64)
    assert not verify_chain([], 1, "0" * 64)
