"""Strict transport parsing, deliberately after identity and role authorization."""

import json
import re
from uuid import UUID

from fastapi import Request
from pydantic import ValidationError

from opspilot.entrypoints.api.dto import CreateIncidentInput
from opspilot.incidents.domain.intake import IncidentInput


class InvalidIntake(Exception):
    pass


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidIntake()
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise InvalidIntake()


async def parse_intake(request: Request) -> tuple[UUID, IncidentInput]:
    media_type = request.headers.get("content-type", "")
    if request.query_params or not re.fullmatch(
        r'application/json(?:\s*;\s*charset=(?:utf-8|"utf-8"))?', media_type, re.IGNORECASE
    ):
        raise InvalidIntake()
    key = request.headers.get("idempotency-key", "")
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", key):
        raise InvalidIntake()
    try:
        raw = (await request.body()).decode("utf-8", errors="strict")
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        dto = CreateIncidentInput.model_validate(value)
        return UUID(key), IncidentInput(dto.title, dto.description)
    except (UnicodeError, ValueError, ValidationError, RecursionError) as exc:
        raise InvalidIntake() from exc
