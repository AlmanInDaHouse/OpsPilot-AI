"""S03 has no body/query/conditional GET; version headers are parsed exactly."""

import re
from uuid import UUID

from fastapi import Request

from opspilot.workflows.domain.access import WorkflowTag

WORKFLOW_ETAG_SCHEMA = {
    "type": "string",
    "pattern": '^"wf-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-v[1-9][0-9]{0,18}"$(?![\\s\\S])',
    "maxLength": 62,
}


class InvalidAccess(Exception):
    pass


async def parse_resource(request: Request, resource: str) -> UUID:
    if (
        request.query_params
        or await request.body()
        or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", resource)
    ):
        raise InvalidAccess()
    return UUID(resource)


def parse_match(request: Request) -> WorkflowTag:
    values = request.headers.getlist("if-match")
    if len(values) != 1:
        raise InvalidAccess()
    try:
        return WorkflowTag.parse(values[0])
    except ValueError as exc:
        raise InvalidAccess() from exc
