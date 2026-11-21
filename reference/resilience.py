"""Self-healing. Every agent's model and tool calls run through `SelfHealer`.
It diagnoses a fault, works through an approved runbook, and hands the decision to
a human when the runbook is exhausted. It never changes infrastructure."""
from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any, Awaitable, Callable

from pydantic import Field

from contracts import Contract, new_id


class FailureKind(StrEnum):
    NETWORK_LOST = "network_lost"
    DNS_FAILURE = "dns_failure"
    TIMEOUT = "timeout"
    THROTTLED = "throttled"
    AUTH_EXPIRED = "auth_expired"
    DEPENDENCY_DOWN = "dependency_down"
    UNKNOWN = "unknown"


class Step(StrEnum):
    PROBE = "probe_connectivity"              # is it us, the network, or the far end?
    RETRY_BACKOFF = "retry_with_backoff"
    REFRESH_CREDENTIAL = "refresh_credential" # new token from the managed identity
    SWITCH_ENDPOINT = "switch_to_approved_alternate"   # next entry in the catalogue or registry
    ESCALATE = "escalate_to_human"


# The approved runbooks. Anything not listed here is not something an agent may do.
RUNBOOKS: dict[FailureKind, list[Step]] = {
    FailureKind.NETWORK_LOST: [Step.PROBE, Step.RETRY_BACKOFF, Step.RETRY_BACKOFF,
                               Step.SWITCH_ENDPOINT, Step.ESCALATE],
    FailureKind.DNS_FAILURE: [Step.PROBE, Step.RETRY_BACKOFF, Step.SWITCH_ENDPOINT, Step.ESCALATE],
    FailureKind.TIMEOUT: [Step.RETRY_BACKOFF, Step.RETRY_BACKOFF, Step.SWITCH_ENDPOINT, Step.ESCALATE],
    FailureKind.THROTTLED: [Step.RETRY_BACKOFF, Step.RETRY_BACKOFF, Step.SWITCH_ENDPOINT, Step.ESCALATE],
    FailureKind.AUTH_EXPIRED: [Step.REFRESH_CREDENTIAL, Step.ESCALATE],
    FailureKind.DEPENDENCY_DOWN: [Step.PROBE, Step.SWITCH_ENDPOINT, Step.RETRY_BACKOFF, Step.ESCALATE],
    FailureKind.UNKNOWN: [Step.ESCALATE],                 # never guess at a fix
}
HUMAN_OPTIONS = ["wait_and_retry", "switch_region", "reduce_scope", "cancel_task"]


def classify(exc: BaseException) -> FailureKind:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None),
                                                          "status_code", None)
    name = type(exc).__name__.lower()
    if status == 429:
        return FailureKind.THROTTLED
    if status in (401, 403):
        return FailureKind.AUTH_EXPIRED
    if status is not None and status >= 500:
        return FailureKind.DEPENDENCY_DOWN
    if "gaierror" in name or "nameresolution" in name:
        return FailureKind.DNS_FAILURE
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in name:
        return FailureKind.TIMEOUT
    if isinstance(exc, (ConnectionError, OSError)):
        return FailureKind.NETWORK_LOST
    return FailureKind.UNKNOWN


class Incident(Contract):
    incident_id: str = Field(default_factory=lambda: new_id("inc"))
    project_id: str
    agent_id: str
    operation: str
    kind: FailureKind
    error: str
    steps_tried: list[tuple[Step, bool]] = []
    resolved: bool = False
    options: list[str] = []          # offered to the human when escalated


class NeedsHuman(Exception):
    """The runbook is exhausted. Carries the incident and the choices on offer."""
    def __init__(self, incident: Incident) -> None:
        super().__init__(f"{incident.kind} on {incident.operation}: human decision needed")
        self.incident = incident


class SelfHealer:
    def __init__(self, actions: dict[Step, Callable[[Incident, int], Awaitable[bool]]],
                 record: Callable[[Incident], Awaitable[None]]) -> None:
        self.actions, self.record = actions, record

    async def run(self, operation: Callable[[], Awaitable[Any]], *, name: str,
                  project_id: str, agent_id: str) -> Any:
        """`operation` must be idempotent: it may be called several times."""
        try:
            return await operation()
        except Exception as exc:                       # noqa: BLE001 - classified below
            incident = Incident(project_id=project_id, agent_id=agent_id, operation=name,
                                kind=classify(exc), error=repr(exc))
        for attempt, step in enumerate(RUNBOOKS[incident.kind]):
            if step is Step.ESCALATE:
                break
            ok = await self.actions[step](incident, attempt)
            incident.steps_tried.append((step, ok))
            if step is Step.PROBE or not ok:
                continue                               # a probe informs; it fixes nothing
            try:
                result = await operation()
            except Exception as exc:                   # noqa: BLE001
                incident.error = repr(exc)
                continue
            incident.resolved = True
            await self.record(incident)                # healed faults are still reported
            return result
        incident.options = HUMAN_OPTIONS
        await self.record(incident)
        raise NeedsHuman(incident)
