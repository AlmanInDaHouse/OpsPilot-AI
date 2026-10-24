"""Closed cancellation decisions and resource-bound strong version tags."""

import re
from dataclasses import dataclass
from uuid import UUID

MAX_VERSION = 9223372036854775807
SAFE_STATES = frozenset(
    {"QUEUED", "INVESTIGATING", "PLAN_READY", "AWAITING_APPROVAL", "RETRY_WAIT", "NEEDS_OPERATOR"}
)
AMBIGUOUS_STATES = frozenset({"EXECUTING", "VERIFYING", "OUTCOME_UNKNOWN"})


class NotFound(Exception):
    pass


class VersionConflict(Exception):
    pass


class TerminalWorkflow(Exception):
    pass


@dataclass(frozen=True)
class WorkflowTag:
    workflow_id: UUID
    version: int

    def wire(self) -> str:
        return f'"wf-{self.workflow_id}-v{self.version}"'

    @classmethod
    def parse(cls, value: str) -> "WorkflowTag":
        match = re.fullmatch(
            r'"wf-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})-v([1-9][0-9]{0,18})"',
            value,
        )
        if match is None or int(match[2]) > MAX_VERSION:
            raise ValueError("Invalid workflow tag")
        return cls(UUID(match[1]), int(match[2]))
